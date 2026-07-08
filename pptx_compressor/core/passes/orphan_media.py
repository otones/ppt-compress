"""Pass 7: remove orphan media files.

Scans every .rels in the archive for media relationships (image/audio
but NOT video — see Non-Goals) and collects the set of referenced media
paths. Any file under ppt/media/ that is *not* referenced gets deleted,
along with its content-type override.

Video files (mp4/avi/mov/wmv) are always preserved per Non-Goals.
"""

from __future__ import annotations

from typing import Set

from ..pptx import PptxFile, qn
from .base import CompressionPass


# Relationship type suffixes that point into ppt/media/.
MEDIA_REL_SUFFIXES = {
    "image",
    "audio",
    "media",
}

# Video extensions we must NOT delete (Non-Goal: no video re-encoding, but
# orphan *video* deletion is also risky for speakers — keep them).
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".wmv", ".m4v", ".mkv", ".webm", ".mpeg", ".mpg"}


class OrphanMediaPass(CompressionPass):
    id = "remove_orphan_media"
    label = "删除孤儿媒体"

    def run(self, pptx: PptxFile) -> PassReport:
        if not self.report.enabled:
            return self.report
        self.report.ran = True

        referenced = self._collect_referenced_media(pptx)

        for path in list(pptx.list_paths()):
            if not path.startswith("ppt/media/"):
                continue
            ext = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path else ""
            if ext in VIDEO_EXTS:
                continue  # Non-Goal: never touch video.
            if path in referenced:
                continue
            size = self._size_of(pptx, path)
            pptx.remove_content_type_override(path)
            pptx.delete_part(path)
            self.report.bytes_freed += size
            self.report.items_affected += 1
            self.report.add_detail(f"删除孤儿媒体 {path}({size} 字节)")

        return self.report

    def _collect_referenced_media(self, pptx: PptxFile) -> Set[str]:
        referenced: Set[str] = set()
        for path in pptx.list_paths():
            if not path.endswith(".rels"):
                continue
            # foo/_rels/bar.xml.rels owns part foo/bar.xml.
            owning = self._owning_part_for_rels(path)
            if owning is None:
                continue
            rels = pptx.get_rels(owning)
            for rel in rels.relationships:
                if rel.target_mode == "External":
                    continue
                if rel.type_short in MEDIA_REL_SUFFIXES:
                    target = rels.resolve_target(rel)
                    if target.startswith("ppt/media/"):
                        referenced.add(target)
        return referenced

    def _owning_part_for_rels(self, rels_path: str):
        # foo/_rels/bar.xml.rels -> foo/bar.xml
        if not rels_path.endswith("/.rels") and not rels_path.endswith(".rels"):
            return None
        if rels_path == "_rels/.rels":
            return ""  # package root
        no_rels = rels_path[: -len(".rels")]
        if "/_rels/" in no_rels:
            idx = no_rels.rfind("/_rels/")
            base = no_rels[:idx]
            name = no_rels[idx + len("/_rels/"):]
            return f"{base}/{name}" if base else name
        return no_rels
