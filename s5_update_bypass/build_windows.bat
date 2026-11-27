@echo off
REM Build S5UpdateBypass.exe on Windows.
REM Run this from a normal cmd.exe or double-click it.
setlocal
cd /d "%~dp0"

echo === S5UpdateBypass Windows build ===

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo ERROR: python not found in PATH.
  echo Install Python 3.9+ from https://www.python.org/ and enable "Add python.exe to PATH".
  goto :err
)

if not exist ".build-venv-win\Scripts\python.exe" (
  echo [1/4] Creating build venv...
  python -m venv .build-venv-win
  if errorlevel 1 goto :err
) else (
  echo [1/4] Reusing .build-venv-win
)

set "PY=.build-venv-win\Scripts\python.exe"

echo [2/4] Installing build dependencies...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install pyinstaller pyusb libusb-package
if errorlevel 1 goto :err

echo [3/4] Building one-file EXE...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name S5UpdateBypass ^
  --icon assets\icon.ico ^
  --paths ..\s5_unlock ^
  --hidden-import s5_unlock_core ^
  --hidden-import usb ^
  --hidden-import usb.backend.libusb1 ^
  --hidden-import libusb_package ^
  --collect-all libusb_package ^
  bypass_gui.py
if errorlevel 1 goto :err

echo [4/4] Checking output...
if not exist "dist\S5UpdateBypass.exe" (
  echo ERROR: dist\S5UpdateBypass.exe was not produced.
  goto :err
)

echo.
echo DONE: %CD%\dist\S5UpdateBypass.exe
echo.
echo Notes:
echo   - This EXE still needs the camera in service mode (PLAY + AF-ON).
echo   - Windows may ask for permission to access the USB device the first time.
echo   - If the camera is not detected, install/repair the WinUSB driver for 04DA:2370
echo     with Zadig (same requirement as lumix_ml\usb_link.py).
echo.
pause
exit /b 0

:err
echo.
echo BUILD FAILED.
pause
exit /b 1
