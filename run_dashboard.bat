@echo off
setlocal

REM Project root
cd /d "%~dp0"

REM Build React frontend so backend can serve it at /
echo Building frontend...
cd frontend
call npm run build
if errorlevel 1 (
  echo Frontend build failed.
  exit /b 1
)
cd ..

REM Activate venv if present
if exist "venv\Scripts\activate.bat" call venv\Scripts\activate.bat

REM Start backend; dashboard will be at http://127.0.0.1:8000
echo Starting backend. Open http://127.0.0.1:8000 for the dashboard.
python api.py

endlocal
