# PPTX 压缩器

离线 PPTX 文件压缩工具，无需联网、无需上传，在本地对 `.pptx` 文件进行多通道压缩，有效缩减文件体积。提供 PySide6 图形界面（GUI）和命令行（CLI）两种使用方式，支持打包为 macOS `.app` 应用。

## 功能特性

通过解析 OOXML（PPTX 本质是 ZIP 归档）并在内存中执行七个独立的压缩通道，实现体积缩减：

| 压缩通道 | 说明 |
|----------|------|
| 压缩图片 | 使用 Pillow 对 `ppt/media/` 下图片重新编码，按长边降采样并转 JPEG，剥离 EXIF/ICC 等元数据 |
| 删除隐藏幻灯片 | 移除 `show="0"` 的备用幻灯片及其引用、关联的备注页 |
| 清理隐藏动画路径 | 移除被禁用动画（`display="0"`）残留的 `animMotion` 路径节点及空 `timing` 包装 |
| 删除未使用嵌入字体 | 清理嵌入但未被任何文本引用的字体子集 |
| 删除母版孤儿图形 | 移除母版/版式中非占位符、无文本、无图表的装饰性残留图形 |
| 删除缩略图 | 移除 `docProps/thumbnail.*` 及其关系引用 |
| 删除孤儿媒体 | 移除 `ppt/media/` 下未被任何 blip 引用的文件（始终保留视频文件） |

每个通道均可独立开关，压缩过程在内存中完成，**原始文件不会被修改**（覆盖策略下会自动创建 `.bak` 备份）。

## 安装

### 环境要求

- Python >= 3.9
- macOS（GUI 与 `.app` 打包主要面向 macOS）

### 从源码安装

```bash
git clone <repo-url>
cd ppt-compress
pip install -r requirements.txt
pip install -e .
```

依赖：Pillow、lxml、click、PySide6

## 使用方式

### 图形界面（GUI）

```bash
python -m pptx_compressor
```

或直接运行启动器：

```bash
python run_gui.py
```

操作流程：拖拽或点击选择 `.pptx` 文件 → 点击「压缩」→ 查看压缩结果与分项详情。可在「设置」中调整各通道开关、图片压缩参数及输出命名策略，设置会持久化到 `~/.pptx_compressor_settings.json`。

### 命令行（CLI）

```bash
pptx-compress <file.pptx> [options]
```

常用选项：

| 选项 | 说明 |
|------|------|
| `-o, --output <path>` | 指定输出文件路径 |
| `--strategy <suffix\|overwrite\|custom>` | 输出命名策略（默认 suffix） |
| `--suffix <text>` | suffix 策略下使用的后缀（默认 `_compressed`） |
| `--max-dimension <int>` | 图片长边最大像素（默认 1920） |
| `--jpeg-quality <int>` | JPEG 质量 1-95（默认 80） |
| `--detail / --no-detail` | 是否打印分项详情（默认开启） |
| `--compress-images / --no-compress-images` | 启用/禁用：压缩图片 |
| `--remove-hidden-slides / --no-remove-hidden-slides` | 启用/禁用：删除隐藏幻灯片 |
| `--remove-hidden-animation-paths / --no-remove-hidden-animation-paths` | 启用/禁用：清理隐藏动画路径 |
| `--remove-unused-fonts / --no-remove-unused-fonts` | 启用/禁用：删除未使用嵌入字体 |
| `--remove-orphan-master-graphics / --no-remove-orphan-master-graphics` | 启用/禁用：删除母版孤儿图形 |
| `--remove-thumbnails / --no-remove-thumbnails` | 启用/禁用：删除缩略图 |
| `--remove-orphan-media / --no-remove-orphan-media` | 启用/禁用：删除孤儿媒体 |

示例：

```bash
# 默认压缩，输出到同目录 name_compressed.pptx
pptx-compress presentation.pptx

# 自定义输出路径与图片参数
pptx-compress presentation.pptx -o out.pptx --max-dimension 1280 --jpeg-quality 70

# 仅压缩图片，关闭其他通道
pptx-compress presentation.pptx --no-remove-hidden-slides --no-remove-thumbnails --no-remove-orphan-media
```

## 打包为 macOS 应用

```bash
./build_app.sh
```

脚本会创建虚拟环境、安装依赖、通过 py2app 构建 `dist/PPTXCompressor.app`。

首次打开若被 Gatekeeper 拦截，执行：

```bash
xattr -dr com.apple.quarantine dist/PPTXCompressor.app
```

## 输出命名策略

| 策略 | 行为 |
|------|------|
| `suffix`（默认） | 输出为 `<name>_compressed.pptx`，放在原文件同目录 |
| `overwrite` | 覆盖原文件，自动生成 `.bak` 备份（可配置关闭） |
| `custom` | 使用 `-o` 指定的路径 |

## 项目结构

```
pptx_compressor/
├── __init__.py
├── __main__.py            # 模块入口，启动 GUI
├── cli.py                 # Click 命令行界面
├── config.py              # 配置：通道开关与可调参数
├── gui.py                 # PySide6 图形界面
└── core/
    ├── compressor.py      # 主编排器，按序执行各压缩通道
    ├── pptx.py            # PPTX 归封装（OOXML ZIP 读写 API）
    ├── report.py          # 压缩报告聚合
    └── passes/
        ├── base.py                # 压缩通道基类
        ├── image_compression.py   # 图片重编码
        ├── hidden_slides.py       # 隐藏幻灯片删除
        ├── animation_paths.py     # 隐藏动画路径清理
        ├── unused_fonts.py        # 未使用嵌入字体删除
        ├── orphan_graphics.py     # 母版孤儿图形删除
        ├── thumbnails.py          # 缩略图删除
        └── orphan_media.py        # 孤儿媒体删除
```

## 测试

```bash
python tests/test_compress_e2e.py
```

端到端测试会构建一个含隐藏页、孤儿媒体、缩略图及超大图片的合成 `.pptx`，执行压缩并验证各通道效果。

## 许可证

MIT
