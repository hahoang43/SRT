@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt pyinstaller
py -3 -m PyInstaller --noconfirm --clean --onedir --windowed --name SRT_Cuon_Chieu --collect-all PySide6 app.py
if errorlevel 1 pause
