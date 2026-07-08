"""Pass 2: remove hidden slides.

A slide is hidden when <p:sld show="0">. Removing a slide safely requires:
  - deleting ppt/slides/slideN.xml and its .rels
  - removing the slideId reference in presentation.xml
  - removing the relationship from presentation.xml.rels
  - dropping any notesSlide / commentary rels that belonged to the slide
"""

from __future__ import annotations

from typing import List

from ..pptx import PptxFile, qn
from .base import CompressionPass


class HiddenSlidesPass(CompressionPass):
    id = "remove_hidden_slides"
    label = "删除隐藏幻灯片"

    def run(self, pptx: PptxFile) -> PassReport:
        if not self.report.enabled:
            return self.report
        self.report.ran = True

        pres_path = "ppt/presentation.xml"
        pres = pptx.get_part(pres_path)
        if pres is None:
            return self.report
        pres_rels = pptx.get_rels(pres_path)

        # Build slideIdLst -> rId mapping.
        sld_id_lst = pres.root.find(qn("p", "sldIdLst"))
        if sld_id_lst is None:
            return self.report

        # Slide rels use type suffix "slide" (officedocument slide).
        slide_rels = pres_rels.find_by_type("slide")
        rid_to_target = {r.id: pres_rels.resolve_target(r) for r in slide_rels}

        to_remove: List[str] = []  # slide part paths
        rid_to_remove: List[str] = []

        for sld_id_el in list(sld_id_lst.findall(qn("p", "sldId"))):
            rid = sld_id_el.get(qn("r", "id"))
            if rid is None:
                continue
            slide_path = rid_to_target.get(rid)
            if slide_path is None:
                continue
            slide_part = pptx.get_part(slide_path)
            if slide_part is None:
                continue
            # Hidden when show attribute exists and equals "0".
            show = slide_part.root.get("show")
            if show == "0":
                size = self._size_of(pptx, slide_path)
                to_remove.append(slide_path)
                rid_to_remove.append(rid)
                self.report.bytes_freed += size
                self.report.items_affected += 1
                self.report.add_detail(
                    f"删除隐藏幻灯片 {slide_path}({size} 字节)"
                )
                # Remove from sldIdLst.
                sld_id_lst.remove(sld_id_el)

        # Remove the relationships for deleted slides.
        for rid in rid_to_remove:
            pres_rels.remove_relationship(rid)
        pptx.save_rels(pres_rels)
        pptx.commit_part_tree(pres_path)

        # Delete slide parts + their rels + their notesSlides.
        for slide_path in to_remove:
            self._delete_slide_and_notes(pptx, slide_path)

        return self.report

    def _delete_slide_and_notes(self, pptx: PptxFile, slide_path: str) -> None:
        # Delete the slide part (its rels part is auto-deleted by delete_part).
        pptx.delete_part(slide_path)
        # Look for notesSlide referenced by the (now deleted) slide's rels.
        # We re-read the rels object: PptxFile.get_rels returns an empty stub
        # after deletion, so instead scan for notesSlides that point back to
        # this slide via their own rels.
        # Heuristic: a notesSlide whose "slide" rel points to slide_path is
        # an orphan now.
        for p in list(pptx.list_paths()):
            if not (p.startswith("ppt/notesSlides/") and p.endswith(".xml")):
                continue
            notes_rels = pptx.get_rels(p)
            slide_rel = notes_rels.find_by_type("slide")
            if not slide_rel:
                continue
            target = notes_rels.resolve_target(slide_rel[0])
            if target == slide_path:
                size = self._size_of(pptx, p)
                pptx.delete_part(p)
                self.report.bytes_freed += size
