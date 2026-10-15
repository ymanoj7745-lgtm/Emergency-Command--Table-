@echo off
title Emergency Command Table - Launcher
color 0B

echo ============================================================
echo     EMERGENCY COMMAND TABLE - LAUNCHER
echo ============================================================
echo.

REM -- Navigate to project folder
cd /d "D:\OPEN CV\Open_cv_production_grade_projects\Emergency"

REM -- Check if venv exists
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Expected at: %CD%\venv
    pause
    exit /b 1
)

REM -- Kill any leftover python processes from previous runs
echo [1/4] Cleaning up old processes...
taskkill /F /IM python.exe >nul 2>&1
timeout /t 1 >nul

REM -- Start HTTP server in a separate window (background)
echo [2/4] Starting HTTP server on port 8000...
start "Emergency - HTTP Server" cmd /k "cd /d "%CD%" && call venv\Scripts\activate.bat && python -m http.server 8000"

REM -- Give the HTTP server a moment to bind
timeout /t 2 >nul

REM -- Open browser AFTER HTTP server is up
echo [3/4] Opening browser...
start "" "http://localhost:8000/index.html"

REM -- Start hand tracker in THIS window
echo [4/4] Starting hand tracker (press 'q' in webcam window to quit)...
echo.
echo ============================================================
echo   TIP: Say "show fire markers" for voice commands
echo        Open palm = rotate  ^|  Pinch = drop  ^|  Fist = delete
echo ============================================================
echo.

call venv\Scripts\activate.bat
python hand_tracker.py

REM -- When hand_tracker exits, kill the HTTP server window too
echo.
echo Shutting down HTTP server...
taskkill /F /FI "WindowTitle eq Emergency - HTTP Server*" >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1

echo.
echo ============================================================
echo   SYSTEM SHUTDOWN COMPLETE
echo ============================================================
pause