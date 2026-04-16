import html
import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, quote
from urllib.request import urlopen, Request

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import mlx_whisper
import uvicorn

app = FastAPI(title="Spotify Transcript API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "null"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = Path("temp_uploads")
TEMP_DIR.mkdir(exist_ok=True)

_whisper_lock = threading.Lock()
print("mlx-whisper listo (Metal GPU)")

# RSS cache: show_name -> (rss_url, timestamp)
_rss_cache: dict[str, tuple[str, float]] = {}
_RSS_CACHE_TTL = 3600  # 1 hour

# Job store: job_id -> dict
_jobs: dict[str, dict] = {}


def _set_job(job_id: str, **kwargs):
    _jobs[job_id].update(kwargs)


def check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_spotify_episode_metadata(episode_url: str) -> dict:
    """Scrape Spotify episode page for show name, episode title, and duration."""
    req = Request(episode_url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as resp:
        page_html = resp.read().decode("utf-8")

    title = ""
    show_name = ""
    duration = 0

    for match in re.finditer(r'<meta\s+(?:name|property)="([^"]+)"\s+content="([^"]*)"', page_html):
        key, val = match.group(1), match.group(2)
        if key == "og:title":
            title = val
        elif key == "og:description":
            if "·" in val:
                show_name = val.split("·")[0].strip()
        elif key == "music:duration":
            duration = int(val)

    if not title:
        raise Exception("No se pudo obtener info del episodio de Spotify")

    return {"title": title, "show_name": show_name, "duration": duration}


def find_rss_feed(show_name: str) -> str:
    """Find podcast RSS feed URL via iTunes Search API. Caches results for 1 hour."""
    cached = _rss_cache.get(show_name)
    if cached:
        rss_url, ts = cached
        if time.time() - ts < _RSS_CACHE_TTL:
            print(f"[rss-cache] HIT: {show_name}")
            return rss_url

    search_url = f"https://itunes.apple.com/search?term={quote(show_name)}&media=podcast&limit=5"
    req = Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    for result in data.get("results", []):
        if result.get("feedUrl"):
            rss_url = result["feedUrl"]
            _rss_cache[show_name] = (rss_url, time.time())
            print(f"[rss-cache] MISS, cached: {show_name} -> {rss_url}")
            return rss_url

    raise Exception(f"No se encontro RSS feed para: {show_name}")


def find_episode_audio_url(rss_url: str, episode_title: str) -> str:
    """Parse RSS feed and find episode MP3 URL by matching title."""
    req = Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        rss_content = resp.read().decode("utf-8")

    root = ET.fromstring(rss_content)

    target = re.sub(r'[^\w\s]', '', html.unescape(episode_title).lower()).strip()

    for item in root.findall('.//item'):
        item_title = item.find('title')
        if item_title is None or not item_title.text:
            continue

        candidate = re.sub(r'[^\w\s]', '', html.unescape(item_title.text).lower()).strip()
        if target in candidate or candidate in target:
            enclosure = item.find('enclosure')
            if enclosure is not None:
                url = enclosure.get('url', '')
                return url.replace('&amp;', '&')

    raise Exception(f"Episodio no encontrado en RSS feed. Titulo buscado: {episode_title}")


def get_media_duration(media_path: str):
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', media_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)

        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'audio':
                duration = float(stream.get('duration', 0))
                if duration > 0:
                    return duration

        duration = float(data.get('format', {}).get('duration', 0))
        return duration

    except Exception as e:
        raise Exception(f"Error obteniendo duracion: {str(e)}")


def extract_audio(input_path: str, audio_path: str):
    try:
        if not check_ffmpeg():
            raise Exception("FFmpeg no esta instalado. Instala con: brew install ffmpeg")

        duration = get_media_duration(input_path)

        if duration > 1800:
            raise Exception("El audio debe durar menos de 30 minutos")

        cmd = [
            'ffmpeg', '-i', input_path, '-acodec', 'pcm_s16le',
            '-ar', '16000', '-ac', '1', '-y', audio_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"Error procesando audio con FFmpeg: {result.stderr}")

        return duration

    except Exception:
        raise


def transcribe_audio(audio_path: str, language: str):
    try:
        lang_map = {"spanish": "es", "english": "en"}
        whisper_lang = lang_map.get(language.lower(), "es")
        with _whisper_lock:
            result = mlx_whisper.transcribe(
                audio_path,
                path_or_hf_repo="mlx-community/whisper-small-mlx",
                language=whisper_lang,
                condition_on_previous_text=False,
            )
        return result
    except Exception as e:
        raise Exception(f"Error en transcripcion con Whisper: {str(e)}")


def _yaml_str(s: str) -> str:
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def create_markdown_output(transcription_result, output_path: str, metadata: dict):
    segments = transcription_result['segments']
    lines = [
        "---",
        f"title: {_yaml_str(metadata.get('title', ''))}",
    ]
    if metadata.get("show"):
        lines.append(f"show: {_yaml_str(metadata['show'])}")
    if metadata.get("url"):
        lines.append(f"url: {_yaml_str(metadata['url'])}")
    lines += [
        f"language: {metadata.get('language', '')}",
        f"duration_seconds: {round(metadata.get('duration', 0))}",
        f"segments: {len(segments)}",
        f"transcribed_at: {_yaml_str(metadata.get('transcribed_at', ''))}",
        f"transcription_time_seconds: {round(metadata.get('transcription_time', 0))}",
        "---",
        "",
        " ".join(s['text'].strip() for s in segments if s['text'].strip()),
    ]
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))


def _run_transcribe_job(job_id: str, url: str, language: str):
    """Background thread: resolve → download → transcribe."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    downloaded_path = None
    output_filename = f"transcription_{timestamp}.md"
    output_path = TEMP_DIR / output_filename

    try:
        # Step 1: Resolve Spotify metadata
        _set_job(job_id, status="resolving", progress=5, message="Obteniendo info del episodio...")
        metadata = get_spotify_episode_metadata(url)

        if not metadata["show_name"]:
            raise Exception("No se pudo identificar el podcast de este episodio")

        # Step 2: Find RSS (cached)
        _set_job(job_id, status="resolving", progress=15, message="Buscando RSS feed...")
        rss_url = find_rss_feed(metadata["show_name"])

        # Step 3: Find episode audio URL in RSS
        _set_job(job_id, status="resolving", progress=25, message="Localizando episodio en RSS...")
        audio_url = find_episode_audio_url(rss_url, metadata["title"])

        # Step 4: Download
        _set_job(job_id, status="downloading", progress=30, message="Descargando audio...")
        dl_path = TEMP_DIR / f"spotify_{timestamp}.mp3"
        req = Request(audio_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=300) as resp:
            total = int(resp.headers.get('Content-Length', 0))
            downloaded = 0
            with open(dl_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = 30 + int((downloaded / total) * 25)
                        _set_job(job_id, progress=pct,
                                 message=f"Descargando... {downloaded // (1024*1024)}MB / {total // (1024*1024)}MB")

        if not dl_path.exists() or dl_path.stat().st_size == 0:
            raise Exception("Error descargando audio del episodio")
        downloaded_path = str(dl_path)

        # Step 5: Check duration
        duration = get_media_duration(downloaded_path)
        if duration > 1800:
            raise Exception("El episodio debe durar menos de 30 minutos")

        # Step 6: Transcribe directly from MP3
        _set_job(job_id, status="transcribing", progress=60, message="Transcribiendo con Whisper...")
        t_start = time.time()
        transcription = transcribe_audio(downloaded_path, language)
        transcription_time = time.time() - t_start

        # Step 7: Write output
        _set_job(job_id, status="transcribing", progress=95, message="Generando transcripcion...")
        create_markdown_output(transcription, str(output_path), {
            "title": metadata.get("title", ""),
            "show": metadata.get("show_name", ""),
            "url": url,
            "language": language,
            "duration": duration,
            "transcribed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "transcription_time": transcription_time,
        })

        _set_job(job_id,
                 status="done",
                 progress=100,
                 message="Transcripcion completada",
                 result={
                     "duration": round(duration, 2),
                     "language": language,
                     "original_segments_count": len(transcription['segments']),
                     "download_url": f"/download/{output_filename}",
                     "episode_title": metadata.get("title", ""),
                     "show_name": metadata.get("show_name", ""),
                 })

    except Exception as e:
        _set_job(job_id, status="error", progress=0, message=str(e), error=str(e))

    finally:
        if downloaded_path and os.path.exists(downloaded_path):
            os.remove(downloaded_path)


@app.get("/resolve")
async def resolve_episode(url: str):
    if 'open.spotify.com/episode' not in url:
        raise HTTPException(status_code=400, detail="URL invalida")
    metadata = get_spotify_episode_metadata(url)
    return {"title": metadata["title"], "show": metadata["show_name"]}


@app.get("/")
async def root():
    return {
        "message": "Spotify Transcript API",
        "status": "running",
        "version": "1.0.0",
        "platform": platform.system(),
        "architecture": platform.machine(),
        "rss_discovery": True,
        "ffmpeg_available": check_ffmpeg()
    }


@app.post("/transcribe")
async def transcribe_media(
    file: UploadFile = File(...),
    language: str = Form(...),
):
    if not (file.content_type.startswith('audio/') or file.content_type.startswith('video/')):
        raise HTTPException(status_code=400, detail="El archivo debe ser un audio")

    if language.lower() not in ['spanish', 'english']:
        raise HTTPException(status_code=400, detail="Idioma debe ser 'spanish' o 'english'")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    input_filename = f"input_{timestamp}_{file.filename}"
    audio_filename = f"audio_{timestamp}.wav"
    output_filename = f"transcription_{timestamp}.md"

    input_path = TEMP_DIR / input_filename
    audio_path = TEMP_DIR / audio_filename
    output_path = TEMP_DIR / output_filename

    try:
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        duration = extract_audio(str(input_path), str(audio_path))
        t_start = time.time()
        transcription = transcribe_audio(str(audio_path), language)
        transcription_time = time.time() - t_start

        create_markdown_output(transcription, str(output_path), {
            "title": file.filename,
            "language": language,
            "duration": duration,
            "transcribed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "transcription_time": transcription_time,
        })

        return {
            "duration": round(duration, 2),
            "language": language,
            "original_segments_count": len(transcription['segments']),
            "download_url": f"/download/{output_filename}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inesperado: {str(e)}")

    finally:
        for temp_file in [input_path, audio_path]:
            if temp_file.exists():
                temp_file.unlink()


@app.post("/transcribe-url")
async def transcribe_from_url(
    url: str = Form(...),
    language: str = Form(...),
):
    if 'open.spotify.com/episode' not in url:
        raise HTTPException(status_code=400, detail="URL invalida. Debe ser un enlace de episodio de Spotify")

    if language.lower() not in ['spanish', 'english']:
        raise HTTPException(status_code=400, detail="Idioma debe ser 'spanish' o 'english'")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "progress": 0, "message": "Iniciando...", "result": None, "error": None}

    t = threading.Thread(
        target=_run_transcribe_job,
        args=(job_id, url, language.lower()),
        daemon=True
    )
    t.start()

    return {"job_id": job_id, "status": "pending"}


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return job


@app.get("/download/{filename}")
async def download_transcription(filename: str):
    file_path = TEMP_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    media_type = 'text/markdown'

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type
    )


@app.delete("/cleanup")
async def cleanup_temp_files():
    try:
        count = 0
        for file_path in TEMP_DIR.glob("*"):
            if file_path.is_file():
                file_path.unlink()
                count += 1

        return {"message": f"Se eliminaron {count} archivos temporales"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error limpiando archivos: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
