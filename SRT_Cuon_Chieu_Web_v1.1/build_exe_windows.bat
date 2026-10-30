@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (set "SRT_PYTHON=python") else (set "SRT_PYTHON=py -3")
%SRT_PYTHON% -c "import sys,struct; assert sys.version_info[:2]>=(3,10) and struct.calcsize('P')==8"
if errorlevel 1 (echo Can Python 3.10 tro len, ban 64-bit.& pause & exit /b 1)
%SRT_PYTHON% -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (pause & exit /b 1)
%SRT_PYTHON% -m PyInstaller --noconfirm --clean SRT_Cuon_Chieu.spec
if errorlevel 1 pause
