"""Pass 6: remove auto-saved thumbnails.

Removes docProps/thumbnail.jpeg (and any other docProps thumbnail parts)
plus its relationship in _rels/.rels and its content-type entry.
"""

from __future__ import annotations

from ..pptx import PptxFile, qn
from .base import CompressionPass


class ThumbnailsPass(CompressionPass):
    id = "remove_thumbnails"
    label = "删除缩略图"

    # Parts to remove outright.
    THUMB_PARTS = {
        "docProps/thumbnail.jpeg",
        "docProps/thumbnail.png",
        "docProps/thumbnail.gif",
        "docProps/thumbnail.bmp",
    }

    def run(self, pptx: PptxFile) -> PassReport:
        if not self.report.enabled:
            return self.report
        self.report.ran = True

        for path in list(pptx.list_paths()):
            if path not in self.THUMB_PARTS and not path.startswith("docProps/thumbnail"):
                continue
            size = self._size_of(pptx, path)
            # Remove content-type override.
            pptx.remove_content_type_override(path)
            # Remove rels entry from _rels/.rels that targets this part.
            root_rels = pptx.get_rels("")  # _rels/.rels
            for rel in list(root_rels.relationships):
                if root_rels.resolve_target(rel) == path:
                    root_rels.remove_relationship(rel.id)
            pptx.save_rels(root_rels)
            # Drop the part itself.
            pptx.delete_part(path)
            self.report.bytes_freed += size
            self.report.items_affected += 1
            self.report.add_detail(f"删除缩略图 {path}({size} 字节)")

        return self.report
