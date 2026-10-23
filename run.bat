@echo off
rem Starts Home Panel without a console window.
rem Finds the full path of pythonw.exe next to the Python that has PySide6 and starts that
rem directly (no "pyw" launcher), so double-clicking this file in Explorer works reliably.
setlocal
cd /d "%~dp0"
set "APP=%~dp0home_panel.py"
set "PYW="

if exist ".venv\Scripts\pythonw.exe" set "PYW=%~dp0.venv\Scripts\pythonw.exe"

if not defined PYW (
  where py >nul 2>&1
  if not errorlevel 1 (
    for /f "usebackq delims=" %%P in (`py -3 -c "import os,sys,PySide6;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2^>nul`) do set "PYW=%%P"
  )
)
if not defined PYW (
  where python >nul 2>&1
  if not errorlevel 1 (
    for /f "usebackq delims=" %%P in (`python -c "import os,sys,PySide6;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2^>nul`) do set "PYW=%%P"
  )
)

if defined PYW if exist "%PYW%" (
  start "Home Panel" "%PYW%" "%APP%" %*
  exit /b 0
)

echo Home Panel: no Python with PySide6 was found.
echo Install it with:   py -m pip install PySide6-Essentials
pause
exit /b 1
