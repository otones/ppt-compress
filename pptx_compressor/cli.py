"""Command-line interface: `pptx-compress <file.pptx> [options]`.

Implements US-5 (P0): compress to <name>_compressed.pptx in the same dir.
"""

from __future__ import annotations

import sys

import click

from .config import Settings
from .core.compressor import compress


@click.command(
    name="pptx-compress",
    help="离线压缩 .pptx 文件(图片/隐藏页/孤儿媒体/未用字体/缩略图等)。",
)
@click.argument("file", type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option("-o", "--output", "output", default=None,
              help="输出文件路径;默认 <name>_compressed.pptx 放在同目录。")
@click.option("--strategy", type=click.Choice(["suffix", "overwrite", "custom"]),
              default=None, help="输出命名策略。")
@click.option("--suffix", default=None, help="suffix 策略下使用的后缀(默认 _compressed)。")
@click.option("--max-dimension", type=int, default=None, help="图片长边最大像素(默认 1920)。")
@click.option("--jpeg-quality", type=int, default=None, help="JPEG 质量 1-95(默认 80)。")
@click.option("--detail/--no-detail", default=True, help="是否打印分项详情。")
@click.option("--compress-images/--no-compress-images", default=None, help="启用/禁用:压缩图片。")
@click.option("--remove-hidden-slides/--no-remove-hidden-slides", default=None, help="启用/禁用:删除隐藏幻灯片。")
@click.option("--remove-hidden-animation-paths/--no-remove-hidden-animation-paths", default=None, help="启用/禁用:清理隐藏动画路径。")
@click.option("--remove-unused-fonts/--no-remove-unused-fonts", default=None, help="启用/禁用:删除未使用嵌入字体。")
@click.option("--remove-orphan-master-graphics/--no-remove-orphan-master-graphics", default=None, help="启用/禁用:删除母版孤儿图形。")
@click.option("--remove-thumbnails/--no-remove-thumbnails", default=None, help="启用/禁用:删除缩略图。")
@click.option("--remove-orphan-media/--no-remove-orphan-media", default=None, help="启用/禁用:删除孤儿媒体。")
def main(file, output, strategy, suffix, max_dimension, jpeg_quality, detail,
         compress_images, remove_hidden_slides, remove_hidden_animation_paths,
         remove_unused_fonts, remove_orphan_master_graphics, remove_thumbnails,
         remove_orphan_media):
    settings = Settings.default()
    if strategy:
        settings.output_strategy = strategy
    if suffix:
        settings.output_suffix = suffix
    if max_dimension:
        settings.image.max_dimension = max_dimension
    if jpeg_quality:
        settings.image.jpeg_quality = jpeg_quality

    toggles = {
        "compress_images": compress_images,
        "remove_hidden_slides": remove_hidden_slides,
        "remove_hidden_animation_paths": remove_hidden_animation_paths,
        "remove_unused_fonts": remove_unused_fonts,
        "remove_orphan_master_graphics": remove_orphan_master_graphics,
        "remove_thumbnails": remove_thumbnails,
        "remove_orphan_media": remove_orphan_media,
    }
    for attr, val in toggles.items():
        if val is not None:
            setattr(settings, attr, val)

    if not file.lower().endswith(".pptx"):
        click.echo("⚠ 仅支持 .pptx 格式(不支持旧版 .ppt)。", err=True)
        sys.exit(2)

    click.echo(f"压缩中:{file}")
    try:
        report = compress(file, settings, output_override=output)
    except FileNotFoundError as e:
        click.echo(f"错误:文件不存在 {e}", err=True)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        click.echo(f"压缩失败:{e}", err=True)
        sys.exit(1)

    click.echo(report.summary_line())
    click.echo(f"输出:{report.output_path}")
    if detail:
        click.echo("")
        for line in report.detail_lines()[1:]:
            click.echo(line)


if __name__ == "__main__":
    main()
