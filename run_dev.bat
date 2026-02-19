@echo off
setlocal

REM Go to project root (folder containing this .bat)
cd /d "%~dp0"

REM Start backend in PowerShell with venv activated first
start "FastAPI Backend" powershell -NoExit -Command "& { Set-Location '%~dp0'; .\venv\Scripts\activate.ps1; python api.py }"

REM Start frontend in separate terminal
start "Vite Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

endlocal
