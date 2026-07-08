#!/usr/bin/env bash
# Build the macOS .app bundle for PPTX 压缩器.
#
#   ./build_app.sh
#
# Produces dist/PPTXCompressor.app. Tested on macOS (Apple Silicon & Intel).
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Creating build venv (./.venv-build)"
python3 -m venv .venv-build
# shellcheck disable=SC1091
source .venv-build/bin/activate

echo "==> Installing build deps"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt py2app >/dev/null

echo "==> Installing package in editable mode"
pip install -e . >/dev/null

echo "==> Cleaning previous builds"
rm -rf build dist

echo "==> Running py2app"
python setup.py py2app

APP="dist/PPTXCompressor.app"
if [ -d "$APP" ]; then
    echo ""
    echo "✓ 构建成功:$APP"
    echo "  双击运行;首次打开若被 Gatekeeper 拦截,执行:"
    echo "    xattr -dr com.apple.quarantine \"$APP\""
else
    echo "✗ 构建失败,请检查上方日志" >&2
    exit 1
fi
