#!/bin/bash
# Bilibili RAG Dependency Installation Script (Linux/Mac)

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
echo -e "${GREEN}   Bilibili RAG Dependency Installation${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# ============================================
# 1. Environment Check
# ============================================
echo -e "${GREEN}[1/4] Checking environment...${NC}"

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

# ============================================
# 2. Create Virtual Environment
# ============================================
echo -e "\n${GREEN}[2/4] Creating virtual environment...${NC}"

if [ ! -d "venv" ]; then
    $PYTHON_CMD -m venv venv
    echo "  Virtual environment created"
else
    echo "  Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate

echo "  Virtual environment activated"

# ============================================
# 3. Install Python Dependencies
# ============================================
echo -e "\n${GREEN}[3/4] Installing Python dependencies...${NC}"

pip install --upgrade pip
pip install -r requirements.txt

echo "  Python dependencies installed"

# ============================================
# 4. Check Configuration
# ============================================
echo -e "\n${GREEN}[4/5] Checking configuration...${NC}"

if [ ! -f "$PROJECT_ROOT/.env" ]; then
    if [ -f "$PROJECT_ROOT/.env.example" ]; then
        echo "  Copying config file..."
        cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
        echo -e "${YELLOW}Warning: Please edit .env and configure DASHSCOPE_API_KEY${NC}"
    fi
fi

echo "  Configuration ready"

# ============================================
# 5. Install Frontend Dependencies
# ============================================
echo -e "\n${GREEN}[5/5] Installing frontend dependencies...${NC}"

cd frontend
npm install
cd ..

echo "  Frontend dependencies installed"

# ============================================
# 6. Initialize Directories
# ============================================
echo -e "\n${GREEN}[6/6] Initializing directories...${NC}"

mkdir -p data
mkdir -p logs
mkdir -p data/models

echo "  Directories initialized"

# ============================================
# Complete
# ============================================
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   Dependencies installed!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  Next steps:"
echo "  1. Copy and edit .env file"
echo "        cp .env.example .env"
echo "  2. Configure DASHSCOPE_API_KEY"
echo "  3. Run startup script"
echo "        ./scripts/start.sh"
echo ""
