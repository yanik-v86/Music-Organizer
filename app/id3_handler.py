from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.id3 import (
    ID3NoHeaderError, TPE1, TALB, TIT2, TRCK, TDRC, TXXX, ID3
)
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from mutagen.oggflac import OggFLAC
from pathlib import Path
from typing import Optional, Any
import re

from app.models import TagSchema


def _text_looks_like_upload_spam(inner: str) -> bool:
    """True for vk.com / music for youtube / site promos in brackets — not venue names like YouTube Theater."""
    s = inner.strip()
    if not s:
        return False
    low = s.lower()
    if re.search(r"https?://", low):
        return True
    if re.search(r"\bwww\.", low):
        return True
    if re.search(r"\.(com|ru|net|org|io|tv|me|cc)\b", low):
        return True
    if re.search(r"\b(t\.me|youtu\.be)\b", low):
        return True
    strong_phrases = (
        "music for",
        "for youtube",
        "music for youtube",
        "vk.com",
        "vkontakte",
        "promo video",
        "official video",
        "lyric video",
        "official audio",
        "video clip",
        "subscribe",
        "my channel",
        "uploaded by",
        "ripped by",
    )
    if any(p in low for p in strong_phrases):
        return True
    if re.search(r"\bvk\b", low):
        return True
    # Bare platform names only with upload-ish context (avoids "YouTube Theater")
    platform = ("spotify", "soundcloud", "bandcamp", "instagram", "tiktok", "facebook", "twitter", "telegram")
    upload_hint = (
        "channel", "subscribe", "promo", "upload", "rip", "vk", "clip", "audio", "video",
        "official", "lyrics", "music",
    )
    if any(p in low for p in platform) and any(h in low for h in upload_hint):
        return True
    if "youtube" in low and re.search(
        r"youtube\s*(music|channel|video|audio|rip|link|com)?|for\s+youtube|youtube\s+for",
        low,
    ):
        return True
    return False


def strip_filename_site_noise(name: str) -> str:
    """
    Remove [brackets] and (parentheses) that contain site names / promo text
    (e.g. [vk.com music for youtube]) before parsing artist/title.
    """
    prev = None
    while prev != name:
        prev = name
        name = re.sub(
            r"\[([^\]]+)\]",
            lambda m: " " if _text_looks_like_upload_spam(m.group(1)) else m.group(0),
            name,
            flags=re.IGNORECASE,
        )
        name = re.sub(
            r"\(([^\)]+)\)",
            lambda m: " " if _text_looks_like_upload_spam(m.group(1)) else m.group(0),
            name,
            flags=re.IGNORECASE,
        )
    return re.sub(r"\s+", " ", name).strip()


def parse_filename_to_tags(filename: str) -> TagSchema:
    """
    Parse audio filename to extract tag information.
    
    Supports common patterns:
    - Artist - Title.mp3
    - Track# - Title.mp3
    - Artist - Album - Track# - Title.mp3
    - Artist - Title (Year).mp3
    - Track# Artist - Title.mp3
    """
    # Remove extension
    name = Path(filename).stem

    # Clean up common artifacts
    name = name.replace('_', ' ')
    name = strip_filename_site_noise(name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    artist = ""
    album = ""
    title = name
    track_number = 0
    year = ""
    
    # Pattern 1: "01 Artist - Title" or "01 - Artist - Title"
    match = re.match(r'^(\d{1,2})\s*[-–—]\s*(.+?)\s*[-–—]\s*(.+)$', name)
    if match:
        track_number = int(match.group(1))
        artist = match.group(2).strip()
        title = match.group(3).strip()
        return TagSchema(artist=artist, title=title, track_number=track_number)
    
    # Pattern 2: "Artist - Title" or "Artist - Album - Title"
    parts = re.split(r'\s*[-–—]\s*', name)
    if len(parts) >= 2:
        # Check if first part looks like a track number
        if re.match(r'^\d{1,2}$', parts[0].strip()):
            track_number = int(parts[0].strip())
            parts = parts[1:]
        
        if len(parts) == 2:
            artist = parts[0].strip()
            title = parts[1].strip()
        elif len(parts) >= 3:
            # Could be "Artist - Album - Title" or "Artist - Title (Year)"
            artist = parts[0].strip()
            
            # Check if last part has year
            year_match = re.search(r'\((\d{4})\)\s*$', parts[-1])
            if year_match:
                year = year_match.group(1)
                title = parts[-1][:year_match.start()].strip()
                if len(parts) == 3:
                    album = parts[1].strip()
                else:
                    album = ' - '.join(parts[1:-1]).strip()
            else:
                album = parts[1].strip()
                title = ' - '.join(parts[2:]).strip()
    
    # Pattern 3: Look for year in parentheses anywhere
    if not year:
        year_match = re.search(r'\((\d{4})\)', title)
        if year_match:
            year = year_match.group(1)
            title = title[:year_match.start()].strip()
    
    # Pattern 4: Track number at the beginning "01 Title" or "01. Title"
    if track_number == 0:
        track_match = re.match(r'^(\d{1,2})[.\s]\s*(.+)$', title)
        if track_match:
            track_number = int(track_match.group(1))
            title = track_match.group(2).strip()
    
    return TagSchema(
        artist=artist or None,
        album=album or None,
        title=title or None,
        track_number=track_number if track_number > 0 else None,
        year=year or None,
    )


def tags_are_empty(tags: TagSchema) -> bool:
    """Check if all important tag fields are empty."""
    return not any([
        tags.artist,
        tags.album,
        tags.title,
        tags.track_number,
        tags.year,
    ])


def _get_id3_tag(tags, key: str) -> str:
    """Get tag value from ID3 tags."""
    try:
        val = tags.get(key)
        if val is None:
            return ""
        if isinstance(val, list):
            return str(val[0]) if val else ""
        return str(val)
    except Exception:
        return ""


def _get_vorbis_tag(tags, key: str) -> str:
    """Get tag value from Vorbis comments (FLAC, OGG)."""
    try:
        val = tags.get(key)
        if val is None:
            return ""
        if isinstance(val, list):
            return str(val[0]) if val else ""
        return str(val)
    except (KeyError, TypeError):
        return ""


def read_tags(filepath: str) -> TagSchema:
    """Read ID3/metadata tags from an audio file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    try:
        audio = MutagenFile(filepath)
    except Exception as e:
        # Corrupted/unsupported files should not spam stdout during scan/startup.
        # Fall back to filename parsing (best-effort) rather than warning.
        parsed = parse_filename_to_tags(path.name)
        # Ensure medium defaults are present so path rendering is stable.
        if parsed.medium_format is None:
            parsed.medium_format = "Digital Media"
        if parsed.medium_number is None:
            parsed.medium_number = 1
        return parsed

    if audio is None:
        parsed = parse_filename_to_tags(path.name)
        if parsed.medium_format is None:
            parsed.medium_format = "Digital Media"
        if parsed.medium_number is None:
            parsed.medium_number = 1
        return parsed

    tags = audio.tags
    artist = ""
    album = ""
    title = ""
    track_number = 0
    year = ""
    medium_format = ""
    medium_number = 1

    # MP3 (ID3 tags)
    if isinstance(audio, MP3):
        id3_tags = tags or {}

        artist = _get_id3_tag(id3_tags, "TPE1")
        album = _get_id3_tag(id3_tags, "TALB")
        title = _get_id3_tag(id3_tags, "TIT2")
        track_raw = _get_id3_tag(id3_tags, "TRCK")
        year = _get_id3_tag(id3_tags, "TDRC")

        if track_raw:
            try:
                track_number = int(str(track_raw).split("/")[0])
            except (ValueError, IndexError):
                pass

        # Get medium info from TXXX
        for key, val in id3_tags.items():
            if isinstance(val, list):
                for v in val:
                    if hasattr(v, "desc") and v.desc == "MEDIA":
                        medium_format = str(v.text[0]) if v.text else ""
                    if hasattr(v, "desc") and v.desc == "DISCNUMBER":
                        try:
                            medium_number = int(str(v.text[0]).split("/")[0])
                        except (ValueError, IndexError):
                            pass

    # FLAC / OGG (Vorbis comments)
    elif isinstance(audio, (FLAC, OggVorbis, OggFLAC)):
        vorbis_tags = tags or {}

        artist = _get_vorbis_tag(vorbis_tags, "artist") or _get_vorbis_tag(vorbis_tags, "ARTIST")
        album = _get_vorbis_tag(vorbis_tags, "album") or _get_vorbis_tag(vorbis_tags, "ALBUM")
        title = _get_vorbis_tag(vorbis_tags, "title") or _get_vorbis_tag(vorbis_tags, "TITLE")
        track_raw = _get_vorbis_tag(vorbis_tags, "tracknumber") or _get_vorbis_tag(vorbis_tags, "TRACKNUMBER")
        year = _get_vorbis_tag(vorbis_tags, "date") or _get_vorbis_tag(vorbis_tags, "DATE") or _get_vorbis_tag(vorbis_tags, "year") or _get_vorbis_tag(vorbis_tags, "YEAR")
        medium_format = _get_vorbis_tag(vorbis_tags, "media") or _get_vorbis_tag(vorbis_tags, "MEDIA")
        
        disc_raw = _get_vorbis_tag(vorbis_tags, "discnumber") or _get_vorbis_tag(vorbis_tags, "DISCNUMBER")
        if disc_raw:
            try:
                medium_number = int(str(disc_raw).split("/")[0])
            except (ValueError, IndexError):
                pass

        if track_raw:
            try:
                track_number = int(str(track_raw).split("/")[0])
            except (ValueError, IndexError):
                pass

        # Get pictures for medium_format if not set
        if not medium_format and hasattr(audio, 'pictures') and audio.pictures:
            medium_format = "Digital Media"

    # MP4 / M4A
    elif isinstance(audio, MP4):
        mp4_tags = tags or {}

        artist = _get_mp4_tag(mp4_tags, "\xa9ART") or _get_mp4_tag(mp4_tags, "artist")
        album = _get_mp4_tag(mp4_tags, "\xa9alb") or _get_mp4_tag(mp4_tags, "album")
        title = _get_mp4_tag(mp4_tags, "\xa9nam") or _get_mp4_tag(mp4_tags, "title")
        track_raw = _get_mp4_tag(mp4_tags, "trkn") or _get_mp4_tag(mp4_tags, "tracknumber")
        year = _get_mp4_tag(mp4_tags, "\xa9day") or _get_mp4_tag(mp4_tags, "date")

        if track_raw:
            try:
                # MP4 track format: (current, total) tuple or string
                if isinstance(track_raw, tuple):
                    track_number = track_raw[0]
                else:
                    track_number = int(str(track_raw).split("/")[0])
            except (ValueError, IndexError, TypeError):
                pass

    # Generic fallback - try to get whatever is available
    else:
        if tags:
            try:
                artist = _get_generic_tag(tags, "artist")
                album = _get_generic_tag(tags, "album")
                title = _get_generic_tag(tags, "title")
                year = _get_generic_tag(tags, "year")
            except Exception:
                pass

    # Format year
    if year:
        year = str(year)[:4]

    return TagSchema(
        artist=artist or "",
        album=album or "",
        title=title or "",
        track_number=track_number,
        year=year,
        medium_format=medium_format or "Digital Media",
        medium_number=medium_number,
    )


def _get_mp4_tag(tags: Any, key: str) -> str:
    """Get tag value from MP4 tags."""
    try:
        val = tags.get(key)
        if val is None:
            return ""
        if isinstance(val, list):
            return str(val[0]) if val else ""
        if isinstance(val, (tuple,)):
            return str(val[0]) if val else ""
        return str(val)
    except (KeyError, TypeError, AttributeError):
        return ""


def _get_generic_tag(tags: Any, key: str) -> str:
    """Get tag value from generic tags."""
    try:
        # Try case-insensitive lookup
        for k in tags.keys():
            if k.lower() == key.lower():
                val = tags[k]
                if isinstance(val, list):
                    return str(val[0]) if val else ""
                return str(val)
        return ""
    except Exception:
        return ""


def write_tags(filepath: str, tags: TagSchema) -> None:
    """Write tags to an audio file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    audio = MutagenFile(filepath)
    if audio is None:
        raise ValueError(f"Unsupported file format: {filepath}")

    # MP3 (ID3 tags)
    if isinstance(audio, MP3):
        if audio.tags is None:
            audio.add_tags()
        t = audio.tags

        if tags.artist is not None:
            t.delall("TPE1")
            t.add(TPE1(encoding=3, text=tags.artist))
        if tags.album is not None:
            t.delall("TALB")
            t.add(TALB(encoding=3, text=tags.album))
        if tags.title is not None:
            t.delall("TIT2")
            t.add(TIT2(encoding=3, text=tags.title))
        # Track number: always write (0 means no track number)
        if tags.track_number is not None:
            t.delall("TRCK")
            if tags.track_number > 0:
                t.add(TRCK(encoding=3, text=str(tags.track_number)))
        if tags.year is not None:
            t.delall("TDRC")
            t.add(TDRC(encoding=3, text=str(tags.year)))
        if tags.medium_format is not None:
            t.delall("TXXX:MEDIA")
            t.add(TXXX(encoding=3, desc="MEDIA", text=tags.medium_format))
        if tags.medium_number is not None:
            t.delall("TXXX:DISCNUMBER")
            t.add(TXXX(encoding=3, desc="DISCNUMBER", text=str(tags.medium_number)))
        audio.save()

    # FLAC / OGG (Vorbis comments)
    elif isinstance(audio, (FLAC, OggVorbis, OggFLAC)):
        if audio.tags is None:
            audio.add_tags()
        t = audio.tags

        if tags.artist is not None:
            t["artist"] = tags.artist
        if tags.album is not None:
            t["album"] = tags.album
        if tags.title is not None:
            t["title"] = tags.title
        # Track number: always write (0 means no track number)
        if tags.track_number is not None:
            if tags.track_number > 0:
                t["tracknumber"] = str(tags.track_number)
            elif "tracknumber" in t:
                del t["tracknumber"]
        if tags.year is not None:
            t["date"] = tags.year
        if tags.medium_format is not None:
            t["media"] = tags.medium_format
        if tags.medium_number is not None:
            t["discnumber"] = str(tags.medium_number)
        audio.save()

    # MP4 / M4A
    elif isinstance(audio, MP4):
        if audio.tags is None:
            audio.add_tags()
        t = audio.tags

        if tags.artist is not None:
            t["\xa9ART"] = tags.artist
        if tags.album is not None:
            t["\xa9alb"] = tags.album
        if tags.title is not None:
            t["\xa9nam"] = tags.title
        # Track number: always write
        if tags.track_number is not None:
            if tags.track_number > 0:
                t["trkn"] = [(tags.track_number, 0)]
            elif "trkn" in t:
                del t["trkn"]
        if tags.year is not None:
            t["\xa9day"] = tags.year
        if tags.medium_format is not None:
            t["----:com.apple.iTunes:MEDIA"] = tags.medium_format
        if tags.medium_number is not None:
            t["----:com.apple.iTunes:DISCNUMBER"] = str(tags.medium_number)
        audio.save()

    # Generic fallback
    else:
        raise ValueError(f"Writing tags not supported for this format: {type(audio)}")
