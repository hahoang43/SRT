@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set "PYTHON=py -3") else (set "PYTHON=python")
%PYTHON% -m pip install -r requirements.txt
if errorlevel 1 (echo Cai thu vien that bai. Kiem tra Python 3.10+ va mang.& pause & exit /b 1)
%PYTHON% app.py
if errorlevel 1 pause
