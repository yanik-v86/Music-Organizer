import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, Response
from sqlalchemy.orm import Session

from app.config import config, CONFIG_PATH, load_config, AppConfig, get_httpx_client_kwargs, get_effective_proxy_url
import app.config as config_module
from app.models import (
    init_db, get_db, AudioFile, OperationLog, Task,
    AudioFileSchema, TagSchema, BatchTagUpdate, MoveRequest, LogSchema, ConfigUpdate, TaskSchema, StatusUpdate, BatchStatusUpdate,
)
from app.id3_handler import read_tags, write_tags, parse_filename_to_tags, tags_are_empty
from app.scanner import scan_source
from app.file_organizer import move_files, render_path, extract_cover_art, detect_image_extension
from app.gotify import send_gotify, test_gotify_connection
from app.worker import worker, start_worker
from app.music_identifier import identify_track, search_track
from app.ollama_handler import extract_tags_from_filename, is_ollama_available


async def background_scanner():
    """Periodically scan source directory for new files."""
    while True:
        try:
            from app.models import SessionLocal
            db = SessionLocal()
            try:
                new_files = scan_source(db)
                if new_files:
                    names = ", ".join(f.filename for f in new_files[:5])
                    msg = f"Found {len(new_files)} new files: {names}"
                    if len(new_files) > 5:
                        msg += f"... and {len(new_files) - 5} more"
                    await send_gotify("Music Organizer - Scan", msg)
            finally:
                db.close()
        except Exception:
            pass
        if config.scan_interval <= 0:
            break
        await asyncio.sleep(config.scan_interval)


bg_task = None
worker_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bg_task, worker_task
    init_db()
    bg_task = asyncio.create_task(background_scanner())
    worker_task = asyncio.create_task(start_worker())
    yield
    if bg_task:
        bg_task.cancel()
    if worker_task:
        worker_task.cancel()


app = FastAPI(title="Music Organizer", lifespan=lifespan)

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _is_subpath(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except Exception:
        return False


def _file_presence_payload(row: AudioFile) -> dict:
    file_path = Path(row.filepath)
    source_path = Path(config.source_dir)
    output_path = Path(config.output_dir)
    exists_on_disk = file_path.exists()
    in_source_dir = _is_subpath(file_path, source_path)
    in_output_dir = _is_subpath(file_path, output_path)
    is_newly_added = bool(row.created_at and row.created_at >= datetime.utcnow() - timedelta(hours=24))
    return {
        "exists_on_disk": exists_on_disk,
        "in_source_dir": in_source_dir,
        "in_output_dir": in_output_dir,
        "is_newly_added": is_newly_added,
        "cover_url": _file_cover_url(row),
    }


def _file_cover_path(row: AudioFile) -> Path | None:
    file_path = Path(row.filepath)
    if not file_path.exists() or not file_path.is_file():
        return None
    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    for candidate in file_path.parent.glob(f"{file_path.stem}.*"):
        if candidate.is_file() and candidate.suffix.lower() in image_exts:
            return candidate
    return None


def _file_cover_url(row: AudioFile) -> str:
    file_path = Path(row.filepath)
    return f"/api/files/{row.id}/cover" if file_path.exists() and file_path.is_file() else ""


# ---- HTML page ----

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = TEMPLATES_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ---- Scan ----

@app.post("/api/scan")
async def api_scan(db: Session = Depends(get_db)):
    """Start scan task in background."""
    await send_gotify("Music Organizer - Scan", "Starting source directory scan...")
    task = await worker.add_task("scan", 0)
    return {"task_id": task.id, "status": "queued", "message": "Scan task queued"}


@app.post("/api/scan/sync")
async def api_scan_sync(db: Session = Depends(get_db)):
    """Synchronous scan (for backward compatibility)."""
    new_files = scan_source(db)
    if new_files:
        names = ", ".join(f.filename for f in new_files[:5])
        msg = f"Found {len(new_files)} new files: {names}"
        if len(new_files) > 5:
            msg += f"... and {len(new_files) - 5} more"
        await send_gotify("Music Organizer - Scan Complete", msg)
    return {"scanned": len(new_files), "files": [{
        "id": f.id,
        "filename": f.filename,
        "filepath": f.filepath,
        "original_filepath": f.original_filepath or "",
        "artist": f.artist or "",
        "album": f.album or "",
        "title": f.title or "",
        "track_number": f.track_number or 0,
        "year": f.year or "",
        "medium_format": f.medium_format or "",
        "medium_number": f.medium_number or 1,
        "status": f.status or "",
        "file_size": f.file_size or 0,
        "bitrate": f.bitrate or "",
        "sample_rate": f.sample_rate or "",
        "duration": f.duration or "",
        "created_at": f.created_at,
        "updated_at": f.updated_at,
    } for f in new_files]}


# ---- Files ----

@app.get("/api/files")
async def api_list_files(
    status: str = "new",
    artist: str = "",
    album: str = "",
    year: str = "",
    search: str = "",
    db: Session = Depends(get_db)
):
    """List files with optional filters."""
    query = db.query(AudioFile).filter(AudioFile.status == status)
    
    if artist:
        query = query.filter(AudioFile.artist.ilike(f"%{artist}%"))
    if album:
        query = query.filter(AudioFile.album.ilike(f"%{album}%"))
    if year:
        query = query.filter(AudioFile.year == year)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (AudioFile.title.ilike(search_filter)) |
            (AudioFile.artist.ilike(search_filter)) |
            (AudioFile.album.ilike(search_filter))
        )
    
    rows = query.order_by(AudioFile.id).all()
    result = []
    for r in rows:
        payload = {
            "id": r.id,
            "filename": r.filename,
            "filepath": r.filepath,
            "original_filepath": r.original_filepath or "",
            "artist": r.artist or "",
            "album": r.album or "",
            "title": r.title or "",
            "track_number": r.track_number or 0,
            "year": r.year or "",
            "medium_format": r.medium_format or "",
            "medium_number": r.medium_number or 1,
            "status": r.status or "",
            "file_size": r.file_size or 0,
            "bitrate": r.bitrate or "",
            "sample_rate": r.sample_rate or "",
            "duration": r.duration or "",
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        payload.update(_file_presence_payload(r))
        result.append(payload)
    return result


@app.get("/api/files/filters")
async def api_get_file_filters(status: str = "new", db: Session = Depends(get_db)):
    """Get unique filter values for dropdowns."""
    query = db.query(AudioFile).filter(AudioFile.status == status)

    artists = [a[0] for a in query.with_entities(AudioFile.artist).distinct().filter(AudioFile.artist != "").all()]
    albums = [a[0] for a in query.with_entities(AudioFile.album).distinct().filter(AudioFile.album != "").all()]
    years = [a[0] for a in query.with_entities(AudioFile.year).distinct().filter(AudioFile.year != "").all()]

    return {
        "artists": sorted(artists),
        "albums": sorted(albums),
        "years": sorted([y for y in years if y]),
    }


@app.put("/api/files/batch/tags")
async def api_batch_tags(update: BatchTagUpdate, db: Session = Depends(get_db)):
    """Batch update tags for multiple files."""
    results = []
    for file_id in update.ids:
        row = db.query(AudioFile).get(file_id)
        if not row:
            continue
        try:
            write_tags(row.filepath, update.tags)
            if update.tags.artist is not None:
                row.artist = update.tags.artist
            if update.tags.album is not None:
                row.album = update.tags.album
            if update.tags.title is not None:
                row.title = update.tags.title
            if update.tags.track_number is not None:
                row.track_number = update.tags.track_number
            if update.tags.year is not None:
                row.year = update.tags.year
            if update.tags.medium_format is not None:
                row.medium_format = update.tags.medium_format
            if update.tags.medium_number is not None:
                row.medium_number = update.tags.medium_number
            row.status = "processed"
            results.append({"id": file_id, "status": "ok"})
        except Exception as e:
            results.append({"id": file_id, "status": "error", "error": str(e)})

    log = OperationLog(action="batch_edit", details=f"Batch edit on {len(update.ids)} files")
    db.add(log)
    db.commit()
    return {"results": results}


@app.get("/api/files/{file_id}")
async def api_get_file(file_id: int, db: Session = Depends(get_db)):
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")
    return {
        "id": row.id,
        "filename": row.filename,
        "filepath": row.filepath,
        "original_filepath": row.original_filepath or "",
        "artist": row.artist or "",
        "album": row.album or "",
        "title": row.title or "",
        "track_number": row.track_number or 0,
        "year": row.year or "",
        "medium_format": row.medium_format or "",
        "medium_number": row.medium_number or 1,
        "status": row.status or "",
        "file_size": row.file_size or 0,
        "bitrate": row.bitrate or "",
        "sample_rate": row.sample_rate or "",
        "duration": row.duration or "",
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        **_file_presence_payload(row),
    }


@app.get("/api/files/{file_id}/audio")
async def api_get_file_audio(file_id: int, db: Session = Depends(get_db)):
    """Stream audio file for browser playback."""
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")

    file_path = Path(row.filepath)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "Audio file missing on disk")

    return FileResponse(path=str(file_path), filename=row.filename)


@app.get("/api/files/{file_id}/cover")
async def api_get_file_cover(file_id: int, db: Session = Depends(get_db)):
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")

    cover_path = _file_cover_path(row)
    if cover_path:
        return FileResponse(path=str(cover_path), filename=cover_path.name)

    cover_data = extract_cover_art(row.filepath)
    if not cover_data:
        raise HTTPException(404, "Cover art not found")

    ext = detect_image_extension(cover_data)
    media_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return Response(content=cover_data, media_type=media_type_map.get(ext, "image/jpeg"))


@app.get("/api/files/{file_id}/detail")
async def api_get_file_detail(file_id: int, db: Session = Depends(get_db)):
    """Get extended file information for modal display."""
    from pathlib import Path
    from app.audio_utils import probe_audio_info
    
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")
    
    # Get file extension
    ext = Path(row.filename).suffix.lower().lstrip('.')
    
    # Get file size
    file_size = 0
    try:
        if Path(row.filepath).exists():
            file_size = Path(row.filepath).stat().st_size
    except Exception:
        pass
    
    # Format file size
    def format_size(size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    # Try to get audio info
    bitrate = row.bitrate or ""
    sample_rate = row.sample_rate or ""
    duration = row.duration or ""
    
    info = probe_audio_info(row.filepath)
    bitrate = info.bitrate or bitrate
    sample_rate = info.sample_rate or sample_rate
    duration = info.duration or duration
    
    return {
        "id": row.id,
        "filename": row.filename,
        "filepath": row.filepath,
        "original_filepath": row.original_filepath or "",
        "artist": row.artist or "",
        "album": row.album or "",
        "title": row.title or "",
        "track_number": row.track_number or 0,
        "year": row.year or "",
        "medium_format": row.medium_format or "",
        "medium_number": row.medium_number or 1,
        "status": row.status or "",
        "file_size": file_size,
        "file_size_formatted": format_size(file_size),
        "extension": ext,
        "bitrate": bitrate,
        "sample_rate": sample_rate,
        "duration": duration,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        **_file_presence_payload(row),
    }


@app.put("/api/files/{file_id}/status")
async def api_update_file_status(file_id: int, update: StatusUpdate, db: Session = Depends(get_db)):
    """Update file status."""
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")
    
    if update.status not in ["new", "processed", "moved", "error", "pending_move", "Delete"]:
        raise HTTPException(400, "Invalid status")
    
    row.status = update.status
    db.commit()
    return {"status": "ok", "file_id": file_id, "new_status": update.status}


@app.put("/api/files/status/batch")
async def api_batch_update_file_status(update: BatchStatusUpdate, db: Session = Depends(get_db)):
    """Batch update status for multiple files."""
    if update.status not in ["new", "processed", "moved", "error", "pending_move", "Delete"]:
        raise HTTPException(400, "Invalid status")

    updated = 0
    skipped = 0
    for file_id in update.ids:
        row = db.query(AudioFile).get(file_id)
        if not row:
            skipped += 1
            continue
        row.status = update.status
        updated += 1

    db.commit()
    return {"status": "ok", "updated": updated, "skipped": skipped, "new_status": update.status}


@app.delete("/api/files/{file_id}")
async def api_delete_file(file_id: int, db: Session = Depends(get_db)):
    """Delete file record from database (does not delete actual file)."""
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")
    
    db.delete(row)
    db.commit()
    return {"status": "ok", "file_id": file_id}


@app.get("/api/files/{file_id}/tags")
async def api_read_tags(file_id: int, db: Session = Depends(get_db)):
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")
    tags = read_tags(row.filepath)
    return tags.model_dump()


@app.post("/api/files/{file_id}/tags/auto-fill")
async def api_auto_fill_tags(
    file_id: int,
    preview: bool = False,
    db: Session = Depends(get_db),
):
    """Auto-fill tags from filename. With preview=true, only returns parsed tags (for modal form); does not write files."""
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")

    # Parse filename
    parsed_tags = parse_filename_to_tags(row.filename)

    if not parsed_tags.artist and not parsed_tags.title:
        return {
            "status": "no_data",
            "message": "Could not extract tags from filename",
            "filename": row.filename,
        }

    if preview:
        return {
            "status": "ok",
            "preview": True,
            "tags": parsed_tags.model_dump(),
        }

    # Read current tags (non-preview: legacy batch behaviour)
    current_tags = read_tags(row.filepath)

    if not tags_are_empty(current_tags):
        return {
            "status": "skipped",
            "message": "File already has tags",
            "current_tags": current_tags.model_dump(),
        }

    # Write parsed tags
    write_tags(row.filepath, parsed_tags)

    # Update DB record
    if parsed_tags.artist:
        row.artist = parsed_tags.artist
    if parsed_tags.album:
        row.album = parsed_tags.album
    if parsed_tags.title:
        row.title = parsed_tags.title
    if parsed_tags.track_number:
        row.track_number = parsed_tags.track_number
    if parsed_tags.year:
        row.year = parsed_tags.year

    db.commit()
    db.refresh(row)

    return {
        "status": "ok",
        "message": "Tags filled from filename",
        "tags": parsed_tags.model_dump(),
    }


@app.post("/api/files/batch/auto-fill")
async def api_batch_auto_fill(ids: list[int], db: Session = Depends(get_db)):
    """Auto-fill tags from filename for multiple files."""
    results = []
    for file_id in ids:
        row = db.query(AudioFile).get(file_id)
        if not row:
            results.append({"id": file_id, "status": "error", "error": "File not found"})
            continue
        
        current_tags = read_tags(row.filepath)
        if not tags_are_empty(current_tags):
            results.append({"id": file_id, "status": "skipped", "message": "Already has tags"})
            continue
        
        parsed_tags = parse_filename_to_tags(row.filename)
        if not parsed_tags.artist and not parsed_tags.title:
            results.append({"id": file_id, "status": "no_data", "message": "Could not parse filename"})
            continue
        
        try:
            write_tags(row.filepath, parsed_tags)
            
            if parsed_tags.artist:
                row.artist = parsed_tags.artist
            if parsed_tags.album:
                row.album = parsed_tags.album
            if parsed_tags.title:
                row.title = parsed_tags.title
            if parsed_tags.track_number:
                row.track_number = parsed_tags.track_number
            if parsed_tags.year:
                row.year = parsed_tags.year
            
            row.status = "processed"
            results.append({"id": file_id, "status": "ok", "tags": parsed_tags.model_dump()})
        except Exception as e:
            results.append({"id": file_id, "status": "error", "error": str(e)})
    
    db.commit()
    return {"results": results}


@app.post("/api/files/batch/identify-acoustid")
async def api_batch_identify_acoustid(ids: list[int], db: Session = Depends(get_db)):
    """Batch auto-identify tags using AcoustID (fingerprint) only.

    Worker updates ID3 and marks artist/title with '.' when verification is needed:
    - if AcoustID suggestion for artist/title is empty -> keep current values but append '.'
      (or set '.' if empty)
    - if AcoustID suggestion matches existing ID3 values -> append '.' to mark "needs confirmation"
    """
    if not ids:
        raise HTTPException(400, "ids is required")

    acoustid_key = (config.acoustid.api_key or "").strip() if config.acoustid else ""
    if not acoustid_key:
        raise HTTPException(
            400,
            "Add your free AcoustID API key in Settings: https://acoustid.org/api-key",
        )

    rows = db.query(AudioFile).filter(AudioFile.id.in_(ids)).all()
    if not rows:
        raise HTTPException(404, "No files found for provided ids")

    for row in rows:
        row.status = "pending_acoustid"
    db.commit()

    await send_gotify(
        "Music Organizer - Batch Identify (AcoustID)",
        f"Queued AcoustID identify for {len(rows)} file(s)",
    )
    task = await worker.add_task("batch_acoustid_identify", len(rows))
    return {"task_id": task.id, "status": "queued", "count": len(rows)}


@app.post("/api/files/batch/generate-metadata-ollama")
async def api_batch_generate_metadata_ollama(ids: list[int], db: Session = Depends(get_db)):
    """Batch generate metadata using Ollama (filename) only.

    Worker updates ID3 and marks artist/title with '.' when verification is needed:
    - if Ollama suggestion for artist/title is empty -> keep current values but append '.'
      (or set '.' if empty)
    - if Ollama suggestion matches existing ID3 values -> append '.' to mark "needs confirmation"
    """
    if not ids:
        raise HTTPException(400, "ids is required")

    ollama_url = (config.ollama.url or "").strip() if config.ollama else ""
    if not ollama_url:
        raise HTTPException(
            400,
            "Configure Ollama URL in Settings before batch Ollama metadata generation.",
        )

    rows = db.query(AudioFile).filter(AudioFile.id.in_(ids)).all()
    if not rows:
        raise HTTPException(404, "No files found for provided ids")

    for row in rows:
        row.status = "pending_ollama"
    db.commit()

    await send_gotify(
        "Music Organizer - Batch Metadata (Ollama)",
        f"Queued Ollama metadata generation for {len(rows)} file(s)",
    )
    task = await worker.add_task("batch_ollama_generate", len(rows))
    return {"task_id": task.id, "status": "queued", "count": len(rows)}


@app.post("/api/files/{file_id}/identify")
async def api_identify_file(
    file_id: int,
    debug: bool = False,
    db: Session = Depends(get_db),
):
    """Identify track using AcoustID fingerprinting."""
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")

    acoustid_key = (config.acoustid.api_key or "").strip() if config.acoustid else ""
    if not acoustid_key:
        return {
            "status": "error",
            "message": "Add your free AcoustID API key in Settings: https://acoustid.org/api-key",
        }

    # Try to identify
    result = await identify_track(row.filepath, debug=debug)
    
    if result["status"] == "identified":
        # Get best release for album info
        album = ""
        year = ""
        def pick_best_by_year(candidates: list[dict]) -> tuple[str, str]:
            if not candidates:
                return "", ""
            with_year = [c for c in candidates if c.get("year")]
            if with_year:
                def sort_key(r: dict) -> tuple[int, str]:
                    y = str(r.get("year") or "")
                    y_int = int(y) if y.isdigit() else 10**9
                    # Prefer latest year first.
                    return (-y_int, str(r.get("date") or ""))
                best = sorted(with_year, key=sort_key)[0]
                return best.get("title", "") or "", str(best.get("year") or "")[:4]

            # Fallback by date string
            with_date = [c for c in candidates if c.get("date")]
            if with_date:
                # Prefer latest date first (YYYY-MM-DD sorts lexicographically).
                best = sorted(with_date, key=lambda x: str(x.get("date", "")))[-1]
                return best.get("title", "") or "", str(best.get("date", "") or "")[:4]

            return "", ""

        releases = result.get("releases") or []
        album, year = pick_best_by_year(releases)

        # If release.date is empty for some reason, use release-groups (often has first-release-date)
        if (not year or not album) and result.get("release_groups"):
            rg_album, rg_year = pick_best_by_year(result.get("release_groups") or [])
            album = album or rg_album
            year = year or rg_year
        
        response = {
            "status": "identified",
            "confidence": result.get("confidence", 0),
            "source": result.get("source"),
            "suggested_tags": {
                "artist": result.get("artist") or "",
                "album": album,
                "title": result.get("title") or "",
                "track_number": result.get("track_number") or 0,
                "year": year,
                "medium_format": "Digital Media",
                "medium_number": 1,
            },
            "releases": result.get("releases", []),
            "release_groups": result.get("release_groups", []),
        }

        if debug:
            # Keep debug payload small but informative.
            response["debug_release_candidates"] = {
                "releases_count": len(response.get("releases") or []),
                "release_groups_count": len(response.get("release_groups") or []),
                "releases_sample": (response.get("releases") or [])[:3],
                "release_groups_sample": (response.get("release_groups") or [])[:3],
            }
            # Also print debug to Python stdout so it's visible when starting server.
            print("[api_identify_file][debug] suggested_tags:", response.get("suggested_tags"))
            print("[api_identify_file][debug] debug_release_candidates:", response.get("debug_release_candidates"))

        return response
    
    # If AcoustID failed, try filename parsing as fallback
    parsed = parse_filename_to_tags(row.filename)
    if parsed.artist or parsed.title:
        return {
            "status": "parsed_from_filename",
            "confidence": 0.5,
            "source": "filename",
            "suggested_tags": parsed.model_dump(),
        }
    
    return {"status": "not_found", "source": "none"}


@app.post("/api/files/{file_id}/generate-metadata")
async def api_generate_metadata(file_id: int, db: Session = Depends(get_db)):
    """Generate metadata using Ollama AI based on filename. Returns suggested tags without saving."""
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")

    # Try Ollama first
    ollama_result = await extract_tags_from_filename(row.filename)

    if ollama_result:
        return {
            "status": "ok",
            "source": "ollama",
            "filename": row.filename,
            "suggested_tags": ollama_result,
        }

    # Fallback to filename parsing
    parsed = parse_filename_to_tags(row.filename)
    if parsed.artist or parsed.title:
        return {
            "status": "ok",
            "source": "filename",
            "filename": row.filename,
            "suggested_tags": parsed.model_dump(),
        }

    return {"status": "error", "message": "Could not generate metadata"}


@app.get("/api/ollama/check")
async def api_check_ollama():
    """Check Ollama connection and available models."""
    success, message = await check_ollama_connection()
    return {"success": success, "message": message}


@app.post("/api/files/{file_id}/search")
async def api_search_tracks(
    query: str = "",
    title: str = "",
    artist: str = "",
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """Search for tracks on MusicBrainz."""
    # Keep backward compatibility with `query`, but allow precise
    # `title + artist` lookup for richer MusicBrainz metadata.
    normalized_limit = max(1, min(limit, 25))
    results = await search_track(
        query=query,
        title=title,
        artist=artist,
        limit=normalized_limit,
    )
    return {
        "results": results,
        "query_used": {
            "query": query,
            "title": title,
            "artist": artist,
            "limit": normalized_limit,
        },
    }


@app.post("/api/files/{file_id}/apply-tags")
async def api_apply_suggested_tags(
    file_id: int,
    tags: TagSchema,
    db: Session = Depends(get_db)
):
    """Apply user-confirmed tags to a file."""
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")
    
    # Write tags to file
    write_tags(row.filepath, tags)
    
    # Update DB record
    if tags.artist is not None:
        row.artist = tags.artist
    if tags.album is not None:
        row.album = tags.album
    if tags.title is not None:
        row.title = tags.title
    if tags.track_number is not None:
        row.track_number = tags.track_number
    if tags.year is not None:
        row.year = tags.year
    if tags.medium_format is not None:
        row.medium_format = tags.medium_format
    if tags.medium_number is not None:
        row.medium_number = tags.medium_number
    
    row.status = "processed"
    
    import json
    log = OperationLog(
        action="auto_identified",
        details=f"Auto-identified and updated tags for {row.filename}",
        log_metadata=json.dumps({
            "action": "auto_identified",
            "filename": row.filename,
            "filepath": row.filepath,
            "new_tags": tags.model_dump(),
        }),
    )
    db.add(log)
    db.commit()
    db.refresh(row)
    
    return {
        "status": "ok",
        "message": "Tags applied successfully",
        "file": {
            "id": row.id,
            "filename": row.filename,
            "artist": row.artist,
            "title": row.title,
        },
    }


@app.get("/api/ollama/status")
async def api_ollama_status():
    """Check if Ollama is available and configured."""
    available = await is_ollama_available()
    url, model = extract_tags_from_filename.__globals__['get_ollama_config']()
    return {
        "available": available,
        "configured": bool(url and model),
        "url": url,
        "model": model,
    }


@app.get("/api/services/check")
async def api_check_services():
    """Check configured external services without side effects."""
    services = []
    proxy_url = get_effective_proxy_url()

    # Proxy
    if proxy_url:
        try:
            async with httpx.AsyncClient(timeout=5.0, **get_httpx_client_kwargs()) as client:
                resp = await client.get("https://httpbin.org/ip")
            services.append({
                "name": "proxy",
                "configured": True,
                "ok": resp.status_code == 200,
                "message": f"{proxy_url.split('://')[0]}" if resp.status_code == 200 else f"http {resp.status_code}",
            })
        except Exception as e:
            services.append({
                "name": "proxy",
                "configured": True,
                "ok": False,
                "message": f"proxy error: {str(e)}",
            })
    else:
        services.append({
            "name": "proxy",
            "configured": False,
            "ok": False,
            "message": "not configured",
        })

    # Ollama
    ollama_url = (config.ollama.url or "").strip() if config.ollama else ""
    ollama_model = (config.ollama.model or "").strip() if config.ollama else ""
    if ollama_url and ollama_model:
        try:
            async with httpx.AsyncClient(timeout=4.0, **get_httpx_client_kwargs(ollama_url)) as client:
                resp = await client.get(f"{ollama_url.rstrip('/')}/api/tags")
            services.append({
                "name": "ollama",
                "configured": True,
                "ok": resp.status_code == 200,
                "message": f"{ollama_model}" if resp.status_code == 200 else f"http {resp.status_code}",
            })
        except Exception as e:
            services.append({
                "name": "ollama",
                "configured": True,
                "ok": False,
                "message": f"offline: {str(e)}",
            })
    else:
        services.append({
            "name": "ollama",
            "configured": False,
            "ok": False,
            "message": "not configured",
        })

    # Gotify
    gotify_url = (config.gotify.url or "").strip() if config.gotify else ""
    gotify_token = (config.gotify.token or "").strip() if config.gotify else ""
    if gotify_url and gotify_token:
        try:
            version_url = f"{gotify_url.rstrip('/')}/version"
            async with httpx.AsyncClient(timeout=4.0, **get_httpx_client_kwargs()) as client:
                resp = await client.get(version_url)
            services.append({
                "name": "gotify",
                "configured": True,
                "ok": resp.status_code == 200,
                "message": "reachable" if resp.status_code == 200 else f"http {resp.status_code}",
            })
        except Exception as e:
            services.append({
                "name": "gotify",
                "configured": True,
                "ok": False,
                "message": f"offline: {str(e)}",
            })
    else:
        services.append({
            "name": "gotify",
            "configured": False,
            "ok": False,
            "message": "url/token missing",
        })

    # AcoustID
    acoustid_key = (config.acoustid.api_key or "").strip() if config.acoustid else ""
    if acoustid_key:
        try:
            async with httpx.AsyncClient(timeout=5.0, **get_httpx_client_kwargs()) as client:
                resp = await client.get(
                    "https://api.acoustid.org/v2/lookup",
                    params={"client": acoustid_key, "meta": "recordings", "duration": 1, "fingerprint": "test"},
                )
            ok = resp.status_code == 200
            services.append({
                "name": "acoustid",
                "configured": True,
                "ok": ok,
                "message": "key accepted/reachable" if ok else f"http {resp.status_code}",
            })
        except Exception as e:
            services.append({
                "name": "acoustid",
                "configured": True,
                "ok": False,
                "message": f"offline: {str(e)}",
            })
    else:
        services.append({
            "name": "acoustid",
            "configured": False,
            "ok": False,
            "message": "api key missing",
        })

    return {"services": services}


@app.post("/api/files/{file_id}/analyze-llm")
async def api_analyze_with_llm(file_id: int, db: Session = Depends(get_db)):
    """Analyze filename using Ollama LLM to extract metadata."""
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")
    
    # Check if Ollama is available
    if not await is_ollama_available():
        return {
            "status": "error",
            "message": "Ollama is not configured. Please set up Ollama URL and model in Settings.",
        }
    
    # Extract tags using LLM
    extracted = await extract_tags_from_filename(row.filename)
    
    if not extracted or (not extracted.get('artist') and not extracted.get('title')):
        return {
            "status": "no_data",
            "message": "Could not extract metadata from filename using LLM",
            "filename": row.filename,
        }
    
    return {
        "status": "ok",
        "source": "ollama_llm",
        "filename": row.filename,
        "suggested_tags": extracted,
    }


@app.put("/api/files/{file_id}/tags")
async def api_write_tags(file_id: int, tags: TagSchema, db: Session = Depends(get_db)):
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")

    # Store old values for logging
    old_values = {
        "artist": row.artist,
        "album": row.album,
        "title": row.title,
        "track_number": row.track_number,
        "year": row.year,
        "medium_format": row.medium_format,
        "medium_number": row.medium_number,
    }

    write_tags(row.filepath, tags)

    # Update DB record
    if tags.artist is not None:
        row.artist = tags.artist
    if tags.album is not None:
        row.album = tags.album
    if tags.title is not None:
        row.title = tags.title
    if tags.track_number is not None:
        row.track_number = tags.track_number
    if tags.year is not None:
        row.year = tags.year
    if tags.medium_format is not None:
        row.medium_format = tags.medium_format
    if tags.medium_number is not None:
        row.medium_number = tags.medium_number

    # Don't change status - keep it as is so file doesn't disappear
    import json
    changes = {k: {"old": old_values[k], "new": getattr(row, k)} 
               for k in old_values if tags.__dict__.get(k) is not None}
    
    log = OperationLog(
        action="edit_tags",
        details=f"Edited tags for {row.filename}",
        log_metadata=json.dumps({
            "action": "edit_tags",
            "filename": row.filename,
            "filepath": row.filepath,
            "changes": changes,
        }),
    )
    db.add(log)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "filename": row.filename,
        "filepath": row.filepath,
        "original_filepath": row.original_filepath or "",
        "artist": row.artist or "",
        "album": row.album or "",
        "title": row.title or "",
        "track_number": row.track_number or 0,
        "year": row.year or "",
        "medium_format": row.medium_format or "",
        "medium_number": row.medium_number or 1,
        "status": row.status or "",
        "file_size": row.file_size or 0,
        "bitrate": row.bitrate or "",
        "sample_rate": row.sample_rate or "",
        "duration": row.duration or "",
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


# ---- Move ----

@app.post("/api/files/move")
async def api_move(req: MoveRequest, db: Session = Depends(get_db)):
    """Start move task in background."""
    mode = (req.mode or "move").strip().lower()
    if mode not in {"move", "copy", "hardlink", "symlink"}:
        raise HTTPException(400, "Invalid move mode")
    await send_gotify("Music Organizer - Move", f"Queuing move operation for {len(req.ids)} file(s)...")
    
    # Store file IDs in a temporary way for the worker
    # For now, we'll use a simple approach - mark files as "pending_move"
    for file_id in req.ids:
        file = db.query(AudioFile).get(file_id)
        if file:
            file.status = "pending_move"
    db.commit()
    
    task = await worker.add_task(f"move:{mode}", len(req.ids))
    return {"task_id": task.id, "status": "queued", "mode": mode, "message": f"Move task queued for {len(req.ids)} files ({mode})"}


@app.post("/api/files/move/sync")
async def api_move_sync(req: MoveRequest, db: Session = Depends(get_db)):
    """Synchronous move (for backward compatibility)."""
    mode = (req.mode or "move").strip().lower()
    if mode not in {"move", "copy", "hardlink", "symlink"}:
        raise HTTPException(400, "Invalid move mode")
    await send_gotify("Music Organizer - Move", f"Starting move operation for {len(req.ids)} file(s)...")
    results = move_files(db, req.ids, mode=mode)
    moved_count = sum(1 for r in results if r.get("status") == "moved")
    error_count = sum(1 for r in results if r.get("status") == "error")
    if moved_count:
        msg = f"Successfully moved {moved_count} file(s)"
        if error_count:
            msg += f" ({error_count} errors)"
        await send_gotify("Music Organizer - Move Complete", msg)
    return {"results": results}


# ---- Logs ----

@app.get("/api/logs")
async def api_logs(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.query(OperationLog).order_by(OperationLog.id.desc()).limit(limit).all()
    return [{
        "id": r.id,
        "action": r.action,
        "details": r.details,
        "timestamp": r.timestamp,
    } for r in rows]


@app.get("/api/logs/{log_id}")
async def api_get_log_detail(log_id: int, db: Session = Depends(get_db)):
    """Get detailed log information."""
    import json
    
    log = db.query(OperationLog).get(log_id)
    if not log:
        raise HTTPException(404, "Log not found")
    
    # Parse log_metadata
    metadata = {}
    if log.log_metadata:
        try:
            metadata = json.loads(log.log_metadata)
        except Exception:
            pass
    
    # Try to find related file
    related_file = None
    if "filename" in metadata:
        related_file = db.query(AudioFile).filter(AudioFile.filename == metadata["filename"]).first()
    
    return {
        "id": log.id,
        "action": log.action,
        "details": log.details,
        "timestamp": log.timestamp,
        "metadata": metadata,
        "related_file": {
            "id": related_file.id,
            "filename": related_file.filename,
            "filepath": related_file.filepath,
            "original_filepath": related_file.original_filepath,
            "status": related_file.status,
        } if related_file else None,
    }


@app.post("/api/files/{file_id}/move-back")
async def api_move_file_back(file_id: int, db: Session = Depends(get_db)):
    """Move file back to original location (undo move operation)."""
    import json
    import shutil
    from pathlib import Path
    
    row = db.query(AudioFile).get(file_id)
    if not row:
        raise HTTPException(404, "File not found")
    
    if row.status != "moved":
        raise HTTPException(400, "File was not moved")
    
    if not row.original_filepath:
        raise HTTPException(400, "Original filepath not stored")
    
    src = Path(row.filepath)
    dest = Path(row.original_filepath)
    
    if not src.exists():
        raise HTTPException(400, "Current file not found")
    
    if dest.exists():
        raise HTTPException(400, "Destination already exists")
    
    # Create destination directory if needed
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    # Move file back
    shutil.move(str(src), str(dest))
    
    # Update record
    row.filepath = str(dest.resolve())
    row.status = "processed"  # Mark as processed (was moved back)
    
    # Remove cover art if exists
    cover_path = src.parent / (src.stem + ".jpg")
    if cover_path.exists():
        cover_path.unlink()
    cover_path = src.parent / (src.stem + ".png")
    if cover_path.exists():
        cover_path.unlink()
    
    log = OperationLog(
        action="move_back",
        details=f"Moved back {row.filename} -> {dest}",
        log_metadata=json.dumps({
            "action": "move_back",
            "filename": row.filename,
            "from_path": str(src.resolve()),
            "to_path": str(dest.resolve()),
        }),
    )
    db.add(log)
    db.commit()
    
    return {
        "status": "ok",
        "message": "File moved back to original location",
        "filepath": row.filepath,
    }


# ---- Config ----

@app.get("/api/config")
async def api_get_config():
    return {
        "source_dir": config.source_dir,
        "output_dir": config.output_dir,
        "path_template": config.path_template,
        "extensions": config.extensions,
        "gotify_url": config.gotify.url,
        "gotify_token": config.gotify.token,
        "acoustid_api_key": config.acoustid.api_key if config.acoustid else "",
        "scan_interval": config.scan_interval,
        "ollama_url": config.ollama.url if config.ollama else "",
        "ollama_model": config.ollama.model if config.ollama else "",
        "proxy_url": config.proxy_url or "",
        "proxy_type": config.proxy_type or "http",
        "proxy_host": config.proxy_host or "",
        "proxy_port": config.proxy_port or 0,
        "proxy_username": config.proxy_username or "",
        "proxy_password": config.proxy_password or "",
        "mobile_player_only": bool(config.mobile_player_only),
    }


@app.post("/api/gotify/test")
async def api_test_gotify():
    """Test Gotify notification connection."""
    success, message = await test_gotify_connection()
    return {"success": success, "message": message}


@app.put("/api/config")
async def api_update_config(update: ConfigUpdate, db: Session = Depends(get_db)):
    data = {}
    path = Path(CONFIG_PATH)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    if update.source_dir is not None:
        data["source_dir"] = update.source_dir
    if update.output_dir is not None:
        data["output_dir"] = update.output_dir
    if update.path_template is not None:
        data["path_template"] = update.path_template
    if update.extensions is not None:
        data["extensions"] = update.extensions
    if update.gotify_url is not None:
        data.setdefault("gotify", {})["url"] = update.gotify_url
    if update.gotify_token is not None:
        data.setdefault("gotify", {})["token"] = update.gotify_token
    if update.acoustid_api_key is not None:
        data.setdefault("acoustid", {})["api_key"] = update.acoustid_api_key
    if update.scan_interval is not None:
        data["scan_interval"] = update.scan_interval
    if update.ollama_url is not None:
        data.setdefault("ollama", {})["url"] = update.ollama_url
    if update.ollama_model is not None:
        data.setdefault("ollama", {})["model"] = update.ollama_model
    if update.proxy_url is not None:
        data["proxy_url"] = update.proxy_url
    if update.proxy_type is not None:
        data["proxy_type"] = update.proxy_type
    if update.proxy_host is not None:
        data["proxy_host"] = update.proxy_host
    if update.proxy_port is not None:
        data["proxy_port"] = update.proxy_port
    if update.proxy_username is not None:
        data["proxy_username"] = update.proxy_username
    if update.proxy_password is not None:
        data["proxy_password"] = update.proxy_password
    if update.mobile_player_only is not None:
        data["mobile_player_only"] = bool(update.mobile_player_only)

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    # Reload config from disk and update both:
    # - this module's `config` (used by existing runtime loops)
    # - the shared `app.config.config` (used by other modules at call time)
    global config
    config_module.config = load_config()
    config = config_module.config
    return {"status": "ok", "config": await api_get_config()}


# ---- Stats ----

@app.get("/api/stats")
async def api_stats(db: Session = Depends(get_db)):
    total = db.query(AudioFile).count()
    new = db.query(AudioFile).filter(AudioFile.status == "new").count()
    processed = db.query(AudioFile).filter(AudioFile.status == "processed").count()
    moved = db.query(AudioFile).filter(AudioFile.status == "moved").count()
    errors = db.query(AudioFile).filter(AudioFile.status == "error").count()
    return {"total": total, "new": new, "processed": processed, "moved": moved, "errors": errors}


# ---- Directory Browser ----

@app.get("/api/directories")
async def api_list_directories(path: str = ""):
    """List directories for browser dialog."""
    try:
        base = Path(path) if path else Path.cwd()
        # Security: restrict to user home and below
        home = Path.home()
        try:
            base = base.resolve()
            # Allow paths under home or /mnt, /media
            allowed = [home, Path("/mnt"), Path("/media"), Path("/")]
            if not any(str(base).startswith(str(a)) for a in allowed):
                return {"error": "Access denied", "path": str(base)}
        except (ValueError, RuntimeError):
            return {"error": "Invalid path", "path": str(path)}

        if not base.exists():
            return {"error": "Path does not exist", "path": str(path)}

        items = []
        for item in sorted(base.iterdir()):
            if item.is_dir():
                items.append({
                    "name": item.name,
                    "path": str(item.resolve()),
                    "parent": str(item.parent.resolve()),
                })
        return {"path": str(base.resolve()), "parent": str(base.parent.resolve()) if base != base.parent else "", "directories": items}
    except PermissionError:
        return {"error": "Permission denied", "path": str(path)}
    except Exception as e:
        return {"error": str(e), "path": str(path)}


# ---- Tasks ----

@app.get("/api/tasks")
async def api_list_tasks(limit: int = 50, db: Session = Depends(get_db)):
    """List recent tasks."""
    tasks = db.query(Task).order_by(Task.id.desc()).limit(limit).all()
    return [TaskSchema.model_validate(t).model_dump() for t in tasks]


@app.get("/api/tasks/{task_id}")
async def api_get_task(task_id: int, db: Session = Depends(get_db)):
    """Get task details."""
    task = db.query(Task).get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return TaskSchema.model_validate(task).model_dump()


@app.post("/api/tasks/{task_id}/cancel")
async def api_cancel_task(task_id: int, db: Session = Depends(get_db)):
    """Cancel a task."""
    task = db.query(Task).get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status in ("pending", "running"):
        task.status = "cancelled"
        db.commit()
        await send_gotify("Task Cancelled", f"Task #{task_id} was cancelled")
    return {"status": "ok", "task": TaskSchema.model_validate(task).model_dump()}


@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: int, db: Session = Depends(get_db)):
    """Delete a completed/failed task."""
    task = db.query(Task).get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status not in ("completed", "failed", "cancelled"):
        raise HTTPException(400, "Can only delete completed/failed tasks")
    db.delete(task)
    db.commit()
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8181, reload=True)
