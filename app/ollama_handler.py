"""
LLM-based metadata extraction using Ollama.
Analyzes filenames to extract artist, title, album, year using local LLM.
"""
import json
import re
import httpx
from pathlib import Path

from app.config import config, get_httpx_client_kwargs
from app.id3_handler import strip_filename_site_noise


def get_ollama_config() -> tuple[str, str]:
    """Get Ollama configuration from config."""
    if not hasattr(config, 'ollama') or not config.ollama:
        return "", ""

    url = config.ollama.url or ""
    model = config.ollama.model or "tinyllama"
    return url, model


# JSON schema hint for Ollama native JSON mode (short = faster generation)
_OLLAMA_JSON_SCHEMA = """{"artist":"","album":"","title":"","year":"","track_number":0}"""


def _normalize_filename(filename: str) -> str:
    stem = Path(filename).stem
    stem = stem.replace("_", " ")
    stem = strip_filename_site_noise(stem)
    return re.sub(r"\s+", " ", stem).strip()


def _extract_json_payload(text: str) -> dict | None:
    if not text:
        return None
    raw = text.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _coerce_metadata(data: dict | None) -> dict:
    data = data or {}
    try:
        track_number = int(data.get("track_number", 0) or 0)
    except Exception:
        track_number = 0
    return {
        "artist": str(data.get("artist", "") or "").strip(),
        "album": str(data.get("album", "") or "").strip(),
        "title": str(data.get("title", "") or "").strip(),
        "track_number": track_number,
        "year": str(data.get("year", "") or "").strip(),
    }


def _merge_missing_fields(primary: dict, fallback: dict) -> dict:
    merged = dict(primary or {})
    fb = fallback or {}
    for key in ("artist", "album", "title", "year"):
        if not str(merged.get(key, "") or "").strip():
            merged[key] = str(fb.get(key, "") or "").strip()
    try:
        track_primary = int(merged.get("track_number", 0) or 0)
    except Exception:
        track_primary = 0
    if track_primary <= 0:
        try:
            merged["track_number"] = int(fb.get("track_number", 0) or 0)
        except Exception:
            merged["track_number"] = 0
    return merged


def _heuristic_metadata_from_filename(filename: str) -> dict:
    clean = _normalize_filename(filename)
    parts = [p.strip(" -–—|'\"") for p in re.split(r"\s+\|\s+", clean) if p.strip(" -–—|'\"")]
    if len(parts) >= 2:
        return {
            "artist": parts[0],
            "album": "",
            "title": " | ".join(parts[1:]),
            "track_number": 0,
            "year": "",
        }
    dash = [p.strip(" -–—|'\"") for p in re.split(r"\s*[-–—]\s*", clean) if p.strip(" -–—|'\"")]
    if len(dash) >= 2:
        return {
            "artist": dash[0],
            "album": "",
            "title": " - ".join(dash[1:]),
            "track_number": 0,
            "year": "",
        }
    return {"artist": "", "album": "", "title": clean, "track_number": 0, "year": ""}


async def extract_tags_from_filename(filename: str) -> dict:
    """
    Use Ollama to generate metadata from filename.
    Analyzes filename pattern and extracts artist, album, title, year, track number.
    """
    if not config.ollama.url:
        return None
    
    clean_filename = _normalize_filename(filename)
    print(f"Clean filename: {clean_filename}")
    print(f"Filename: {filename}")
    
    prompt = f"""You are a specialized music metadata extraction system. Parse the filename and return structured metadata.

FILENAME: {clean_filename}

EXTRACTION RULES:
1. ARTIST & TITLE: Extract these as the core entities
2. ALBUM: Identify album name if clearly present
3. TRACK NUMBER: Detect patterns like "01.", "1 -", "track01", etc.
4. YEAR: Look for 4-digit numbers in parentheses (2024), brackets [2024], or after dash

CLEANING PROTOCOLS:
- Strip all platform names: YouTube, VK, Spotify, Apple Music, SoundCloud, Tidal, Deezer
- Remove video descriptors: "official video", "lyric video", "music video", "audio", "HD", "4K", "live"
- Eliminate file markers: "[www]", "WEB", "320kbps", "FLAC", "MP3"
- Remove social media handles and URLs

OUTPUT FORMAT:
Return valid JSON only. No explanations, no markdown wrappers.
Fields: artist, album, title, track_number (integer, default 0), year (string)

FALLBACK BEHAVIOR:
Even for mix/playlist filenames, extract the most meaningful artist and title possible.

Example:
Input: "02. Coldplay - Yellow (2000) [Official Audio].mp3"
Output: {{"artist": "Coldplay", "album": "", "title": "Yellow", "track_number": 2, "year": "2000"}}

JSON:"""

    try:
        async with httpx.AsyncClient(timeout=12.0, **get_httpx_client_kwargs(config.ollama.url)) as client:
            response = await client.post(
                f"{config.ollama.url}/api/generate",
                json={
                    "model": config.ollama.model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result.get("response", "")
                metadata = _coerce_metadata(_extract_json_payload(content))
                fallback = _heuristic_metadata_from_filename(clean_filename)
                metadata = _merge_missing_fields(metadata, fallback)
                if fallback["artist"] or fallback["title"]:
                    return metadata
                return None
            else:
                return None
    except Exception as e:
        print(f"Ollama error: {e}")
        fallback = _heuristic_metadata_from_filename(filename)
        return fallback if (fallback["artist"] or fallback["title"]) else None



async def is_ollama_available() -> bool:
    """Check if Ollama is available and configured."""
    url, model = get_ollama_config()

    if not url or not model:
        return False

    try:
        async with httpx.AsyncClient(timeout=5.0, **get_httpx_client_kwargs(url)) as client:
            response = await client.get(f"{url.rstrip('/')}/api/tags")
            return response.status_code == 200
    except Exception:
        return False
