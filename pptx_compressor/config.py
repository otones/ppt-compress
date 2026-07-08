"""Compression configuration: per-pass toggles and tunable parameters."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict


@dataclass
class ImageOptions:
    """Image recompression parameters."""

    # Images larger than this (on the long edge, in px) get downscaled.
    max_dimension: int = 1920
    # JPEG quality (1-95) for photographic images.
    jpeg_quality: int = 80
    # If a PNG is opaque and larger than the JPEG equivalent would be, convert to JPEG.
    allow_png_to_jpeg: bool = True
    # Discard DPI/metadata chunks (EXIF, ICCP, etc.) from embedded images.
    strip_metadata: bool = True


@dataclass
class Settings:
    """User-facing settings. Each pass can be enabled/disabled independently."""

    # --- Pass toggles (US-3) ---
    compress_images: bool = True
    remove_hidden_slides: bool = True
    remove_hidden_animation_paths: bool = True
    remove_unused_fonts: bool = True
    remove_orphan_master_graphics: bool = True
    remove_thumbnails: bool = True
    remove_orphan_media: bool = True

    # --- Image pass options ---
    image: ImageOptions = field(default_factory=ImageOptions)

    # --- Output naming (US-4) ---
    # Suffix strategy: "suffix" -> name_compressed.pptx
    #                  "overwrite" -> overwrite original (with .bak backup)
    #                  "custom" -> use output_path
    output_strategy: str = "suffix"
    output_suffix: str = "_compressed"
    # When strategy == "overwrite", keep a backup next to the original.
    keep_backup_on_overwrite: bool = True

    # --- Safety ---
    # Always keep the original file untouched unless strategy == "overwrite".
    verify_zip_after_write: bool = True

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d

    @classmethod
    def default(cls) -> "Settings":
        return cls()

    @classmethod
    def from_dict(cls, d: Dict) -> "Settings":
        img = d.pop("image", {}) if "image" in d else {}
        s = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        if img:
            s.image = ImageOptions(
                **{k: v for k, v in img.items() if k in ImageOptions.__dataclass_fields__}
            )
        return s


# Ordered list of (attribute_name, human_label, description) for UI/CLI display.
PASS_DESCRIPTIONS = [
    ("compress_images", "压缩图片", "重新编码高分辨率图片,降采样并转 JPEG"),
    ("remove_hidden_slides", "删除隐藏幻灯片", "移除 show=\"0\" 的备用幻灯片及其引用"),
    ("remove_hidden_animation_paths", "清理隐藏动画路径", "移除被禁用动画残留的路径节点数据"),
    ("remove_unused_fonts", "删除未使用嵌入字体", "清理嵌入但未被任何文本引用的字体子集"),
    ("remove_orphan_master_graphics", "删除母版孤儿图形", "移除母版/版式中无引用的残留图形"),
    ("remove_thumbnails", "删除缩略图", "移除 docProps/thumbnail.jpeg 及其引用"),
    ("remove_orphan_media", "删除孤儿媒体", "移除 ppt/media/ 下未被任何 blip 引用的文件"),
]
