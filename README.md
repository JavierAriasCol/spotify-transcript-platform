# Spotify Transcripts

Transcribe podcasts from audio files or Spotify episode links using mlx-whisper (Apple Silicon Metal GPU). Local processing — audio never leaves your machine.

## Features

- **Audio file transcription** — upload MP3, WAV, M4A, FLAC, OGG
- **Spotify episode transcription** — paste a Spotify episode URL; audio fetched directly from RSS feed
- **Spanish and English** support
- **Markdown output** — `.md` file with YAML frontmatter + full transcript text
- **Async job system** — background processing with live progress polling
- **MCP server** — expose transcription as tools for LLM agents (Claude, etc.)
- **macOS Apple Silicon** optimized (Metal GPU via mlx-whisper)

## Requirements

- macOS Apple Silicon (M1/M2/M3)
- Python 3.12+
- FFmpeg

## Quick Start

```bash
chmod +x setup.sh start.sh
./setup.sh
./start.sh
```

Opens `http://localhost:3000` automatically.

## Manual Setup

```bash
brew install ffmpeg

cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Terminal 1 — backend
python main.py

# Terminal 2 — frontend
cd frontend
python3 -m http.server 3000
```

## Usage

### Tab: Subir Audio
1. Select language (Spanish/English)
2. Select output folder
3. Drag or select audio file (max 30 min)
4. Click "Transcribir Audio"
5. Download `.md` transcript

### Tab: Spotify
1. Select language
2. Select output folder
3. Paste Spotify episode URL (`https://open.spotify.com/episode/...`)
4. Click "Transcribir Episodio"
5. Download `.md` transcript

## Output Format

Each transcription produces a Markdown file with YAML frontmatter:

```markdown
---
title: "Episode Title"
show: "Podcast Name"
url: "https://open.spotify.com/episode/..."
language: spanish
duration_seconds: 1423
segments: 312
transcribed_at: "2024-01-15T10:30:00"
transcription_time_seconds: 45
---

Full transcript text here as a single paragraph...
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/resolve?url=...` | Get episode title + show from Spotify URL |
| POST | `/transcribe` | Transcribe uploaded audio file |
| POST | `/transcribe-url` | Start async Spotify transcription job |
| GET | `/jobs/{job_id}` | Poll job status + progress |
| GET | `/download/{filename}` | Download `.md` output |
| DELETE | `/cleanup` | Clean temp files |

## MCP Server

Exposes transcription as MCP tools for LLM agents:

```bash
cd backend
source venv/bin/activate
python mcp_server.py
```

### Tools

**`resolve_episode`** — fetch episode metadata (title, show, duration) from a Spotify URL.

**`transcribe_episode`** — download, transcribe, and save `.md` to a given path. Returns saved path, duration, and segment count.

### Claude Desktop Config

```json
{
  "mcpServers": {
    "spotify-transcript": {
      "command": "/path/to/backend/venv/bin/python",
      "args": ["/path/to/backend/mcp_server.py"]
    }
  }
}
```

## How Spotify Download Works

No third-party downloaders (spotdl, yt-dlp). Pure RSS:

1. Scrape Spotify episode page for title + show name
2. Query iTunes Search API for podcast RSS feed
3. Match episode title in RSS feed
4. Download MP3 directly from `<enclosure>` URL

## Tech Stack

- **Backend**: Python, FastAPI, mlx-whisper, FFmpeg
- **Frontend**: Vanilla HTML/CSS/JS
- **MCP**: `mcp` Python SDK
- **Audio source**: iTunes API + direct RSS MP3 download

## Whisper Models

Change model in `backend/core.py` (`mlx_whisper.transcribe` call):

| Model | HF Repo | Speed |
|-------|---------|-------|
| tiny | `mlx-community/whisper-tiny-mlx` | Fastest |
| base | `mlx-community/whisper-base-mlx` | Fast |
| **small** | **`mlx-community/whisper-small-mlx`** | **Default** |
| medium | `mlx-community/whisper-medium-mlx` | Slow |
| large | `mlx-community/whisper-large-v3-mlx` | Slowest |
