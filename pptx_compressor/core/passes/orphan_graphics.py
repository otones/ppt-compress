"""Pass 5: remove orphan graphics from slide masters / layouts.

A "orphan" graphic is a <p:sp> / <p:pic> / <p:graphicFrame> / <p:grpSp>
inside a master or layout that is *not* a placeholder (<p:nvSpPr><p:nvPr>
without <p:ph>) AND carries no text. Such decorative leftovers inflate
masters without serving layout purpose. We drop them.

Conservative: we never remove shapes that contain text, charts, tables,
or that are placeholders.
"""

from __future__ import annotations

from ..pptx import PptxFile, qn
from .base import CompressionPass


# Shape tags we consider "graphics" for orphan detection.
SHAPE_TAGS = {
    qn("p", "sp"),
    qn("p", "pic"),
    qn("p", "graphicFrame"),
    qn("p", "grpSp"),
    qn("p", "cxnSp"),
}


class OrphanMasterGraphicsPass(CompressionPass):
    id = "remove_orphan_master_graphics"
    label = "删除母版孤儿图形"

    def run(self, pptx: PptxFile) -> PassReport:
        if not self.report.enabled:
            return self.report
        self.report.ran = True

        targets = [
            p for p in pptx.list_paths()
            if (p.startswith("ppt/slideMasters/slideMaster")
                or p.startswith("ppt/slideLayouts/slideLayout"))
            and p.endswith(".xml")
        ]

        for path in targets:
            part = pptx.get_part(path)
            if part is None:
                continue
            removed = self._strip_orphans(part.root)
            if removed > 0:
                before = len(part.data)
                pptx.commit_part_tree(path)
                after = len(part.data)
                saved = max(0, before - after)
                self.report.bytes_freed += saved
                self.report.items_affected += removed
                self.report.add_detail(
                    f"{path}: 移除 {removed} 个母版孤儿图形(节省 {saved} 字节)"
                )
        return self.report

    def _strip_orphans(self, root) -> int:
        removed = 0
        # Look inside <p:cSld><p:spTree>.
        sp_tree = root.find(".//" + qn("p", "spTree"))
        if sp_tree is None:
            return 0
        for shape in list(sp_tree):
            if shape.tag not in SHAPE_TAGS:
                continue
            if self._is_placeholder(shape):
                continue
            if self._has_text(shape):
                continue
            if self._has_table_chart_diagram(shape):
                continue
            sp_tree.remove(shape)
            removed += 1
        return removed

    def _is_placeholder(self, shape) -> bool:
        # nvSpPr/nvPr/ph present => placeholder.
        for tag in (qn("p", "nvSpPr"), qn("p", "nvPicPr"),
                    qn("p", "nvGraphicFramePr"), qn("p", "nvGrpSpPr"),
                    qn("p", "nvCxnSpPr")):
            nv = shape.find(tag)
            if nv is None:
                continue
            nv_pr = nv.find(qn("p", "nvPr"))
            if nv_pr is not None and nv_pr.find(qn("p", "ph")) is not None:
                return True
        return False

    def _has_text(self, shape) -> bool:
        # Any <a:t> with non-empty text.
        for t in shape.iter(qn("a", "t")):
            if (t.text or "").strip():
                return True
        return False

    def _has_table_chart_diagram(self, shape) -> bool:
        # graphicFrame with <a:tbl>/<c:chart>/<dgm:...> etc. — keep.
        for tag in (qn("a", "tbl"), qn("a", "graphicData")):
            if shape.find(".//" + tag) is not None:
                return True
        return False
