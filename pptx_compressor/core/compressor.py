"""Main compressor orchestrator.

Loads a .pptx, runs each enabled pass in order, writes the result to the
configured output path, and returns a CompressionReport.
"""

from __future__ import annotations

import os
import shutil
from typing import List, Optional, Type

from ..config import Settings
from .pptx import PptxFile
from .passes.base import CompressionPass, PassReport
from .passes.image_compression import ImageCompressionPass
from .passes.hidden_slides import HiddenSlidesPass
from .passes.animation_paths import AnimationPathsPass
from .passes.unused_fonts import UnusedFontsPass
from .passes.orphan_graphics import OrphanMasterGraphicsPass
from .passes.thumbnails import ThumbnailsPass
from .passes.orphan_media import OrphanMediaPass
from .report import CompressionReport


# Pass execution order matters:
#  - delete hidden slides FIRST (frees media via orphan pass later)
#  - thumbnails / fonts / master-graphics are independent
#  - animation cleanup is independent
#  - image compression
#  - orphan media LAST so it can reap anything unlinked by prior passes
PASS_ORDER: List[Type[CompressionPass]] = [
    HiddenSlidesPass,
    ThumbnailsPass,
    UnusedFontsPass,
    OrphanMasterGraphicsPass,
    AnimationPathsPass,
    ImageCompressionPass,
    OrphanMediaPass,
]


def compute_output_path(input_path: str, settings: Settings,
                        output_override: Optional[str] = None) -> str:
    """Resolve the destination file path according to settings/override."""
    if output_override:
        return output_override
    d, name = os.path.split(input_path)
    base, ext = os.path.splitext(name)
    if ext.lower() != ".pptx":
        ext = ".pptx"
    strat = settings.output_strategy
    if strat == "overwrite":
        return input_path
    if strat == "suffix":
        return os.path.join(d, f"{base}{settings.output_suffix}{ext}")
    if strat == "custom":
        return os.path.join(d, f"{base}{settings.output_suffix}{ext}")
    return os.path.join(d, f"{base}{settings.output_suffix}{ext}")


def compress(input_path: str,
             settings: Optional[Settings] = None,
             output_override: Optional[str] = None) -> CompressionReport:
    """Compress a single .pptx file. Returns a CompressionReport."""
    settings = settings or Settings.default()
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)

    output_path = compute_output_path(input_path, settings, output_override)
    input_size = os.path.getsize(input_path)

    # Load the archive into memory (original untouched).
    pptx = PptxFile(input_path)

    # Backup if overwriting.
    backup_path: Optional[str] = None
    if settings.output_strategy == "overwrite" and settings.keep_backup_on_overwrite:
        backup_path = input_path + ".bak"
        shutil.copy2(input_path, backup_path)

    reports: List[PassReport] = []
    for pass_cls in PASS_ORDER:
        p = pass_cls(settings)
        try:
            r = p.run(pptx)
        except Exception as e:  # noqa: BLE001 - a pass failing shouldn't abort others
            r = PassReport(name=p.label, enabled=p.report.enabled, ran=True)
            r.add_detail(f"⚠ 该 pass 执行出错已跳过:{e}")
        reports.append(r)

    # Write the new archive.
    # If output == input (overwrite) we already backed up; write to temp then
    # atomically replace to avoid corrupting on failure.
    if output_path == input_path:
        tmp = input_path + ".tmp"
        pptx.save(tmp)
        os.replace(tmp, input_path)
    else:
        pptx.save(output_path)

    output_size = os.path.getsize(output_path)

    report = CompressionReport(
        input_path=input_path,
        output_path=output_path,
        input_size=input_size,
        output_size=output_size,
        passes=reports,
    )
    return report
