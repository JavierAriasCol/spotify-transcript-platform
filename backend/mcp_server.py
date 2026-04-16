"""
Spotify Transcript MCP Server
Exposes two tools for LLMs:
  - resolve_episode: get episode title and show from a Spotify URL
  - transcribe_episode: download, transcribe, and save .md to a given path
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from core import (
    get_spotify_episode_metadata,
    find_rss_feed,
    find_episode_audio_url,
    get_media_duration,
    transcribe_audio,
    create_markdown_output,
)

server = Server("spotify-transcript")

MAX_DURATION_SECONDS = 1800  # 30 min


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="resolve_episode",
            description=(
                "Fetch metadata for a Spotify podcast episode: title, show name, and duration. "
                "Use this before transcribing to confirm the episode details."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "spotify_url": {
                        "type": "string",
                        "description": "Full Spotify episode URL, e.g. https://open.spotify.com/episode/..."
                    }
                },
                "required": ["spotify_url"],
            },
        ),
        Tool(
            name="transcribe_episode",
            description=(
                "Download and transcribe a Spotify podcast episode. "
                "Saves a Markdown file with YAML frontmatter and full transcript text. "
                "Episode must be under 30 minutes. "
                "Returns the path where the file was saved plus duration and segment count."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "spotify_url": {
                        "type": "string",
                        "description": "Full Spotify episode URL"
                    },
                    "output_path": {
                        "type": "string",
                        "description": (
                            "Absolute path where the .md transcript will be saved. "
                            "Parent directories are created automatically. "
                            "Example: /Users/javier/Documents/notes/episode-title.md"
                        )
                    },
                    "language": {
                        "type": "string",
                        "enum": ["spanish", "english"],
                        "description": "Spoken language of the episode. Defaults to 'english' if not specified."
                    },
                },
                "required": ["spotify_url", "output_path"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "resolve_episode":
        return await _resolve_episode(arguments)
    elif name == "transcribe_episode":
        return await _transcribe_episode(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def _resolve_episode(arguments: dict) -> list[TextContent]:
    url = arguments["spotify_url"]
    if "open.spotify.com/episode" not in url:
        raise ValueError("Invalid URL: must be a Spotify episode link")

    meta = await asyncio.to_thread(get_spotify_episode_metadata, url)
    return [TextContent(type="text", text=json.dumps({
        "title":     meta["title"],
        "show":      meta["show_name"],
        "duration_seconds": meta["duration"],
    }, ensure_ascii=False))]


async def _transcribe_episode(arguments: dict) -> list[TextContent]:
    url       = arguments["spotify_url"]
    out_path  = Path(arguments["output_path"])
    language  = arguments.get("language", "english")

    if "open.spotify.com/episode" not in url:
        raise ValueError("Invalid URL: must be a Spotify episode link")
    if language not in ("spanish", "english"):
        raise ValueError("language must be 'spanish' or 'english'")

    # Resolve metadata
    meta = await asyncio.to_thread(get_spotify_episode_metadata, url)

    if not meta["show_name"]:
        raise ValueError("Could not identify the podcast show from this episode URL")

    # Find RSS + audio URL
    rss_url   = await asyncio.to_thread(find_rss_feed, meta["show_name"])
    audio_url = await asyncio.to_thread(find_episode_audio_url, rss_url, meta["title"])

    # Download to temp file
    tmp = Path("/tmp") / f"mcp_spotify_{int(time.time())}.mp3"
    try:
        def _download():
            req = Request(audio_url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=300) as resp:
                tmp.write_bytes(resp.read())

        await asyncio.to_thread(_download)

        if not tmp.exists() or tmp.stat().st_size == 0:
            raise RuntimeError("Audio download failed or produced empty file")

        # Duration check
        duration = await asyncio.to_thread(get_media_duration, str(tmp))
        if duration > MAX_DURATION_SECONDS:
            raise ValueError(f"Episode is {round(duration/60, 1)} min — limit is 30 min")

        # Transcribe
        t0 = time.time()
        result = await asyncio.to_thread(transcribe_audio, str(tmp), language)
        transcription_time = time.time() - t0

        # Write output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            create_markdown_output,
            result,
            str(out_path),
            {
                "title":             meta["title"],
                "show":              meta["show_name"],
                "url":               url,
                "language":          language,
                "duration":          duration,
                "transcribed_at":    datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "transcription_time": transcription_time,
            }
        )

    finally:
        if tmp.exists():
            tmp.unlink()

    return [TextContent(type="text", text=json.dumps({
        "saved_to":              str(out_path),
        "episode_title":         meta["title"],
        "show":                  meta["show_name"],
        "duration_seconds":      round(duration),
        "segments":              len(result["segments"]),
        "transcription_time_s":  round(transcription_time),
    }, ensure_ascii=False))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
