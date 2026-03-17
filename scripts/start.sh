#!/bin/bash
# Bilibili RAG One-Click Startup Script (Linux/Mac)

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}   Bilibili RAG One-Click Startup${NC}"
echo -e "${BLUE}========================================${NC}"

# ============================================
# 1. Environment Check
# ============================================
echo -e "\n${GREEN}[1/5] Checking environment...${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo -e "${RED}Error: Python not found. Please install Python 3.8+${NC}"
        exit 1
    fi
    PYTHON_CMD=python
else
    PYTHON_CMD=python3
fi

PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "  Python: $PYTHON_VERSION"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}Error: Node.js not found. Please install Node.js 18+${NC}"
    exit 1
fi

NODE_VERSION=$(node -v)
echo "  Node.js: $NODE_VERSION"

# Check ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${YELLOW}Warning: ffmpeg not found. ASR functionality may not work${NC}"
    echo "  Install: brew install ffmpeg (macOS) / sudo apt install ffmpeg (Linux)"
fi

# ============================================
# 2. Dependency Check
# ============================================
echo -e "\n${GREEN}[2/5] Checking dependencies...${NC}"

# Python dependencies
if [ ! -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    echo "  Creating virtual environment..."
    $PYTHON_CMD -m venv venv
fi

echo "  Activating virtual environment..."
source "$PROJECT_ROOT/venv/bin/activate"

echo "  Installing Python dependencies..."
pip install -q -r requirements.txt 2>/dev/null || pip install -r requirements.txt

# Node.js dependencies
if [ ! -d "$PROJECT_ROOT/frontend/node_modules" ]; then
    echo "  Installing frontend dependencies..."
    cd "$PROJECT_ROOT/frontend"
    npm install
    cd "$PROJECT_ROOT"
fi

echo "  Dependencies ready"

# ============================================
# 3. Configuration Check
# ============================================
echo -e "\n${GREEN}[3/5] Checking configuration...${NC}"

if [ ! -f "$PROJECT_ROOT/.env" ]; then
    if [ -f "$PROJECT_ROOT/.env.example" ]; then
        echo "  Copying config file..."
        cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
        echo -e "${YELLOW}Warning: Please edit .env and configure DASHSCOPE_API_KEY${NC}"
    else
        echo -e "${RED}Error: Config file not found${NC}"
        exit 1
    fi
fi

# Check critical config
if grep -q "DASHSCOPE_API_KEY=your_api_key" "$PROJECT_ROOT/.env" 2>/dev/null; then
    echo -e "${YELLOW}Warning: Please configure DASHSCOPE_API_KEY in .env${NC}"
fi

echo "  Configuration ready"

# ============================================
# 4. Create Required Directories
# ============================================
echo -e "\n${GREEN}[4/5] Initializing directories...${NC}"

mkdir -p "$PROJECT_ROOT/data"
mkdir -p "$PROJECT_ROOT/logs"
mkdir -p "$PROJECT_ROOT/data/models"

echo "  Directories ready"

# ============================================
# 5. Start Services
# ============================================
echo -e "\n${GREEN}[5/5] Starting services...${NC}"
echo ""

# Start backend
echo -e "${BLUE}Starting backend service (http://localhost:8000)...${NC}"
cd "$PROJECT_ROOT"
$PYTHON_CMD -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Wait for backend
sleep 3

# Start frontend
echo -e "${BLUE}Starting frontend service (http://localhost:3000)...${NC}"
cd "$PROJECT_ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   Startup complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  Backend API: http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "  Frontend: http://localhost:3000"
echo ""
echo "  Press Ctrl+C to stop services"
echo ""

# Catch exit signal
cleanup() {
    echo ""
    echo "  Stopping services..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    echo "  Services stopped"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for child processes
wait
