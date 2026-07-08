"""End-to-end smoke test: build a synthetic .pptx and compress it.

Run:  python tests/test_compress_e2e.py
"""

from __future__ import annotations

import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from pptx_compressor.config import Settings
from pptx_compressor.core.compressor import compress
from pptx_compressor.core.pptx import PptxFile


def _png_bytes(w: int, h: int, color=(255, 0, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(w: int, h: int, color=(0, 0, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def build_sample_pptx(path: str) -> None:
    """Build a minimal but valid .pptx with hidden slide, orphan media,
    thumbnail, and an oversized image."""
    parts = {}

    parts["[Content_Types].xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Default Extension="jpeg" ContentType="image/jpeg"/>'
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
        '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        '<Override PartName="/ppt/slides/slide2.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        '<Override PartName="/docProps/thumbnail.jpeg" ContentType="image/jpeg"/>'
        '</Types>'
    ).encode()

    parts["_rels/.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail" Target="docProps/thumbnail.jpeg"/>'
        '</Relationships>'
    ).encode()

    parts["docProps/thumbnail.jpeg"] = _jpeg_bytes(800, 600)

    # presentation.xml references slide1 (visible) + slide2 (hidden).
    parts["ppt/presentation.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'saveSubsetFonts="1">'
        '<p:sldIdLst><p:sldId id="256" r:id="rId1"/>'
        '<p:sldId id="257" r:id="rId2"/></p:sldIdLst>'
        '</p:presentation>'
    ).encode()

    parts["ppt/_rels/presentation.xml.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide2.xml"/>'
        '</Relationships>'
    ).encode()

    # slide1: visible, references image1 (a 4000x3000 oversized PNG).
    parts["ppt/slides/slide1.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:spTree>'
        '<p:pic><p:nvPicPr><p:cNvPr id="4" name="Pic 1"/>'
        '<p:cNvPicPr/><p:nvPr/></p:nvPicPr>'
        '<p:blipFill><a:blip r:embed="rId1"/></p:blipFill>'
        '<p:spPr/></p:pic>'
        '</p:spTree></p:cSld>'
        '</p:sld>'
    ).encode()

    parts["ppt/slides/_rels/slide1.xml.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>'
        '</Relationships>'
    ).encode()

    # slide2: HIDDEN (show="0").
    parts["ppt/slides/slide2.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" show="0">'
        '<p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr/>'
        '<p:nvPr/></p:nvSpPr><p:spPr/><p:txBody/></p:sp></p:spTree></p:cSld>'
        '</p:sld>'
    ).encode()

    # Oversized referenced image.
    parts["ppt/media/image1.png"] = _png_bytes(4000, 3000)
    # Orphan media (NOT referenced anywhere).
    parts["ppt/media/image2.png"] = _png_bytes(2000, 1500, color=(0, 255, 0))

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in parts.items():
            zf.writestr(name, data)


def main() -> int:
    src = "/tmp/sample.pptx"
    build_sample_pptx(src)
    src_size = os.path.getsize(src)
    print(f"原始大小:{src_size} 字节")

    settings = Settings.default()
    # Force aggressive downscale for the test.
    settings.image.max_dimension = 1280
    report = compress(src, settings)

    out_size = os.path.getsize(report.output_path)
    print(report.summary_line())

    # Assertions.
    pf = PptxFile(report.output_path)
    paths = set(pf.list_paths())
    ok = True

    # 1. Hidden slide2 removed.
    if "ppt/slides/slide2.xml" in paths:
        print("✗ FAIL: 隐藏幻灯片 slide2 未被删除")
        ok = False
    else:
        print("✓ 隐藏幻灯片 slide2 已删除")
    # 2. Visible slide1 kept.
    if "ppt/slides/slide1.xml" not in paths:
        print("✗ FAIL: 可见幻灯片 slide1 被误删")
        ok = False
    else:
        print("✓ 可见幻灯片 slide1 保留")
    # 3. Thumbnail removed.
    if "docProps/thumbnail.jpeg" in paths:
        print("✗ FAIL: 缩略图未被删除")
        ok = False
    else:
        print("✓ 缩略图已删除")
    # 4. Orphan image2 removed.
    if "ppt/media/image2.png" in paths:
        print("✗ FAIL: 孤儿媒体 image2 未被删除")
        ok = False
    else:
        print("✓ 孤儿媒体 image2 已删除")
    # 5. Referenced image1 kept.
    if "ppt/media/image1.png" not in paths:
        print("✗ FAIL: 被引用的 image1 被误删")
        ok = False
    else:
        print("✓ 被引用的 image1 保留")
    # 6. Output smaller.
    if out_size >= src_size:
        print(f"✗ FAIL: 输出未变小({out_size} >= {src_size})")
        ok = False
    else:
        print(f"✓ 输出变小:{src_size} → {out_size}")

    print("\n--- 分项详情 ---")
    for line in report.detail_lines():
        print(line)

    print("\n结果:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
