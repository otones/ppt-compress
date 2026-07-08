"""PPTX file wrapper.

A .pptx is a ZIP archive (OOXML) of XML "parts" related by .rels files.
This module provides a high-level read/modify/write API over the archive
with namespace-aware XML parsing and relationship (rels) management.
"""

from __future__ import annotations

import io
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

from lxml import etree

# ---------------------------------------------------------------------------
# OOXML namespaces
# ---------------------------------------------------------------------------
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
}


def qn(prefix: str, tag: str) -> str:
    """Build a Clark-notation qualified name from a namespace prefix."""
    return "{%s}%s" % (NS[prefix], tag)


def _strip_root(path: str) -> str:
    return path.lstrip("/")


def _parent_dir(path: str) -> str:
    p = _strip_root(path)
    if "/" not in p:
        return ""
    return p.rsplit("/", 1)[0]


def _basename(path: str) -> str:
    return _strip_root(path).rsplit("/", 1)[-1]


def _join(base: str, rel: str) -> str:
    """Resolve a relationship target (which may be relative) against base dir."""
    rel = rel.replace("\\", "/")
    if rel.startswith("/"):
        return _strip_root(rel)
    # collapse "../" segments
    parts = base.split("/")
    for seg in rel.split("/"):
        if seg == "" or seg == ".":
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)


# ---------------------------------------------------------------------------
# Relationship handling
# ---------------------------------------------------------------------------
@dataclass
class Relationship:
    """A single <Relationship> entry inside a .rels part."""

    id: str
    type: str
    target: str  # as stored (relative or absolute)
    target_mode: Optional[str] = None  # "External" or None

    @property
    def type_short(self) -> str:
        return self.type.rsplit("/", 1)[-1]


class RelsPart:
    """In-memory representation of a *.rels part."""

    def __init__(self, path: str, root: etree._Element):
        self.path = path
        self.root = root
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self.relationships: List[Relationship] = []
        for rel in self.root.findall(qn("rel", "Relationship")):
            self.relationships.append(
                Relationship(
                    id=rel.get("Id"),
                    type=rel.get("Type"),
                    target=rel.get("Target"),
                    target_mode=rel.get("TargetMode"),
                )
            )

    def find_by_type(self, type_suffix: str) -> List[Relationship]:
        return [r for r in self.relationships if r.type_short == type_suffix]

    def find_by_id(self, rid: str) -> Optional[Relationship]:
        for r in self.relationships:
            if r.id == rid:
                return r
        return None

    def resolve_target(self, rel: Relationship) -> str:
        """Return the absolute (archive-relative) path of a relationship target."""
        base_dir = _parent_dir(self.path)
        # rels files live in a "_rels" sibling dir; the base for resolution is
        # the directory of the *owning* part, i.e. parent of the _rels folder.
        if base_dir.endswith("/_rels"):
            base_dir = base_dir[: -len("/_rels")]
        return _join(base_dir, rel.target)

    def remove_relationship(self, rid: str) -> bool:
        for rel_el in self.root.findall(qn("rel", "Relationship")):
            if rel_el.get("Id") == rid:
                self.root.remove(rel_el)
                self._rebuild_index()
                return True
        return False

    def serialize(self) -> bytes:
        return etree.tostring(
            self.root, xml_declaration=True, encoding="UTF-8", standalone=True
        )


# ---------------------------------------------------------------------------
# Part abstraction
# ---------------------------------------------------------------------------
@dataclass
class Part:
    """A single archive member."""

    path: str
    data: bytes
    is_xml: bool
    # Parsed tree (lazy), only for XML parts.
    _tree: Optional[etree._ElementTree] = field(default=None, repr=False)

    @property
    def tree(self) -> etree._ElementTree:
        if self._tree is None:
            # Reparse to get an ElementTree with root access.
            self._tree = etree.ElementTree(etree.fromstring(self.data))
        return self._tree

    @property
    def root(self) -> etree._Element:
        return self.tree.getroot()

    def commit_tree(self) -> None:
        """Serialize the (possibly modified) tree back into .data."""
        if self._tree is None:
            return
        self.data = etree.tostring(
            self._tree, xml_declaration=True, encoding="UTF-8", standalone=True
        )


class PptxFile:
    """Read/modify/write a .pptx archive entirely in memory.

    The original file is never mutated. Call save() to emit a new archive.
    """

    def __init__(self, source: str | os.PathLike | bytes):
        self.parts: Dict[str, Part] = {}
        self._deleted: set = set()
        self.source_name: Optional[str] = None

        if isinstance(source, (str, os.PathLike)):
            self.source_name = str(source)
            with open(source, "rb") as f:
                raw = f.read()
        else:
            raw = bytes(source)

        self._load(raw)

    # ------------------------------------------------------------------ load
    def _load(self, raw: bytes) -> None:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                data = zf.read(info.filename)
                path = _strip_root(info.filename)
                is_xml = path.endswith(".xml") or path.endswith(".rels")
                self.parts[path] = Part(path=path, data=data, is_xml=is_xml)

    # --------------------------------------------------------------- access
    def __contains__(self, path: str) -> bool:
        return _strip_root(path) in self.parts

    def get_part(self, path: str) -> Optional[Part]:
        return self.parts.get(_strip_root(path))

    def iter_parts(self) -> Iterator[Part]:
        return iter(self.parts.values())

    def list_paths(self) -> List[str]:
        return sorted(self.parts.keys())

    # ----------------------------------------------------- rels convenience
    def rels_path_for(self, part_path: str) -> str:
        """Return the .rels path that owns relationships for part_path."""
        part_path = _strip_root(part_path)
        base = _parent_dir(part_path)
        name = _basename(part_path) + ".rels"
        if base:
            return f"{base}/_rels/{name}"
        return f"_rels/{name}"

    def get_rels(self, part_path: str) -> RelsPart:
        """Return the RelsPart for part_path, creating an empty one if missing."""
        rp = self.rels_path_for(part_path)
        part = self.parts.get(rp)
        if part is None:
            # None key = default namespace (lxml convention).
            root = etree.Element(qn("rel", "Relationships"), nsmap={None: NS["rel"]})
            return RelsPart(path=rp, root=root)
        return RelsPart(path=rp, root=part.root)

    def save_rels(self, rels: RelsPart) -> None:
        # Only persist if it still has relationships OR it already existed.
        existing = rels.path in self.parts
        if not rels.relationships and not existing:
            return
        part = self.parts.get(rels.path)
        if part is None:
            part = Part(path=rels.path, data=b"", is_xml=True)
            self.parts[rels.path] = part
        part.data = rels.serialize()
        part._tree = None  # invalidate cached tree

    # ----------------------------------------------------------- mutation
    def delete_part(self, path: str) -> bool:
        path = _strip_root(path)
        if path not in self.parts:
            return False
        del self.parts[path]
        self._deleted.add(path)
        # Also drop its rels part if present.
        rp = self.rels_path_for(path)
        if rp in self.parts:
            del self.parts[rp]
        return True

    def replace_part_data(self, path: str, data: bytes) -> None:
        path = _strip_root(path)
        part = self.parts.get(path)
        if part is None:
            self.parts[path] = Part(path=path, data=data, is_xml=False)
        else:
            part.data = data
            part._tree = None

    def commit_part_tree(self, path: str) -> None:
        part = self.parts.get(_strip_root(path))
        if part is not None:
            part.commit_tree()

    # ----------------------------------------------------------------- save
    def save(self, output: str | os.PathLike) -> None:
        """Write the (modified) archive to output path."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            # [Content_Types].xml must be first for some strict readers.
            ct = "[Content_Types].xml"
            if ct in self.parts:
                zf.writestr(ct, self.parts[ct].data)
            for path, part in sorted(self.parts.items()):
                if path == ct:
                    continue
                zf.writestr(path, part.data)
        data = buf.getvalue()
        with open(output, "wb") as f:
            f.write(data)

    # ------------------------------------------------------- content types
    def content_types_root(self) -> etree._Element:
        return self.parts["[Content_Types].xml"].root

    def remove_content_type_override(self, part_path: str) -> bool:
        """Remove <Override PartName="/..."> entry for part_path."""
        ct = self.content_types_root()
        target = "/" + _strip_root(part_path)
        for ov in ct.findall(qn("ct", "Override")):
            if ov.get("PartName") == target:
                ct.remove(ov)
                self.commit_part_tree("[Content_Types].xml")
                return True
        return False

    def add_default_extension(self, ext: str, content_type: str) -> None:
        ct = self.content_types_root()
        ext = ext.lstrip(".")
        for d in ct.findall(qn("ct", "Default")):
            if d.get("Extension") == ext:
                return
        el = etree.SubElement(ct, qn("ct", "Default"))
        el.set("Extension", ext)
        el.set("ContentType", content_type)
        self.commit_part_tree("[Content_Types].xml")

    def remove_default_extension(self, ext: str) -> bool:
        ct = self.content_types_root()
        ext = ext.lstrip(".")
        for d in ct.findall(qn("ct", "Default")):
            if d.get("Extension") == ext:
                ct.remove(d)
                self.commit_part_tree("[Content_Types].xml")
                return True
        return False
