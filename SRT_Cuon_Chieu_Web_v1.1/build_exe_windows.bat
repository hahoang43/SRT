@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3.12 -c "import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8"
if errorlevel 1 (echo Can Python 3.12 64-bit.& pause & exit /b 1)
py -3.12 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (pause & exit /b 1)
py -3.12 -m PyInstaller --noconfirm --clean SRT_Cuon_Chieu.spec
if errorlevel 1 pause
