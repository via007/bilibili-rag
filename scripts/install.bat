@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo    Bilibili RAG Dependencies
echo ========================================
echo.

set PROJECT_ROOT=%~dp0..
cd /d "%PROJECT_ROOT%"

:: ========================================
:: 1. Check Environment
:: ========================================
echo [1/5] Checking environment...

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python 3.8+ not found
    exit /b 1
)
echo   - Python OK

:: Check Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo Error: Node.js 18+ not found
    exit /b 1
)
echo   - Node.js OK

:: ========================================
:: 2. Create Virtual Environment
:: ========================================
echo.
echo [2/5] Creating virtual environment...

if not exist "venv" (
    echo   Creating venv...
    python -m venv venv
) else (
    echo   venv already exists
)

echo   Activating venv...
call venv\Scripts\activate.bat

echo   - venv activated

:: ========================================
:: 3. Install Python Dependencies
:: ========================================
echo.
echo [3/5] Installing Python dependencies...

pip install --upgrade pip
pip install -r requirements.txt

echo   - Python dependencies OK

:: ========================================
:: 4. Check Config
:: ========================================
echo.
echo [4/5] Checking config...

if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo   Warning: Please edit .env and configure DASHSCOPE_API_KEY
    )
)

echo   - Config OK

:: ========================================
:: 5. Initialize Directories
:: ========================================
echo.
echo [5/5] Initializing directories...

if not exist "data" mkdir data
if not exist "logs" mkdir logs
if not exist "data\models" mkdir data\models

echo   - Directories OK

:: ========================================
:: Complete
:: ========================================
echo.
echo ========================================
echo    Dependencies installed!
echo ========================================
echo.
echo   Next steps:
echo   1. Edit .env file
echo      copy .env.example .env
echo   2. Configure DASHSCOPE_API_KEY
echo   3. Run startup script
echo      scripts\start.bat
echo.

pause
