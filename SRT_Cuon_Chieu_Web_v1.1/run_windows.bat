@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (set "SRT_PYTHON=python") else (set "SRT_PYTHON=py -3.12")
%SRT_PYTHON% -c "import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8, 'Can Python 3.12 64-bit'"
if errorlevel 1 (echo Can cai Python 3.12 64-bit.& pause & exit /b 1)
%SRT_PYTHON% -m pip install -r requirements.txt
if errorlevel 1 (echo Cai thu vien that bai. Kiem tra mang.& pause & exit /b 1)
%SRT_PYTHON% -B app.py
if errorlevel 1 pause
