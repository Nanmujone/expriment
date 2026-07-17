@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
set "APP_PYTHON=%PROJECT_ROOT%.venv\Scripts\pythonw.exe"

if not exist "%APP_PYTHON%" (
  echo Project Python was not found. Run "uv sync --frozen" first.
  pause
  exit /b 1
)

cd /d "%PROJECT_ROOT%"
start "English Song Learning Player" "%APP_PYTHON%" -m english_player
