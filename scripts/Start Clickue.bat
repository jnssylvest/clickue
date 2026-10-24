@echo off
rem Run Clickue from source. The first time, installs the required packages.
cd /d "%~dp0\.."
python -c "import pystray, PIL, cv2, numpy" 1>nul 2>nul
if errorlevel 1 (
  echo Installing Clickue's helper packages ^(one time only^)...
  python -m pip install --quiet --disable-pip-version-check -r requirements.txt
)
start "" pythonw "src\clickue.py"
