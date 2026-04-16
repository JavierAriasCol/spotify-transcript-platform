#!/bin/bash
set -e

echo "========================================"
echo "  Spotify Transcripts - Setup (macOS)"
echo "========================================"
echo ""

# Check Homebrew
if ! command -v brew &> /dev/null; then
    echo "Homebrew no encontrado. Instalando..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "Homebrew OK"
fi

# Check Python 3.11+
PYTHON_CMD=""
for cmd in python3.13 python3.12 python3.11; do
    if command -v "$cmd" &> /dev/null; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "Python 3.11+ no encontrado. Instalando python@3.12..."
    brew install python@3.12
    PYTHON_CMD="python3.12"
fi

echo "Python: $PYTHON_CMD ($($PYTHON_CMD --version))"

# Check FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "FFmpeg no encontrado. Instalando..."
    brew install ffmpeg
else
    echo "FFmpeg OK"
fi

# Create venv and install deps
echo ""
echo "Configurando entorno virtual..."
cd "$(dirname "$0")/backend"

if [ -d "venv" ]; then
    rm -rf venv
fi

$PYTHON_CMD -m venv venv
echo "Entorno virtual creado con $PYTHON_CMD"

source venv/bin/activate
pip install --upgrade pip setuptools wheel -q
pip install -r requirements.txt -q

echo ""
echo "========================================"
echo "  Setup completado"
echo "  Ejecuta ./start.sh para iniciar"
echo "========================================"
