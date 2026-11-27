#!/bin/bash
# 在仓库根目录或任意工作目录运行；使用 Python 3.11 arm64 构建。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-.venv/bin/python}"
export YEHANG_BUILD_VERSION="0.1.0-beta.3"
export YEHANG_BUILD_COMMIT="$(git rev-parse HEAD)"
"$PYTHON" packaging/notices.py
"$PYTHON" - <<'PY'
import json, os
from pathlib import Path
from PIL import Image
Image.open('packaging/yehang.ico').save('.build/yehang.icns')
Path('.build/build-info.json').write_text(json.dumps({'version':os.environ['YEHANG_BUILD_VERSION'], 'source_commit':os.environ['YEHANG_BUILD_COMMIT']},indent=2)+'\n')
PY
"$PYTHON" -m PyInstaller --noconfirm --distpath .build/macos/dist --workpath .build/macos/work packaging/macos.spec
codesign --verify --deep --strict .build/macos/dist/Yehang.app
mkdir -p .build/release
ditto -c -k --sequesterRsrc --keepParent .build/macos/dist/Yehang.app ".build/release/Yehang-${YEHANG_BUILD_VERSION}-macOS-arm64.zip"
(cd .build/release && shasum -a 256 "Yehang-${YEHANG_BUILD_VERSION}-macOS-arm64.zip" > SHA256SUMS-macOS.txt)
