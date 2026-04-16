#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo "Deteniendo servidores..."
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "========================================"
echo "  Spotify Transcripts"
echo "========================================"
echo ""

# Start backend
echo "Iniciando backend (puerto 8000)..."
cd "$SCRIPT_DIR/backend"

if [ ! -d "venv" ]; then
    echo "Ejecuta ./setup.sh primero"
    exit 1
fi

source venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

sleep 3

# Start frontend
echo "Iniciando frontend (puerto 3000)..."
cd "$SCRIPT_DIR/frontend"
python3 -m http.server 3000 &
FRONTEND_PID=$!

echo ""
echo "========================================"
echo "  Backend:  http://127.0.0.1:8000"
echo "  Frontend: http://localhost:3000"
echo "  Ctrl+C para detener"
echo "========================================"
echo ""

# Open browser
open http://localhost:3000 2>/dev/null || true

wait
