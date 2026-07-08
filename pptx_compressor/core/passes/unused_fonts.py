"""Pass 4: remove embedded-but-unused font subsets.

presentation.xml may carry <p:embeddedFontLst> with <p:embeddedFont>
entries, each pointing (via rels rId) to a font blob in ppt/fonts/.
We collect every <a:rFont>/<a:latin>/<a:ea>/<a:cs>/<a:sym> typeface
referenced from slide/layout/master/theme XML, then drop embedded fonts
whose typeface is never referenced.
"""

from __future__ import annotations

from typing import Set

from ..pptx import PptxFile, qn
from .base import CompressionPass


# All attributes that can carry a typeface name.
FONT_ATTRS = {
    "typeface",
}


class UnusedFontsPass(CompressionPass):
    id = "remove_unused_fonts"
    label = "删除未使用嵌入字体"

    def run(self, pptx: PptxFile) -> PassReport:
        if not self.report.enabled:
            return self.report
        self.report.ran = True

        pres_path = "ppt/presentation.xml"
        pres = pptx.get_part(pres_path)
        if pres is None:
            return self.report

        font_lst = pres.root.find(qn("p", "embeddedFontLst"))
        if font_lst is None:
            return self.report

        used_typefaces = self._collect_used_typefaces(pptx)

        pres_rels = pptx.get_rels(pres_path)
        rids_to_drop = []

        for ef in list(font_lst.findall(qn("p", "embeddedFont"))):
            typeface = ef.get("typeface")
            if typeface is None:
                # Read from <p:font typeface="..."/>
                fnt = ef.find(qn("p", "font"))
                if fnt is not None:
                    typeface = fnt.get("typeface")
            if typeface is not None and typeface in used_typefaces:
                continue
            # Unused. Collect each regular/bold/italic/boldItalic rel id.
            for style_tag in ("regular", "bold", "italic", "boldItalic"):
                el = ef.find(qn("p", style_tag))
                if el is None:
                    continue
                rid = el.get(qn("r", "id"))
                if not rid:
                    continue
                rel = pres_rels.find_by_id(rid)
                if rel is None:
                    continue
                font_path = pres_rels.resolve_target(rel)
                size = self._size_of(pptx, font_path)
                self.report.bytes_freed += size
                self.report.items_affected += 1
                self.report.add_detail(
                    f"删除未使用嵌入字体 {typeface!r} ({style_tag}) → {font_path}({size} 字节)"
                )
                rids_to_drop.append(rid)
                pptx.delete_part(font_path)
            font_lst.remove(ef)

        for rid in rids_to_drop:
            pres_rels.remove_relationship(rid)
        pptx.save_rels(pres_rels)
        pptx.commit_part_tree(pres_path)

        return self.report

    def _collect_used_typefaces(self, pptx: PptxFile) -> Set[str]:
        used: Set[str] = set()
        # Scan slide/layout/master/theme xml for typeface attributes.
        scan_prefixes = (
            "ppt/slides/slide",
            "ppt/slideLayouts/slideLayout",
            "ppt/slideMasters/slideMaster",
            "ppt/theme/theme",
            "ppt/notesSlides/notesSlide",
        )
        for path in pptx.list_paths():
            if not path.endswith(".xml"):
                continue
            if not path.startswith(scan_prefixes):
                continue
            part = pptx.get_part(path)
            if part is None:
                continue
            for el in part.root.iter():
                for attr in FONT_ATTRS:
                    val = el.get(attr)
                    if val:
                        used.add(val)
        # "+mn-lt"/"+mj-lt" minor/major scheme refs aren't typeface names;
        # the actual font is in theme. We added theme scan above so it's fine.
        return used
