import os
import platform
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

from core import (
    get_spotify_episode_metadata,
    find_rss_feed,
    find_episode_audio_url,
    get_media_duration,
    transcribe_audio,
    create_markdown_output,
)

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

print("mlx-whisper listo (Metal GPU)")

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


def extract_audio(input_path: str, audio_path: str):
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


def _run_transcribe_job(job_id: str, url: str, language: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    downloaded_path = None
    output_filename = f"transcription_{timestamp}.md"
    output_path = TEMP_DIR / output_filename

    try:
        _set_job(job_id, status="resolving", progress=5, message="Obteniendo info del episodio...")
        metadata = get_spotify_episode_metadata(url)

        if not metadata["show_name"]:
            raise Exception("No se pudo identificar el podcast de este episodio")

        _set_job(job_id, status="resolving", progress=15, message="Buscando RSS feed...")
        rss_url = find_rss_feed(metadata["show_name"])

        _set_job(job_id, status="resolving", progress=25, message="Localizando episodio en RSS...")
        audio_url = find_episode_audio_url(rss_url, metadata["title"])

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

        duration = get_media_duration(downloaded_path)
        if duration > 1800:
            raise Exception("El episodio debe durar menos de 30 minutos")

        _set_job(job_id, status="transcribing", progress=60, message="Transcribiendo con Whisper...")
        t_start = time.time()
        transcription = transcribe_audio(downloaded_path, language)
        transcription_time = time.time() - t_start

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
        "ffmpeg_available": check_ffmpeg(),
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
    return FileResponse(path=str(file_path), filename=filename, media_type='text/markdown')


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
