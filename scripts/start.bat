@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo    Bilibili RAG One-Click Startup
echo ========================================
echo.

set PROJECT_ROOT=%~dp0..
cd /d "%PROJECT_ROOT%"

:: ========================================
:: 1. Environment Check
:: ========================================
echo [1/5] Checking environment...

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo   Error: Python 3.8+ not found
    exit /b 1
)
echo   - Python OK

:: Check Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo   Error: Node.js 18+ not found
    exit /b 1
)
echo   - Node.js OK

:: ========================================
:: 2. Dependency Check
:: ========================================
echo.
echo [2/5] Checking dependencies...

:: Python dependencies
if not exist "venv\Scripts\activate.bat" (
    echo   Creating virtual environment...
    python -m venv venv
)

echo   Activating virtual environment...
call venv\Scripts\activate.bat

echo   Installing Python dependencies...
pip install -r requirements.txt >nul 2>&1

:: Node.js dependencies
if not exist "frontend\node_modules" (
    echo   Installing frontend dependencies...
    cd frontend
    call npm install
    cd ..
)

echo   - Dependencies ready

:: ========================================
:: 3. Configuration Check
:: ========================================
echo.
echo [3/5] Checking configuration...

if not exist ".env" (
    if exist ".env.example" (
        echo   Copying config file...
        copy .env.example .env >nul
        echo   Warning: Please edit .env and configure DASHSCOPE_API_KEY
    )
)

echo   - Configuration ready

:: ========================================
:: 4. Initialize Directories
:: ========================================
echo.
echo [4/5] Initializing directories...

if not exist "data" mkdir data
if not exist "logs" mkdir logs
if not exist "data\models" mkdir data\models

echo   - Directories ready

:: ========================================
:: 5. Start Services
:: ========================================
echo.
echo [5/5] Starting services...
echo.

:: Start backend
echo   Starting backend service (http://localhost:8000)...
start "Bilibili RAG Backend" cmd /k "call venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

:: Wait for backend
timeout /t 3 /nobreak >nul

:: Start frontend
echo   Starting frontend service (http://localhost:3000)...
start "Bilibili RAG Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ========================================
echo    Startup complete!
echo ========================================
echo.
echo   Backend API: http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo   Frontend: http://localhost:3000
echo.
echo   Close the command window to stop services
echo.

pause
