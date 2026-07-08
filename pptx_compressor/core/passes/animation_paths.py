"""Pass 3: clean up hidden animation path residue.

PowerPoint sometimes leaves <p:timing> trees containing motion path
<animMotion> / <animVar> data for animations that have been disabled.
We strip <p:timing> branches that contain *only* disabled-effect entries,
and remove empty <p:timing> wrappers entirely.

This is conservative: we never touch animation *timing/sequencing* — only
orphan motion-path geometry under disabled <par>/<seq> nodes.
"""

from __future__ import annotations

from ..pptx import PptxFile, qn
from .base import CompressionPass


class AnimationPathsPass(CompressionPass):
    id = "remove_hidden_animation_paths"
    label = "清理隐藏动画路径"

    def run(self, pptx: PptxFile) -> PassReport:
        if not self.report.enabled:
            return self.report
        self.report.ran = True

        # Scan every slide (and slideLayout / slideMaster) for timing trees.
        targets = [
            p for p in pptx.list_paths()
            if (p.startswith("ppt/slides/slide")
                or p.startswith("ppt/slideLayouts/slideLayout")
                or p.startswith("ppt/slideMasters/slideMaster"))
            and p.endswith(".xml")
        ]

        for path in targets:
            part = pptx.get_part(path)
            if part is None:
                continue
            before = len(part.data)
            removed = self._clean_timing(part.root)
            if removed > 0:
                pptx.commit_part_tree(path)
                after = len(part.data)
                saved = max(0, before - after)
                self.report.bytes_freed += saved
                self.report.items_affected += removed
                self.report.add_detail(
                    f"{path}: 移除 {removed} 个残留动画路径节点(节省 {saved} 字节)"
                )
        return self.report

    def _clean_timing(self, root) -> int:
        """Remove disabled-effect motion-path residue. Returns count removed."""
        removed = 0
        # Find all <p:timing> elements.
        for timing in list(root.iter(qn("p", "timing"))):
            # Walk for animMotion / path elements under disabled effects.
            # An effect is "disabled" when its <p:cBhvr> has
            # <p:cTn display="0" ...> OR the parent <p:par>/<p:seq> is
            # marked presetClass="path" with no actual target shape.
            for anim in list(timing.iter(qn("a", "animMotion"))):
                parent_cTn = self._find_ancestor(anim, qn("p", "cTn"))
                if parent_cTn is not None and parent_cTn.get("display") == "0":
                    # Disabled animation path -> drop the animMotion element.
                    self._remove_element(anim)
                    removed += 1
            # If timing now has no animMotion / animEffect / set, drop it.
            has_active = (
                timing.find(".//" + qn("a", "animMotion")) is not None
                or timing.find(".//" + qn("p", "animEffect")) is not None
                or timing.find(".//" + qn("p", "set")) is not None
                or timing.find(".//" + qn("a", "anim")) is not None
                or timing.find(".//" + qn("a", "animEffect")) is not None
            )
            if not has_active:
                self._remove_element(timing)
                removed += 1
        return removed

    def _find_ancestor(self, el, tag):
        parent = el.getparent()
        while parent is not None:
            if parent.tag == tag:
                return parent
            parent = parent.getparent()
        return None

    def _remove_element(self, el) -> None:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)
