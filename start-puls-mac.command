#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
  YEHANG_PY=.venv/bin/python
else
  YEHANG_PY=../macos-build-env/bin/python
fi
export YEHANG_DB_PATH="$PWD/.local/puls-preview/interactive.sqlite3"
exec "$YEHANG_PY" launch_studio.py --port 8521
