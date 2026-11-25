@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto :run
where py >nul 2>nul
if errorlevel 1 (
    python -m venv .venv
) else (
    py -3 -m venv .venv
)
if errorlevel 1 goto :failed
:run
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, ijson, pypdfium2, keyring, PIL, httpx, tzdata" >nul 2>nul
if errorlevel 1 ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -X utf8 launch_studio.py
if not errorlevel 1 exit /b 0
:failed
echo Check Python 3.11+ and your network connection, then try again.
pause
exit /b 1
