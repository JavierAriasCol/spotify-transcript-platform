import html
import json
import re
import subprocess
import threading
import time
from urllib.parse import quote
from urllib.request import urlopen, Request
import xml.etree.ElementTree as ET

import mlx_whisper

_whisper_lock = threading.Lock()

# RSS cache: show_name -> (rss_url, timestamp)
_rss_cache: dict[str, tuple[str, float]] = {}
_RSS_CACHE_TTL = 3600


def get_spotify_episode_metadata(episode_url: str) -> dict:
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
    cached = _rss_cache.get(show_name)
    if cached:
        rss_url, ts = cached
        if time.time() - ts < _RSS_CACHE_TTL:
            return rss_url

    search_url = f"https://itunes.apple.com/search?term={quote(show_name)}&media=podcast&limit=5"
    req = Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    for result in data.get("results", []):
        if result.get("feedUrl"):
            rss_url = result["feedUrl"]
            _rss_cache[show_name] = (rss_url, time.time())
            return rss_url

    raise Exception(f"No se encontro RSS feed para: {show_name}")


def find_episode_audio_url(rss_url: str, episode_title: str) -> str:
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


def get_media_duration(media_path: str) -> float:
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

    return float(data.get('format', {}).get('duration', 0))


def transcribe_audio(audio_path: str, language: str) -> dict:
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


def _yaml_str(s: str) -> str:
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def create_markdown_output(transcription_result: dict, output_path: str, metadata: dict):
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
