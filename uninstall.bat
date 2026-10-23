@echo off
rem Removes the Home Panel Start menu and startup shortcuts. Your files, settings
rem (%APPDATA%\HomePanel) and the Edge profile (%LOCALAPPDATA%\HomePanel) are kept.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0shortcut.ps1" -Folder Programs -Remove
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0shortcut.ps1" -Folder Startup -Remove
pause
