@echo off
chcp 65001 >nul
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
  echo Create the environment first: py -3 -m venv .venv
  echo Then install Flask: .venv\Scripts\python.exe -m pip install -r requirements.txt
  goto finish
)
".venv\Scripts\python.exe" -c "import flask" >nul 2>&1
if errorlevel 1 (
  echo Install Flask: .venv\Scripts\python.exe -m pip install -r requirements.txt
  goto finish
)
echo Open http://127.0.0.1:5055 in your browser. Press Ctrl+C to stop.
".venv\Scripts\python.exe" app.py
:finish
popd
pause
