@echo off
chcp 65001 >nul
pushd "%~dp0" || exit /b 1
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
  if not errorlevel 1 goto local_python
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto python_launcher
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto system_python
echo Python 3.10+ not found. Install Python from https://www.python.org/downloads/
set "journal_exit=1"
goto finish

:local_python
".venv\Scripts\python.exe" journal.py
goto result

:python_launcher
py -3 journal.py
goto result

:system_python
python journal.py

:result
set "journal_exit=%errorlevel%"

:finish
popd
pause
exit /b %journal_exit%
