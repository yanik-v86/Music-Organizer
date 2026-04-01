import os
from pathlib import Path
from sqlalchemy.orm import Session

from app.config import config
from app.models import AudioFile
from app.id3_handler import read_tags
from app.audio_utils import probe_audio_info


def scan_source(db: Session) -> list[AudioFile]:
    """Scan source directory for new audio files and register them in DB."""
    source = Path(config.source_dir).resolve()
    if not source.exists():
        source.mkdir(parents=True, exist_ok=True)
        return []

    existing_paths = {row.filepath for row in db.query(AudioFile.filepath).all()}
    new_files = []

    for root, _, files in os.walk(source):
        for fname in sorted(files):
            ext = Path(fname).suffix.lower()
            if ext not in config.extensions:
                continue
            full_path = str(Path(root) / fname)
            if full_path in existing_paths:
                continue

            tags = read_tags(full_path)
            info = probe_audio_info(full_path)

            record = AudioFile(
                filename=fname,
                filepath=full_path,
                artist=tags.artist or "",
                album=tags.album or "",
                title=tags.title or "",
                track_number=tags.track_number or 0,
                year=tags.year or "",
                medium_format=tags.medium_format or "",
                medium_number=tags.medium_number or 1,
                status="new",
                file_size=info.file_size,
                bitrate=info.bitrate,
                sample_rate=info.sample_rate,
                duration=info.duration,
            )
            db.add(record)
            new_files.append(record)

    db.commit()
    for f in new_files:
        db.refresh(f)
    return new_files
