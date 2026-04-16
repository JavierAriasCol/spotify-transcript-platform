# Spotify Transcripts

Transcribe podcasts from audio files or Spotify episode links using OpenAI Whisper. Local processing — your audio never leaves your machine.

## Features

- **Audio file transcription** — upload MP3, WAV, M4A, FLAC, OGG
- **Spotify episode transcription** — paste a Spotify episode URL, audio is downloaded and transcribed
- **Spanish and English** support
- **VTT output** — subtitles with timestamps (max 5 words per segment)
- **Clean text output** — plain text grouped in paragraphs
- **macOS Apple Silicon** optimized

## Requirements

- macOS (Apple Silicon or Intel)
- Python 3.8+
- FFmpeg
- Internet connection (first run downloads Whisper model ~460MB)

## Quick Start

```bash
# 1. Setup (installs FFmpeg, creates venv, installs deps)
chmod +x setup.sh start.sh
./setup.sh

# 2. Run
./start.sh
```

Opens `http://localhost:3000` automatically.

## Manual Setup

```bash
# Install FFmpeg
brew install ffmpeg

# Setup backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start backend (terminal 1)
python main.py

# Start frontend (terminal 2)
cd frontend
python3 -m http.server 3000
```

## Usage

### Tab: Subir Audio
1. Select language (Spanish/English)
2. Drag or select audio file (max 30 min, 100MB)
3. Click "Transcribir Audio"
4. Download VTT or TXT

### Tab: Spotify
1. Select language
2. Paste Spotify episode URL (`https://open.spotify.com/episode/...`)
3. Click "Transcribir Episodio"
4. Download VTT or TXT

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check + tool availability |
| POST | `/transcribe` | Transcribe uploaded audio file |
| POST | `/transcribe-url` | Transcribe from Spotify episode URL |
| GET | `/download/{filename}` | Download transcription output |
| DELETE | `/cleanup` | Clean temp files |

## Tech Stack

- **Backend**: Python, FastAPI, OpenAI Whisper, spotdl, FFmpeg
- **Frontend**: Vanilla HTML/CSS/JS
- **Audio download**: spotdl (for Spotify episodes)

## Whisper Models

Change model in `backend/main.py`:

| Model | Size | Speed |
|-------|------|-------|
| tiny | ~39MB | Fastest |
| base | ~140MB | Fast |
| **small** | **~460MB** | **Default** |
| medium | ~1.5GB | Slow |
| large | ~3GB | Slowest |
