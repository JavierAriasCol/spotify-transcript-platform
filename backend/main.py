import html
import json
import os
import platform
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from urllib.request import urlopen, Request

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn
import whisper

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

print("Cargando modelo Whisper...")
model = whisper.load_model("small")
print("Modelo Whisper 'small' cargado exitosamente")


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
            # Format: "Show Name · Episode"
            if "·" in val:
                show_name = val.split("·")[0].strip()
        elif key == "music:duration":
            duration = int(val)

    if not title:
        raise HTTPException(status_code=400, detail="No se pudo obtener info del episodio de Spotify")

    return {"title": title, "show_name": show_name, "duration": duration}


def find_rss_feed(show_name: str) -> str:
    """Find podcast RSS feed URL via iTunes Search API."""
    from urllib.parse import quote
    search_url = f"https://itunes.apple.com/search?term={quote(show_name)}&media=podcast&limit=5"
    req = Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    for result in data.get("results", []):
        if result.get("feedUrl"):
            return result["feedUrl"]

    raise HTTPException(status_code=404, detail=f"No se encontro RSS feed para: {show_name}")


def find_episode_audio_url(rss_url: str, episode_title: str) -> str:
    """Parse RSS feed and find episode MP3 URL by matching title."""
    req = Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        rss_content = resp.read().decode("utf-8")

    root = ET.fromstring(rss_content)

    # Normalize target title for comparison (unescape HTML entities first)
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

    raise HTTPException(
        status_code=404,
        detail=f"Episodio no encontrado en RSS feed. Titulo buscado: {episode_title}"
    )


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
        raise HTTPException(status_code=500, detail=f"Error obteniendo duracion: {str(e)}")


def extract_audio(input_path: str, audio_path: str):
    try:
        if not check_ffmpeg():
            raise HTTPException(
                status_code=500,
                detail="FFmpeg no esta instalado. Instala con: brew install ffmpeg"
            )

        duration = get_media_duration(input_path)

        if duration > 1800:
            raise HTTPException(status_code=400, detail="El audio debe durar menos de 30 minutos")

        cmd = [
            'ffmpeg', '-i', input_path, '-acodec', 'pcm_s16le',
            '-ar', '16000', '-ac', '1', '-y', audio_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Error procesando audio con FFmpeg: {result.stderr}"
            )

        return duration

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando archivo: {str(e)}")


def download_spotify_episode(url: str, output_dir: str) -> tuple[str, dict]:
    """Download Spotify episode via RSS feed discovery. Returns (file_path, metadata)."""
    if 'open.spotify.com/episode' not in url:
        raise HTTPException(
            status_code=400,
            detail="URL invalida. Debe ser un enlace de episodio de Spotify (open.spotify.com/episode/...)"
        )

    # Step 1: Get episode metadata from Spotify page
    metadata = get_spotify_episode_metadata(url)

    if not metadata["show_name"]:
        raise HTTPException(status_code=400, detail="No se pudo identificar el podcast de este episodio")

    # Step 2: Find RSS feed via iTunes
    rss_url = find_rss_feed(metadata["show_name"])

    # Step 3: Find episode audio URL in RSS
    audio_url = find_episode_audio_url(rss_url, metadata["title"])

    # Step 4: Download the audio file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"spotify_{timestamp}.mp3")

    req = Request(audio_url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=300) as resp:
        with open(output_path, "wb") as f:
            shutil.copyfileobj(resp, f)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise HTTPException(status_code=500, detail="Error descargando audio del episodio")

    return output_path, metadata


def transcribe_audio(audio_path: str, language: str):
    try:
        lang_map = {
            "spanish": "es",
            "english": "en"
        }
        whisper_lang = lang_map.get(language.lower(), "es")

        result = model.transcribe(audio_path, language=whisper_lang, fp16=False)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en transcripcion con Whisper: {str(e)}")


def create_vtt_file(transcription_result, output_path: str):
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("WEBVTT\n\n")

            segment_counter = 1

            for segment in transcription_result['segments']:
                start_time_seconds = segment['start']
                end_time_seconds = segment['end']
                text = segment['text'].strip()

                words = text.split()

                if len(words) <= 5:
                    f.write(f"{segment_counter}\n")
                    f.write(f"{format_timestamp(start_time_seconds)} --> {format_timestamp(end_time_seconds)}\n")
                    f.write(f"{text}\n\n")
                    segment_counter += 1
                else:
                    segment_duration = end_time_seconds - start_time_seconds
                    total_words = len(words)

                    for i in range(0, total_words, 5):
                        sub_words = words[i:i+5]
                        sub_text = ' '.join(sub_words)
                        words_processed = i
                        words_in_subsegment = len(sub_words)

                        sub_start = start_time_seconds + (words_processed / total_words) * segment_duration
                        sub_end = start_time_seconds + ((words_processed + words_in_subsegment) / total_words) * segment_duration

                        f.write(f"{segment_counter}\n")
                        f.write(f"{format_timestamp(sub_start)} --> {format_timestamp(sub_end)}\n")
                        f.write(f"{sub_text}\n\n")
                        segment_counter += 1

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creando archivo VTT: {str(e)}")


def create_clean_transcription(transcription_result, output_path: str):
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            full_text = ""
            for segment in transcription_result['segments']:
                text = segment['text'].strip()
                if text:
                    full_text += text + " "

            full_text = full_text.strip()
            sentences = re.split(r'[.!?]+', full_text)

            paragraphs = []
            current_paragraph = []

            for sentence in sentences:
                sentence = sentence.strip()
                if sentence:
                    current_paragraph.append(sentence)
                    if len(current_paragraph) >= 3 or len(sentence) > 100:
                        paragraphs.append('. '.join(current_paragraph) + '.')
                        current_paragraph = []

            if current_paragraph:
                paragraphs.append('. '.join(current_paragraph) + '.')

            if not paragraphs:
                paragraphs = [full_text]

            for i, paragraph in enumerate(paragraphs):
                f.write(paragraph)
                if i < len(paragraphs) - 1:
                    f.write('\n')

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creando transcripcion limpia: {str(e)}")


def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


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
    transcription_type: str = Form("vtt")
):
    if not (file.content_type.startswith('audio/') or file.content_type.startswith('video/')):
        raise HTTPException(status_code=400, detail="El archivo debe ser un audio")

    if language.lower() not in ['spanish', 'english']:
        raise HTTPException(status_code=400, detail="Idioma debe ser 'spanish' o 'english'")

    if transcription_type.lower() not in ['vtt', 'clean']:
        raise HTTPException(status_code=400, detail="Tipo de transcripcion debe ser 'vtt' o 'clean'")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    input_filename = f"input_{timestamp}_{file.filename}"
    audio_filename = f"audio_{timestamp}.wav"

    if transcription_type.lower() == "clean":
        output_filename = f"transcription_{timestamp}.txt"
    else:
        output_filename = f"transcription_{timestamp}.vtt"

    input_path = TEMP_DIR / input_filename
    audio_path = TEMP_DIR / audio_filename
    output_path = TEMP_DIR / output_filename

    try:
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        duration = extract_audio(str(input_path), str(audio_path))
        transcription = transcribe_audio(str(audio_path), language)

        if transcription_type.lower() == "clean":
            create_clean_transcription(transcription, str(output_path))
        else:
            create_vtt_file(transcription, str(output_path))

        return {
            "message": "Transcripcion completada exitosamente",
            "duration": round(duration, 2),
            "language": language,
            "transcription_type": transcription_type.lower(),
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
    transcription_type: str = Form("vtt")
):
    if language.lower() not in ['spanish', 'english']:
        raise HTTPException(status_code=400, detail="Idioma debe ser 'spanish' o 'english'")

    if transcription_type.lower() not in ['vtt', 'clean']:
        raise HTTPException(status_code=400, detail="Tipo de transcripcion debe ser 'vtt' o 'clean'")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_filename = f"audio_{timestamp}.wav"

    if transcription_type.lower() == "clean":
        output_filename = f"transcription_{timestamp}.txt"
    else:
        output_filename = f"transcription_{timestamp}.vtt"

    audio_path = TEMP_DIR / audio_filename
    output_path = TEMP_DIR / output_filename
    downloaded_path = None

    try:
        downloaded_path, metadata = download_spotify_episode(url, str(TEMP_DIR))

        duration = get_media_duration(downloaded_path)
        if duration > 1800:
            raise HTTPException(status_code=400, detail="El episodio debe durar menos de 30 minutos")

        cmd = [
            'ffmpeg', '-i', downloaded_path, '-acodec', 'pcm_s16le',
            '-ar', '16000', '-ac', '1', '-y', str(audio_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Error convirtiendo audio: {result.stderr[:500]}")

        transcription = transcribe_audio(str(audio_path), language)

        if transcription_type.lower() == "clean":
            create_clean_transcription(transcription, str(output_path))
        else:
            create_vtt_file(transcription, str(output_path))

        return {
            "message": "Transcripcion desde Spotify completada",
            "duration": round(duration, 2),
            "language": language,
            "transcription_type": transcription_type.lower(),
            "original_segments_count": len(transcription['segments']),
            "download_url": f"/download/{output_filename}",
            "source": "spotify",
            "episode_title": metadata.get("title", ""),
            "show_name": metadata.get("show_name", "")
        }

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Timeout descargando episodio. Intenta de nuevo.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inesperado: {str(e)}")

    finally:
        if audio_path.exists():
            audio_path.unlink()
        if downloaded_path and os.path.exists(downloaded_path):
            os.remove(downloaded_path)


@app.get("/download/{filename}")
async def download_transcription(filename: str):
    file_path = TEMP_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    if filename.lower().endswith('.txt'):
        media_type = 'text/plain'
    else:
        media_type = 'text/vtt'

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
