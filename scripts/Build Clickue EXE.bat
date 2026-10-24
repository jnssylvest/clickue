@echo off
rem Builds dist\Clickue.exe (one file, with its icon). Python must be installed.
cd /d "%~dp0\.."
python -m pip install --upgrade --disable-pip-version-check pyinstaller -r requirements.txt
python -m PyInstaller --noconfirm --onefile --noconsole --name Clickue --icon assets\clickue.ico --hidden-import pystray._win32 src\clickue.py
echo.
echo Done: dist\Clickue.exe
pause
