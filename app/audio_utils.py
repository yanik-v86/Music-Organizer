from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from mutagen import File as MutagenFile


@dataclass(frozen=True)
class AudioInfo:
    file_size: int = 0
    bitrate: str = ""
    sample_rate: str = ""
    duration: str = ""


def safe_mutagen_open(filepath: str):
    """
    Best-effort Mutagen open.

    Some real-world MP3s (truncated, mislabeled, garbage headers) can raise
    exceptions like "can't sync to MPEG frame". Callers should treat a None
    return as "unsupported/unreadable" and fall back gracefully.
    """
    try:
        return MutagenFile(filepath)
    except Exception:
        return None


def probe_audio_info(filepath: str) -> AudioInfo:
    """Best-effort file size + codec info (bitrate/sample rate/duration)."""
    file_size = 0
    try:
        file_size = Path(filepath).stat().st_size
    except Exception:
        file_size = 0

    audio = safe_mutagen_open(filepath)
    if not audio or not getattr(audio, "info", None):
        return AudioInfo(file_size=file_size)

    info = audio.info
    bitrate = ""
    sample_rate = ""
    duration = ""

    try:
        if getattr(info, "bitrate", None):
            bitrate = f"{int(info.bitrate) // 1000} kbps"
    except Exception:
        pass

    try:
        if getattr(info, "sample_rate", None):
            sample_rate = f"{float(info.sample_rate) / 1000:.1f} kHz"
    except Exception:
        pass

    try:
        length = getattr(info, "length", None)
        if length:
            mins = int(length // 60)
            secs = int(length % 60)
            duration = f"{mins}:{secs:02d}"
    except Exception:
        pass

    return AudioInfo(
        file_size=file_size,
        bitrate=bitrate,
        sample_rate=sample_rate,
        duration=duration,
    )

