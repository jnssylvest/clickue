@echo off
rem Run Clickue from source. The first time (or when a helper package is too old), installs
rem or updates the required packages from requirements.txt.
cd /d "%~dp0\.."
python -c "import pystray, PIL, cv2, numpy; v=tuple(int(x) for x in PIL.__version__.split('.')[:2]); assert v >= (12, 3)" 1>nul 2>nul
if errorlevel 1 (
  echo Installing or updating Clickue's helper packages ^(one time only^)...
  python -m pip install --quiet --upgrade --disable-pip-version-check -r requirements.txt
)
start "" pythonw "src\clickue.py"
