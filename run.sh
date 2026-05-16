#!/bin/bash
# OpenBrain Alpha — Start Server
# Usage: ./run.sh

set -e
cd "$(dirname "$0")/backend"
echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║   OpenBrain Alpha Engine — IQC 2026   ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""
echo "  → Starting server at http://localhost:8000"
echo "  → Press Ctrl+C to stop"
echo ""
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
