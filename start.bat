@echo off
chcp 65001 >nul
echo =======================================
echo   REPKA Gantt AI Backend v4
echo =======================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10+ not found in PATH
    pause
    exit /b 1
)

echo [1/4] Checking .env...
findstr /C:"sk-or-v1-..." .env >nul 2>&1
if not errorlevel 1 (
    echo [ERROR] Replace sk-or-v1-... in .env with your real OpenRouter key!
    echo        Get key: https://openrouter.ai/keys
    pause
    exit /b 1
)

if not exist ".env" (
    echo [ERROR] .env file not found!
    echo        Copy .env.example to .env and add your OpenRouter key.
    pause
    exit /b 1
)

echo [2/4] Setting up venv...
if not exist "venv\" (
    python -m venv venv
)
call venv\Scripts\activate.bat

echo [3/4] Installing dependencies...
pip install -q -r requirements.txt

echo [4/4] Starting server...
echo.
echo =======================================
echo   Open in browser: http://localhost:8000
echo   Swagger UI:      http://localhost:8000/docs
echo   Health check:    http://localhost:8000/api/health
echo =======================================
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
