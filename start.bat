@echo off
chcp 65001 >nul
title REPKA Gantt AI Backend
cd /d "%~dp0"

echo.
echo ═══════════════════════════════════════════
echo   🚀 REPKA Gantt AI Backend
echo ═══════════════════════════════════════════
echo.

REM ── Проверка Python ──
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в PATH.
    echo Установи Python с https://python.org
    echo И поставь галочку "Add Python to PATH"
    pause
    exit /b 1
)
python --version
echo.

REM ── Проверка .env ──
if not exist ".env" (
    echo [ОШИБКА] Файл .env не найден!
    pause
    exit /b 1
)

REM Проверим, не заглушка ли ключ
findstr /C:"sk-or-v1-..." .env >nul 2>&1
if not errorlevel 1 (
    echo [ОШИБКА] В .env всё ещё заглушка "sk-or-v1-..."
    echo Открой .env в Блокноте и замени на реальный ключ с https://openrouter.ai/keys
    pause
    exit /b 1
)
echo [OK] .env настроен
echo.

REM ── Виртуальное окружение ──
if not exist "venv\" (
    echo [SETUP] Создаю виртуальное окружение...
    python -m venv venv
)
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ОШИБКА] Не удалось активировать venv
    pause
    exit /b 1
)
echo [OK] venv активирован
echo.

REM ── Зависимости ──
echo [SETUP] Устанавливаю зависимости...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ОШИБКА] pip install провалился
    pause
    exit /b 1
)
echo [OK] Зависимости установлены
echo.

REM ── Быстрая проверка ──
python -c "from openai import OpenAI; print('[OK] openai импортируется')" 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Библиотека openai не установлена
    pause
    exit /b 1
)

python -c "from dotenv import load_dotenv; import os; load_dotenv(); key=os.getenv('OPENROUTER_API_KEY',''); print(f'[OK] Ключ загружен: {key[:12]}...')" 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Не могу загрузить .env
    pause
    exit /b 1
)

REM ── Запуск ──
echo.
echo ═══════════════════════════════════════════
echo   ✅ Сервер: http://localhost:8000
echo   📋 Swagger: http://localhost:8000/docs
echo   Нажми Ctrl+C для остановки
echo ═══════════════════════════════════════════
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
