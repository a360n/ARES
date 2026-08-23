#!/bin/bash
# ============================================================================
# ARES (Autonomous Rescue & Emergency System)
# Smart Auto-Launcher for macOS / Terminal
# ============================================================================

# Set working directory to the directory where this script is located
cd "$(dirname "$0")"

echo "========================================================"
echo "🛡️  ARES Autonomous System // Smart Auto-Launcher"
echo "========================================================"

# 1. Check if project files exist; if not, clone/download from GitHub
if [ ! -f "app.py" ]; then
    echo "📥 Project files not found locally."
    echo "📥 Downloading / Updating ARES project from GitHub..."
    if [ ! -d ".git" ]; then
        git init
        git remote add origin https://github.com/a360n/ARES.git
    fi
    git fetch origin main
    git checkout -B main origin/main
    git reset --hard origin/main
    echo "✅ Project files downloaded successfully!"
    echo ""
fi

# 2. Check if virtual environment exists; if not, create and install dependencies
if [ ! -d "venv" ]; then
    echo "📦 Setting up Python virtual environment (venv)..."
    python3 -m venv venv
    if [ -f "venv/bin/pip" ]; then
        echo "⬇️  Installing required packages from requirements.txt (this may take a few minutes on first run)..."
        venv/bin/pip install --upgrade pip
        venv/bin/pip install -r requirements.txt
        echo "✅ Dependencies installed successfully!"
    else
        echo "⚠️  Failed to create virtual environment. Running with system python3..."
    fi
    echo ""
fi

# 3. Automatically open default web browser to ARES login interface after short delay
echo "🚀 Starting HTTPS Mission Control Server..."
(sleep 2.5 && open "https://127.0.0.1:5001/login") &

# 4. Execute main modular ARES server
if [ -f "venv/bin/python" ]; then
    venv/bin/python app.py
elif [ -f "venv/bin/python3" ]; then
    venv/bin/python3 app.py
else
    python3 app.py
fi

# Keep window open if process exits
echo ""
echo "Press [ENTER] to close this window..."
read -r
