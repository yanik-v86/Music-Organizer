import json
import os
import re
import shutil
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from mutagen.oggflac import OggFLAC

from app.config import config
from app.audio_utils import probe_audio_info
from app.models import AudioFile, OperationLog
from sqlalchemy.orm import Session


def sanitize_filename(name: str) -> str:
    """Remove characters unsafe for filesystem paths."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.strip(". ")
    return name


def extract_cover_art(audio_path: str) -> bytes | None:
    """Extract cover art image data from audio file."""
    try:
        audio = MutagenFile(audio_path)
        if audio is None:
            return None

        tags = audio.tags
        if tags is None:
            # Check for pictures in FLAC/OGG even without tags
            if isinstance(audio, (FLAC, OggVorbis, OggFLAC)) and hasattr(audio, 'pictures') and audio.pictures:
                return audio.pictures[0].data
            return None

        # MP3 (ID3) - APIC frame
        if isinstance(audio, MP3) and isinstance(tags, ID3):
            for key in tags.keys():
                if key.startswith("APIC"):
                    apic = tags[key]
                    if hasattr(apic, "data") and apic.data:
                        return apic.data

        # FLAC
        if isinstance(audio, FLAC):
            for pic in audio.pictures:
                if pic.type == 3 or pic.mime.startswith("image"):  # Front cover
                    return pic.data
            if audio.pictures:
                return audio.pictures[0].data

        # MP4/M4A
        if isinstance(audio, MP4):
            if "covr" in audio.tags:
                covr = audio.tags["covr"]
                if covr:
                    return bytes(covr[0])

        # OGG Vorbis / OggFLAC
        if isinstance(audio, (OggVorbis, OggFLAC)):
            for pic in audio.pictures:
                if pic.type == 3 or pic.mime.startswith("image"):
                    return pic.data
            if audio.pictures:
                return audio.pictures[0].data

        # Generic metadata with pictures
        if hasattr(audio, "pictures") and audio.pictures:
            return audio.pictures[0].data

    except Exception:
        pass

    return None


def get_image_extension(mime_type: str) -> str:
    """Get file extension from MIME type."""
    mime_map = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }
    return mime_map.get(mime_type.lower(), ".jpg")


def detect_image_extension(image_data: bytes) -> str:
    """Detect image format from magic bytes."""
    if len(image_data) < 12:
        return ".jpg"

    # JPEG: FF D8 FF
    if image_data[:3] == b"\xFF\xD8\xFF":
        return ".jpg"
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if image_data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    # GIF: 47 49 46 38
    if image_data[:4] == b"GIF8":
        return ".gif"
    # WebP: 52 49 46 46 xx xx xx xx 57 45 42 50
    if image_data[8:12] == b"WEBP":
        return ".webp"
    # BMP: 42 4D
    if image_data[:2] == b"BM":
        return ".bmp"

    return ".jpg"


def render_path(template: str, file_record: AudioFile) -> str:
    """Replace tokens in template with record values."""
    replacements = {
        "{Artist Name}": file_record.artist or "Unknown Artist",
        "{Album Title}": file_record.album or "Unknown Album",
        "{track:00}": f"{file_record.track_number:02d}" if file_record.track_number else "00",
        "{Track Title}": file_record.title or Path(file_record.filename).stem,
        "{Release Year}": file_record.year or "0000",
        "{Medium Format}": file_record.medium_format or "CD",
        "{medium:00}": f"{file_record.medium_number:02d}" if file_record.medium_number else "01",
    }
    result = template
    for token, value in replacements.items():
        result = result.replace(token, sanitize_filename(value))
    return result


def move_files(db: Session, ids: list[int], mode: str = "move") -> list[dict]:
    """Move/copy/link selected files to output directory using configured template."""
    results = []
    operation_mode = (mode or "move").strip().lower()
    if operation_mode not in {"move", "copy", "hardlink", "symlink"}:
        operation_mode = "move"
    for record in db.query(AudioFile).filter(AudioFile.id.in_(ids)).all():
        try:
            rel_path = render_path(config.path_template, record)
            ext = Path(record.filename).suffix
            dest = Path(config.output_dir) / (rel_path + ext)
            dest.parent.mkdir(parents=True, exist_ok=True)

            src = Path(record.filepath)
            if not src.exists():
                raise FileNotFoundError(f"Source missing: {record.filepath}")

            # Store original path before moving
            record.original_filepath = str(src.resolve())
            
            # Get file info before moving
            info = probe_audio_info(str(src))
            record.file_size = info.file_size
            record.bitrate = info.bitrate
            record.sample_rate = info.sample_rate
            record.duration = info.duration

            # Extract cover art before moving
            cover_data = extract_cover_art(str(src))

            if operation_mode == "move":
                shutil.move(str(src), str(dest))
            elif operation_mode == "copy":
                shutil.copy2(str(src), str(dest))
            elif operation_mode == "hardlink":
                os.link(str(src), str(dest))
            elif operation_mode == "symlink":
                os.symlink(str(src), str(dest))

            # Save cover art if found
            if cover_data:
                img_ext = detect_image_extension(cover_data)
                cover_path = dest.parent / (dest.stem + img_ext)
                cover_path.write_bytes(cover_data)
                log = OperationLog(
                    action="cover_saved",
                    details=f"Saved cover art: {cover_path}",
                )
                db.add(log)

            # Clean up empty source dirs only for physical move.
            if operation_mode == "move":
                parent = src.parent
                while parent != Path(config.source_dir).resolve() and parent != parent.parent:
                    try:
                        if not any(parent.iterdir()):
                            parent.rmdir()
                        parent = parent.parent
                    except OSError:
                        break

            record.status = "moved"
            record.filepath = str(dest.resolve())

            # Log with detailed metadata
            log = OperationLog(
                action="move",
                details=f"Moved {record.filename} -> {dest}",
                log_metadata=json.dumps({
                    "action": "move",
                    "filename": record.filename,
                    "from_path": record.original_filepath,
                    "to_path": str(dest.resolve()),
                    "cover_art_saved": bool(cover_data),
                    "mode": operation_mode,
                }),
            )
            db.add(log)
            results.append({"id": record.id, "status": "moved", "path": str(dest), "mode": operation_mode})

        except Exception as e:
            record.status = "error"
            log = OperationLog(action="error", details=str(e))
            db.add(log)
            results.append({"id": record.id, "status": "error", "error": str(e)})

    db.commit()
    return results
