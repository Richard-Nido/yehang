#!/bin/bash
# 在仓库根目录或任意工作目录运行；使用 Python 3.11 arm64 构建。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-.venv/bin/python}"
"$PYTHON" packaging/notices.py
"$PYTHON" - <<'PY'
from PIL import Image
Image.open('packaging/yehang.ico').save('.build/yehang.icns')
PY
"$PYTHON" -m PyInstaller --noconfirm --distpath .build/macos/dist --workpath .build/macos/work packaging/macos.spec
codesign --verify --deep --strict .build/macos/dist/Yehang.app
mkdir -p .build/release
ditto -c -k --sequesterRsrc --keepParent .build/macos/dist/Yehang.app .build/release/Yehang-0.1.0-beta.2-macOS-arm64.zip
shasum -a 256 .build/release/Yehang-0.1.0-beta.2-macOS-arm64.zip > .build/release/SHA256SUMS-macOS.txt
