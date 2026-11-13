@echo off
setlocal
cd /d "%~dp0"
title SLSK 2D HD Remake Remaster - starting

set "PYEXE="
set "PYARG="

py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
  set "PYEXE=py"
  set "PYARG=-3"
)

if not defined PYEXE call :findpython

if not defined PYEXE (
  echo Python was not found. Installing it now, this happens only once...
  winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
  call :findpython
)

if not defined PYEXE (
  echo.
  echo Could not set up Python automatically.
  echo Please install it from https://www.python.org/downloads/
  echo and tick the box "Add python.exe to PATH" in the installer.
  echo Then double-click Start.bat again.
  pause
  exit /b 1
)

if not exist ".venv\ready.txt" (
  echo First run: setting things up, this takes about a minute...
  if exist ".venv" rmdir /s /q ".venv"
  "%PYEXE%" %PYARG% -m venv .venv
  if errorlevel 1 goto :fail
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 goto :fail
  echo ok> ".venv\ready.txt"
)

start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

:findpython
for %%P in ("%LocalAppData%\Programs\Python\Python312\python.exe" "%ProgramFiles%\Python312\python.exe" "%LocalAppData%\Programs\Python\Python313\python.exe" "%LocalAppData%\Programs\Python\Python311\python.exe" "%LocalAppData%\Programs\Python\Python310\python.exe") do (
  if exist %%P if not defined PYEXE set "PYEXE=%%~P"
)
exit /b 0

:fail
echo.
echo Setup failed. Check your internet connection and double-click Start.bat again.
pause
exit /b 1
