@echo off
cd /d "%~dp0"
if exist "C:\Python314\pythonw.exe" (
  start "" "C:\Python314\pythonw.exe" "%~dp0src\cool_blender_ui_thingy.py"
) else (
  start "" pythonw "%~dp0src\cool_blender_ui_thingy.py"
)
