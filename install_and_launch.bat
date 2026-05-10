@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found.
  echo.
  echo Install Python 3.10 or newer from:
  echo https://www.python.org/downloads/
  echo.
  echo During install, enable "Add python.exe to PATH".
  echo Then run this file again.
  pause
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 or newer is required.
  echo.
  echo Install a newer Python from:
  echo https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)

echo Installing Python requirements...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Failed to install requirements.
  pause
  exit /b 1
)

echo Launching BlenderThemeMaker...
where pythonw >nul 2>nul
if errorlevel 1 (
  start "" python "%~dp0src\cool_blender_ui_thingy.py"
) else (
  start "" pythonw "%~dp0src\cool_blender_ui_thingy.py"
)

endlocal
