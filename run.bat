@echo off
title 2Care.ai real-time voice cockpit
echo =======================================================================
echo              2Care.ai - Real-Time Multilingual Voice AI Agent          
echo              Autonomous Clinical Scheduling Cockpit Launcher          
echo =======================================================================
echo.

cd /d "%~dp0"

:: Check dependencies
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in system PATH.
    echo Please install Python 3.9+ to continue.
    pause
    exit /b 1
)

where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not in system PATH.
    echo Please install Node.js to continue.
    pause
    exit /b 1
)

echo [Step 1/3] Preparing Python FastAPI backend...
cd backend
if exist ".venv" goto skip_venv
echo [System] Creating Python virtual environment .venv...
python -m venv .venv
:skip_venv

echo [System] Upgrading pip inside virtualenv...
.venv\Scripts\python -m pip install --upgrade pip

echo [System] Installing python requirements...
.venv\Scripts\pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARNING] Some python requirements failed to install. Continuing...
)

echo.
echo [Step 2/3] Preparing React TypeScript Frontend...
cd ../frontend
if exist "node_modules" goto skip_npm
echo [System] node_modules not found. Running npm install (this may take a minute)...
call npm install
:skip_npm

echo.
echo [Step 3/3] Starting servers concurrently in separate windows...

:: Launch backend in new terminal window
echo [System] Launching FastAPI Backend on http://localhost:8000 ...
start "2Care.ai FastAPI Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\activate && uvicorn main:app --reload --port 8000"

:: Launch frontend in new terminal window
echo [System] Launching Vite Frontend on http://localhost:5173 ...
start "2Care.ai React Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo [Launch Success] Concurrently booted clinical scheduler cockpit!
echo Waiting 5 seconds for servers to start, then opening web interface...
timeout /t 5 >nul

:: Open browser
explorer "http://localhost:5173"

echo.
echo Cockpit running successfully. Have a nice flight!
echo.
pause
