#!/bin/bash
# ============================================================================
# ARES (Autonomous Rescue & Emergency System)
# One-Click System Launcher for macOS / Terminal
# ============================================================================

# Set working directory to the directory where this script is located
cd "$(dirname "$0")"

echo "========================================================"
echo "🛡️  ARES Autonomous System // One-Click Launcher"
echo "========================================================"
echo "Initializing environment and starting HTTPS server..."
echo ""

# Automatically open default web browser to ARES login interface after short delay
(sleep 2.5 && open "https://127.0.0.1:5001/login") &

# Execute main modular ARES server using project virtual environment
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
