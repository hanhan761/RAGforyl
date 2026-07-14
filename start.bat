@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_CMD=python"
where py >nul 2>nul
if %errorlevel%==0 set "PYTHON_CMD=py -3"

if not exist ".venv\Scripts\python.exe" (
  echo [1/5] Creating virtual environment...
  %PYTHON_CMD% -m venv .venv || goto :error
)

call ".venv\Scripts\activate.bat" || goto :error
echo [2/5] Installing RAGforyl...
python -m pip install -e . || goto :error

if not exist ".env" copy /Y ".env.example" ".env" >nul
if not exist "data\source" mkdir "data\source"
dir /b /a-d "data\source\*" >nul 2>nul
if errorlevel 1 copy /Y "examples\sources\flight_basics.md" "data\source\flight_basics.md" >nul

echo [3/5] Checking environment...
python -m ragforyl doctor || goto :error

if not exist "data\index\manifest.json" (
  echo [4/5] Building the demo knowledge graph...
  python -m ragforyl build || goto :error
) else (
  echo [4/5] Existing index found.
)

echo [5/5] Opening http://127.0.0.1:8000
python -m ragforyl serve --host 127.0.0.1 --port 8000 --open-browser
goto :eof

:error
echo.
echo Startup failed. Read the error above, then run start.bat again.
pause
exit /b 1
