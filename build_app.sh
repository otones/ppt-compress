#!/usr/bin/env bash
# Build the macOS .app bundle for PPTX 压缩器,并做体积瘦身。
#
#   ./build_app.sh
#
# 产出 dist/PPTXCompressor.app。在 macOS(Apple Silicon & Intel)测试通过。
# 目标:最终 .app 体积 < 100MB。
set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="PPTXCompressor"
APP="dist/${APP_NAME}.app"
PY=python3

echo "==> 创建构建虚拟环境 (./.venv-build)"
$PY -m venv .venv-build
# shellcheck disable=SC1091
source .venv-build/bin/activate

echo "==> 安装构建依赖"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt py2app >/dev/null

echo "==> 以可编辑模式安装本包"
pip install -e . >/dev/null

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
# 瘦身阶段:py2app 即便排除了子模块,仍会把 PySide6 包目录(含 Qt 插件、
# 翻译、QML、文档、示例)整目录拷进 .app。这里做后处理,删除 GUI 用不到
# 的资源。GUI 只用 QtCore/QtGui/QtWidgets。
# =========================================================================
echo "==> 瘦身:删除冗余 Qt 资源"

# PySide6 资源位于 .app/Contents/Resources/lib/python*/site-packages/PySide6/
PYSIDE6_DIR=$(find "$APP/Contents/Resources" -type d -name PySide6 2>/dev/null | head -1 || true)

if [ -n "$PYSIDE6_DIR" ] && [ -d "$PYSIDE6_DIR" ]; then
    echo "   PySide6 目录:$PYSIDE6_DIR"

    # 1) 删除被排除的子模块 .so / .pyi(防止漏网)
    rm -f "$PYSIDE6_DIR"/QtWebEngine*.so
    rm -f "$PYSIDE6_DIR"/QtQml*.so
    rm -f "$PYSIDE6_DIR"/QtQuick*.so
    rm -f "$PYSIDE6_DIR"/Qt3D*.so
    rm -f "$PYSIDE6_DIR"/QtCharts*.so
    rm -f "$PYSIDE6_DIR"/QtDataVisualization*.so
    rm -f "$PYSIDE6_DIR"/QtPdf*.so
    rm -f "$PYSIDE6_DIR"/QtMultimedia*.so
    rm -f "$PYSIDE6_DIR"/QtNetwork*.so
    rm -f "$PYSIDE6_DIR"/QtBluetooth*.so
    rm -f "$PYSIDE6_DIR"/QtSensors*.so
    rm -f "$PYSIDE6_DIR"/QtPositioning*.so
    rm -f "$PYSIDE6_DIR"/QtLocation*.so
    rm -f "$PYSIDE6_DIR"/QtSerialBus*.so
    rm -f "$PYSIDE6_DIR"/QtSerialPort*.so
    rm -f "$PYSIDE6_DIR"/QtSql*.so
    rm -f "$PYSIDE6_DIR"/QtTest*.so
    rm -f "$PYSIDE6_DIR"/QtXml*.so
    rm -f "$PYSIDE6_DIR"/QtSvg*.so
    rm -f "$PYSIDE6_DIR"/QtOpenGL*.so
    rm -f "$PYSIDE6_DIR"/QtPrintSupport*.so
    rm -f "$PYSIDE6_DIR"/QtDesigner*.so
    rm -f "$PYSIDE6_DIR"/QtUiTools*.so
    rm -f "$PYSIDE6_DIR"/QtHelp*.so
    rm -f "$PYSIDE6_DIR"/QtScxml*.so
    rm -f "$PYSIDE6_DIR"/QtStateMachine*.so
    rm -f "$PYSIDE6_DIR"/QtRemoteObjects*.so
    rm -f "$PYSIDE6_DIR"/QtWebChannel*.so
    rm -f "$PYSIDE6_DIR"/QtWebSockets*.so
    rm -f "$PYSIDE6_DIR"/QtNfc*.so
    rm -f "$PYSIDE6_DIR"/QtTextToSpeech*.so
    rm -f "$PYSIDE6_DIR"/QtConcurrent*.so

    # 2) QML 目录(即便没用 Quick/Qml 也会被拷进来,通常几十 MB)
    rm -rf "$PYSIDE6_DIR/qml"
    rm -rf "$PYSIDE6_DIR/Qt/qml"

    # 3) 翻译文件 .qm(GUI 用不到,数十 MB)
    rm -rf "$PYSIDE6_DIR/translations"
    rm -rf "$PYSIDE6_DIR/Qt/translations"

    # 4) 资源 / 示例 / 文档
    rm -rf "$PYSIDE6_DIR/examples"
    rm -rf "$PYSIDE6_DIR/include"
    rm -rf "$PYSIDE6_DIR/Qt/lib/QtWebEngineCore.framework" 2>/dev/null || true

    # 5) Qt 插件:只保留 platforms / styles / imageformats / platforms
    if [ -d "$PYSIDE6_DIR/plugins" ]; then
        find "$PYSIDE6_DIR/plugins" -maxdepth 1 -mindepth 1 -type d \
            ! -name platforms \
            ! -name styles \
            ! -name imageformats \
            -exec rm -rf {} +
    fi
    # imageformats 里只留常用格式,删 svg / tiff / pdf 等插件
    if [ -d "$PYSIDE6_DIR/plugins/imageformats" ]; then
        rm -f "$PYSIDE6_DIR/plugins/imageformats"/libqsvg*
        rm -f "$PYSIDE6_DIR/plugins/imageformats"/libqtiff*
        rm -f "$PYSIDE6_DIR/plugins/imageformats"/libqpdf*
        rm -f "$PYSIDE6_DIR/plugins/imageformats"/libqtga*
        rm -f "$PYSIDE6_DIR/plugins/imageformats"/libqwbmp*
        rm -f "$PYSIDE6_DIR/plugins/imageformats"/libqwebp*
    fi
fi

# 6) PySide6 的 .pyi 类型存根文件(运行时不需要)
find "$APP/Contents/Resources" -name "*.pyi" -delete 2>/dev/null || true

# 7) .pyc 之外的所有源码 .py 已被 py2app 编译;删除冗余的源文件
#    (注意:保留包结构,只删纯源码文件)
find "$APP/Contents/Resources" -name "*.py" -path "*/site-packages/*" -delete 2>/dev/null || true

# 8) 对所有 Mach-O 二进制和动态库 strip 调试符号
echo "==> 瘦身:strip 二进制调试符号"
while IFS= read -r -d '' f; do
    # 仅对 Mach-O 文件 strip
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
