#!/usr/bin/env bash
# Build the macOS .app bundle for PPTX 压缩器,并做体积瘦身。
#
#   ./build_app.sh
#
# 使用 uv 创建虚拟环境并指定 Python 3.12,不依赖系统 Python 版本。
# uv 会自动下载所需 Python,首次运行需联网。
#
# 产出 dist/PPTXCompressor.app。在 macOS(Apple Silicon & Intel)测试通过。
# 目标:最终 .app 体积 < 100MB。
set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="PPTXCompressor"
APP="dist/${APP_NAME}.app"

# py2app 与 .app 打包仅在 macOS 上可用。
if [ "$(uname -s)" != "Darwin" ]; then
    echo "✗ 此脚本必须在 macOS 上运行(当前系统:$(uname -s))。" >&2
    echo "  py2app 仅在 PyPI 提供 macOS wheel,在 Linux/Windows 上无法安装。" >&2
    echo "  请在 Mac 上执行:./build_app.sh" >&2
    exit 1
fi

# --- 使用 uv 管理 venv 与 Python 版本 ---
# py2app 0.28 要求 Python >= 3.10;3.13 支持尚不稳定,固定使用 3.12。
# uv 会自动下载对应版本的 Python,无需系统预装。
PY_VERSION="3.12"

# 确保 uv 可用:优先用 PATH 中的 uv;否则尝试 brew 安装路径;都没有就安装。
if ! command -v uv >/dev/null 2>&1; then
    if [ -x "/opt/homebrew/bin/uv" ]; then
        export PATH="/opt/homebrew/bin:$PATH"
    elif [ -x "/usr/local/bin/uv" ]; then
        export PATH="/usr/local/bin:$PATH"
    else
        echo "==> 未检测到 uv,正在安装 uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # 安装后 uv 通常位于 ~/.local/bin
        export PATH="$HOME/.local/bin:$PATH"
    fi
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "✗ uv 安装失败,请手动安装:curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

echo "==> uv 版本:$(uv --version)"

# 用 uv 创建指定 Python 3.12 的虚拟环境。
# uv 会自动下载 Python 3.12(若本地没有),完全不依赖系统 Python 版本。
echo "==> 创建虚拟环境 (./.venv-build)  [Python $PY_VERSION]"
uv venv --python "$PY_VERSION" .venv-build

# shellcheck disable=SC1091
source .venv-build/bin/activate

# uv 的 pip 速度更快,且能正确解析现代 wheel metadata,避免旧版 pip
# 报 "No matching distribution found" 的问题。
echo "==> 安装构建依赖"
# 关键:锁定 setuptools<81。setuptools 81+ 在检测到 pyproject.toml [project]
# 表后,会拒绝 py2app 依赖的旧式 setup() 调用语义,报
# "error: install_requires is no longer supported"。py2app 社区通用解法
# 是构建时固定 setuptools<81。
uv pip install --upgrade "pip<81" "setuptools<81" "wheel"
uv pip install -r requirements.txt py2app
uv pip install -e .

echo "==> 当前环境:"
python --version
python -m pip --version

echo "==> 清理上次构建产物"
rm -rf build dist

echo "==> 运行 py2app(已配置 strip + 排除大量 Qt 子模块)"
python setup.py py2app

if [ ! -d "$APP" ]; then
    echo "✗ 构建失败,请检查上方日志" >&2
    exit 1
fi

before_bytes=$(du -sk "$APP" | awk '{print $1}')
echo "==> py2app 产出体积:${before_bytes} KB"

# =========================================================================
# 瘦身阶段:setup.py 的 packages:["PySide6"] 会把整个 PySide6 目录(含
# Qt 全部框架)整包拷进 .app,excludes 对此不生效。真正的大头是
# PySide6/Qt/lib/*.framework —— QtWebEngineCore 一个就 ~300MB。这里用
# 白名单方式:只保留 QtWidgets 应用必需的框架,其余全删。
# =========================================================================
echo "==> 瘦身:删除冗余 Qt 资源"

# PySide6 资源位于 .app/Contents/Resources/lib/python*/site-packages/PySide6/
PYSIDE6_DIR=$(find "$APP/Contents/Resources" -type d -name PySide6 2>/dev/null | head -1 || true)

if [ -n "$PYSIDE6_DIR" ] && [ -d "$PYSIDE6_DIR" ]; then
    echo "   PySide6 目录:$PYSIDE6_DIR"

    # --- A) Qt 框架白名单(QtWidgets 应用最小依赖)---
    # 保留:QtCore / QtGui / QtWidgets(核心),QtOpenGL(QtGui 渲染依赖),
    #       QtSvg / QtDBus / QtNetwork(平台插件可能需要,体积都很小)。
    QT_LIB="$PYSIDE6_DIR/Qt/lib"
    KEEP_FW="QtCore QtGui QtWidgets QtOpenGL QtSvg QtDBus QtNetwork"
    if [ -d "$QT_LIB" ]; then
        echo "   Qt 框架目录:$QT_LIB"
        # 删除所有 .framework,除了白名单
        for fw in "$QT_LIB"/*.framework; do
            [ -d "$fw" ] || continue
            name=$(basename "$fw" .framework)
            case " $KEEP_FW " in
                *" $name "*) echo "   保留框架:$name" ;;
                *) rm -rf "$fw"; echo "   删除框架:$name" ;;
            esac
        done
        # 删除独立的 .dylib / .so / 静态库 / 链接描述文件
        rm -f "$QT_LIB"/*.dylib "$QT_LIB"/*.so 2>/dev/null || true
        rm -f "$QT_LIB"/*.a "$QT_LIB"/*.prl "$QT_LIB"/*.la "$QT_LIB"/*.cmake 2>/dev/null || true
        # 删除 CMake / pkgconfig 元数据
        rm -rf "$QT_LIB/cmake" "$QT_LIB/pkgconfig" "$QT_LIB/metatypes" 2>/dev/null || true
        # 删除 QtWebEngineProcess 及其 Helper(若存在)
        rm -rf "$QT_LIB/QtWebEngineCore.framework" 2>/dev/null || true
        find "$QT_LIB" -name "QtWebEngineProcess*" -delete 2>/dev/null || true
    fi

    # --- B) Qt 资源目录(WebEngine 资源 icudtl.dat/locales ~数十 MB)---
    rm -rf "$PYSIDE6_DIR/Qt/resources" 2>/dev/null || true
    rm -rf "$PYSIDE6_DIR/Qt/translations" 2>/dev/null || true
    rm -rf "$PYSIDE6_DIR/Qt/qml" 2>/dev/null || true

    # --- C) PySide6 顶层资源 ---
    rm -rf "$PYSIDE6_DIR/qml" 2>/dev/null || true
    rm -rf "$PYSIDE6_DIR/translations" 2>/dev/null || true
    rm -rf "$PYSIDE6_DIR/examples" 2>/dev/null || true
    rm -rf "$PYSIDE6_DIR/include" 2>/dev/null || true
    rm -rf "$PYSIDE6_DIR/Qt/include" 2>/dev/null || true
    rm -rf "$PYSIDE6_DIR/Qt/mkspecs" 2>/dev/null || true

    # --- D) 删除被排除子模块的 .so(防止漏网)---
    rm -f "$PYSIDE6_DIR"/QtWebEngine*.so \
          "$PYSIDE6_DIR"/QtQml*.so \
          "$PYSIDE6_DIR"/QtQuick*.so \
          "$PYSIDE6_DIR"/Qt3D*.so \
          "$PYSIDE6_DIR"/QtCharts*.so \
          "$PYSIDE6_DIR"/QtDataVisualization*.so \
          "$PYSIDE6_DIR"/QtPdf*.so \
          "$PYSIDE6_DIR"/QtMultimedia*.so \
          "$PYSIDE6_DIR"/QtBluetooth*.so \
          "$PYSIDE6_DIR"/QtSensors*.so \
          "$PYSIDE6_DIR"/QtPositioning*.so \
          "$PYSIDE6_DIR"/QtLocation*.so \
          "$PYSIDE6_DIR"/QtSerialBus*.so \
          "$PYSIDE6_DIR"/QtSerialPort*.so \
          "$PYSIDE6_DIR"/QtSql*.so \
          "$PYSIDE6_DIR"/QtTest*.so \
          "$PYSIDE6_DIR"/QtXml*.so \
          "$PYSIDE6_DIR"/QtPrintSupport*.so \
          "$PYSIDE6_DIR"/QtDesigner*.so \
          "$PYSIDE6_DIR"/QtUiTools*.so \
          "$PYSIDE6_DIR"/QtHelp*.so \
          "$PYSIDE6_DIR"/QtScxml*.so \
          "$PYSIDE6_DIR"/QtStateMachine*.so \
          "$PYSIDE6_DIR"/QtRemoteObjects*.so \
          "$PYSIDE6_DIR"/QtWebChannel*.so \
          "$PYSIDE6_DIR"/QtWebSockets*.so \
          "$PYSIDE6_DIR"/QtNfc*.so \
          "$PYSIDE6_DIR"/QtTextToSpeech*.so \
          "$PYSIDE6_DIR"/QtConcurrent*.so 2>/dev/null || true

    # --- E) Qt 插件:只保留 platforms / styles / imageformats ---
    for plugdir in "$PYSIDE6_DIR/plugins" "$PYSIDE6_DIR/Qt/plugins"; do
        [ -d "$plugdir" ] || continue
        find "$plugdir" -maxdepth 1 -mindepth 1 -type d \
            ! -name platforms \
            ! -name styles \
            ! -name imageformats \
            -exec rm -rf {} +
        # imageformats 里只留 png/jpg/gif/bmp/ico,删 svg/tiff/pdf/webp 等
        if [ -d "$plugdir/imageformats" ]; then
            rm -f "$plugdir/imageformats"/libqsvg* \
                  "$plugdir/imageformats"/libqtiff* \
                  "$plugdir/imageformats"/libqpdf* \
                  "$plugdir/imageformats"/libqtga* \
                  "$plugdir/imageformats"/libqwbmp* \
                  "$plugdir/imageformats"/libqwebp* \
                  "$plugdir/imageformats"/libqheif* \
                  "$plugdir/imageformats"/libqjp2* 2>/dev/null || true
        fi
    done
fi

# --- F) 全局清理:.pyi 存根 / .py 源码(py2app 已编译为 .pyc)---
find "$APP/Contents/Resources" -name "*.pyi" -delete 2>/dev/null || true
find "$APP/Contents/Resources" -name "*.py" -path "*/site-packages/*" -delete 2>/dev/null || true

# --- G) strip 所有 Mach-O 二进制调试符号 ---
echo "==> 瘦身:strip 二进制调试符号"
while IFS= read -r -d '' f; do
    if file "$f" | grep -q "Mach-O"; then
        strip -ux "$f" 2>/dev/null || true
    fi
done < <(find "$APP" -type f -print0)

after_bytes=$(du -sk "$APP" | awk '{print $1}')
saved=$((before_bytes - after_bytes))
echo "==> 瘦身后体积:${after_bytes} KB(节省 ${saved} KB)"

# 9) 可选:UPX 压缩 .so / dylib(若系统装了 upx)
if command -v upx >/dev/null 2>&1; then
    echo "==> 检测到 upx,压缩动态库"
    mapfile -t UPX_TARGETS < <(find "$APP" \( -name "*.so" -o -name "*.dylib" \) 2>/dev/null)
    if [ "${#UPX_TARGETS[@]}" -gt 0 ]; then
        upx -9 --best "${UPX_TARGETS[@]}" 2>/dev/null || true
        after_bytes=$(du -sk "$APP" | awk '{print $1}')
        echo "==> UPX 后体积:${after_bytes} KB"
    fi
else
    echo "   (未检测到 upx,跳过动态库压缩;如需进一步缩小可 brew install upx)"
fi

# =========================================================================
# 体积报告
# =========================================================================
final_mb=$(echo "scale=1; $after_bytes / 1024" | bc)
echo ""
echo "✓ 构建成功:$APP"
echo "  最终体积:${final_mb} MB"
if [ "$after_bytes" -lt 102400 ]; then
    echo "  ✓ 已低于 100MB 目标"
else
    echo "  ⚠ 仍超过 100MB;可进一步手动检查 dist 内最大文件:"
    echo "    du -sh \"$APP/Contents/Resources\"/* | sort -h"
fi
echo ""
echo "  双击运行;首次打开若被 Gatekeeper 拦截,执行:"
echo "    xattr -dr com.apple.quarantine \"$APP\""
