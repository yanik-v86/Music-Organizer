"""
Background worker for processing long-running tasks.
"""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from mutagen import File as MutagenFile
from sqlalchemy.orm import Session

from app.models import Task, AudioFile, OperationLog
from app.config import config
from app.gotify import send_gotify
from app.audio_utils import probe_audio_info


class Worker:
    """Background worker for processing tasks."""
    
    def __init__(self):
        self.running = False
        self.current_task: Optional[Task] = None
        self._task_queue: asyncio.Queue = asyncio.Queue()
    
    async def start(self):
        """Start the worker loop."""
        self.running = True
        while self.running:
            try:
                await self._process_queue()
                await asyncio.sleep(0.5)  # Small delay to prevent busy waiting
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Worker error: {e}")
                await asyncio.sleep(1)
    
    def stop(self):
        """Stop the worker."""
        self.running = False
    
    async def add_task(self, task_type: str, total_items: int = 0) -> Task:
        """Add a task to the queue."""
        from app.models import SessionLocal
        db = SessionLocal()
        try:
            task = Task(
                task_type=task_type,
                status="pending",
                total_items=total_items,
                processed_items=0,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            await self._task_queue.put(task.id)
            return task
        finally:
            db.close()
    
    async def _process_queue(self):
        """Process tasks from the queue."""
        if self._task_queue.empty():
            return
        
        task_id = await self._task_queue.get()
        await self._execute_task(task_id)
    
    async def _execute_task(self, task_id: int):
        """Execute a task by its ID."""
        from app.models import SessionLocal
        db = SessionLocal()
        task = None
        try:
            task = db.query(Task).get(task_id)
            if not task:
                return
            
            self.current_task = task
            task.status = "running"
            task.updated_at = datetime.utcnow()
            db.commit()
            
            # Send notification about task start
            await send_gotify(
                "Task Started",
                f"Task #{task_id} ({task.task_type}) started"
            )
            
            if task.task_type == "scan":
                await self._run_scan(db, task)
            elif task.task_type.startswith("move"):
                await self._run_move(db, task)
            elif task.task_type == "batch_tags":
                await self._run_batch_tags(db, task)
            elif task.task_type == "batch_acoustid_identify":
                await self._run_batch_acoustid_identify(db, task)
            elif task.task_type == "batch_ollama_generate":
                await self._run_batch_ollama_generate(db, task)
            
            # Mark as completed
            task.status = "completed"
            task.updated_at = datetime.utcnow()
            db.commit()
            
            # Send notification about task completion
            await send_gotify(
                "Task Completed",
                f"Task #{task_id} ({task.task_type}) completed successfully"
            )
            
        except Exception as e:
            if task:
                task.status = "failed"
                task.error_message = str(e)
                task.updated_at = datetime.utcnow()
                db.commit()
                
                await send_gotify(
                    "Task Failed",
                    f"Task #{task_id} ({task.task_type}) failed: {str(e)}"
                )
        finally:
            self.current_task = None
            db.close()
    
    async def _run_scan(self, db: Session, task: Task):
        """Run scan operation with progress tracking."""
        from app.id3_handler import read_tags
        
        source = Path(config.source_dir).resolve()
        if not source.exists():
            source.mkdir(parents=True, exist_ok=True)
            task.status = "completed"
            return
        
        existing_paths = {row.filepath for row in db.query(AudioFile.filepath).all()}
        new_files = []
        
        # First pass: count files
        total_files = 0
        files_to_process = []
        for root, _, files in os.walk(source):
            for fname in files:
                ext = Path(fname).suffix.lower()
                if ext in config.extensions:
                    full_path = str(Path(root) / fname)
                    if full_path not in existing_paths:
                        files_to_process.append((root, fname, full_path))
                        total_files += 1
        
        task.total_items = total_files
        processed = 0
        
        # Second pass: process files
        for root, fname, full_path in files_to_process:
            try:
                tags = read_tags(full_path)
                
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
                )
                db.add(record)
                new_files.append(record)
            except Exception as e:
                print(f"Error processing {full_path}: {e}")
            
            processed += 1
            task.processed_items = processed
            db.commit()
            
            # Yield to event loop periodically
            if processed % 10 == 0:
                await asyncio.sleep(0)
        
        if new_files:
            await send_gotify(
                "Scan Complete",
                f"Found {len(new_files)} new files"
            )
    
    async def _run_move(self, db: Session, task: Task):
        """Run move operation with progress tracking."""
        import shutil
        mode = "move"
        if ":" in (task.task_type or ""):
            mode = (task.task_type.split(":", 1)[1] or "move").strip().lower()
        if mode not in {"move", "copy", "hardlink", "symlink"}:
            mode = "move"
        
        # Get files marked as pending_move
        files = db.query(AudioFile).filter(AudioFile.status == "pending_move").all()
        task.total_items = len(files)
        
        for i, record in enumerate(files):
            try:
                from app.file_organizer import render_path, extract_cover_art, detect_image_extension
                
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
                
                if mode == "move":
                    shutil.move(str(src), str(dest))
                elif mode == "copy":
                    shutil.copy2(str(src), str(dest))
                elif mode == "hardlink":
                    os.link(str(src), str(dest))
                elif mode == "symlink":
                    os.symlink(str(src), str(dest))
                
                # Save cover art if found
                if cover_data:
                    img_ext = detect_image_extension(cover_data)
                    cover_path = dest.parent / (dest.stem + img_ext)
                    cover_path.write_bytes(cover_data)
                
                # Clean up empty source dirs only for physical move.
                if mode == "move":
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
                
                log = OperationLog(
                    action="move",
                    details=f"Moved {record.filename} -> {dest}",
                    log_metadata=json.dumps({
                        "action": "move",
                        "filename": record.filename,
                        "from_path": record.original_filepath,
                        "to_path": str(dest.resolve()),
                        "cover_art_saved": bool(cover_data),
                        "mode": mode,
                    }),
                )
                db.add(log)
                
            except Exception as e:
                record.status = "error"
                log = OperationLog(action="error", details=str(e))
                db.add(log)
            
            task.processed_items = i + 1
            db.commit()
            
            # Yield to event loop periodically
            if (i + 1) % 10 == 0:
                await asyncio.sleep(0)
        
        moved_count = sum(1 for f in files if f.status == "moved")
        if moved_count:
            await send_gotify(
                "Move Complete",
                f"Moved {moved_count}/{len(files)} files"
            )
    
    async def _run_batch_tags(self, db: Session, task: Task):
        """Run batch tag update operation."""
        # This would need file IDs passed somehow
        # For now, just mark as completed
        task.processed_items = task.total_items

    async def _run_batch_acoustid_identify(self, db: Session, task: Task):
        """Batch ID3 update using AcoustID (audio fingerprint) only."""
        from app.id3_handler import read_tags, write_tags
        from app.models import TagSchema
        from app.music_identifier import identify_track

        def normalize_for_compare(s: str) -> str:
            t = (s or "").strip()
            if not t:
                return ""
            return t.rstrip(". ").strip().lower()

        def add_dot_marker(value: str) -> str:
            v = (value or "").strip()
            if not v:
                return "."
            if v.endswith("."):
                return v
            return v + "."

        def pick_best_by_year(candidates: list[dict]) -> tuple[str, str]:
            """Pick best album title + year (YYYY) from MusicBrainz candidates."""
            if not candidates:
                return "", ""
            with_year = [c for c in candidates if c.get("year")]
            if with_year:
                def sort_key(r: dict) -> tuple[int, str]:
                    y = str(r.get("year") or "")
                    y_int = int(y) if y.isdigit() else 10**9
                    return (-y_int, str(r.get("date") or ""))

                best = sorted(with_year, key=sort_key)[0]
                return best.get("title", "") or "", str(best.get("year", "") or "")[:4]

            with_date = [c for c in candidates if c.get("date")]
            if with_date:
                best = sorted(with_date, key=lambda x: str(x.get("date", "")))[-1]
                date_str = str(best.get("date", "") or "")
                return best.get("title", "") or "", date_str[:4] if len(date_str) >= 4 else ""

            return "", ""

        files = db.query(AudioFile).filter(AudioFile.status == "pending_acoustid").all()
        task.total_items = len(files)
        task.processed_items = 0

        for i, record in enumerate(files):
            current_tags = read_tags(record.filepath)
            current_artist = (current_tags.artist or "").strip()
            current_title = (current_tags.title or "").strip()
            current_artist_norm = normalize_for_compare(current_artist)
            current_title_norm = normalize_for_compare(current_title)

            cand_artist = ""
            cand_title = ""
            cand_album = ""
            cand_year = ""
            cand_track_number = 0

            try:
                result = await identify_track(record.filepath, debug=False)
                if result.get("status") == "identified":
                    releases = result.get("releases") or []
                    release_groups = result.get("release_groups") or []

                    album, year = pick_best_by_year(releases)
                    if (not year or not album) and release_groups:
                        rg_album, rg_year = pick_best_by_year(release_groups)
                        album = album or rg_album
                        year = year or rg_year

                    cand_artist = result.get("artist") or ""
                    cand_title = result.get("title") or ""
                    cand_album = album or ""
                    cand_year = year or ""
                    cand_track_number = result.get("track_number") or 0
            except Exception as e:
                print(f"[batch_acoustid_identify] AcoustID error for {record.filepath}: {e}")

            # Marker rules for artist/title only.
            if not cand_artist.strip():
                final_artist = add_dot_marker(current_artist) if current_artist_norm else "."
            else:
                if current_artist_norm and normalize_for_compare(cand_artist) == current_artist_norm:
                    final_artist = add_dot_marker(current_artist)
                else:
                    final_artist = cand_artist

            if not cand_title.strip():
                final_title = add_dot_marker(current_title) if current_title_norm else "."
            else:
                if current_title_norm and normalize_for_compare(cand_title) == current_title_norm:
                    final_title = add_dot_marker(current_title)
                else:
                    final_title = cand_title

            final_album = cand_album.strip() or None
            final_year = (str(cand_year).strip()[:4] if str(cand_year).strip() else "") or None
            final_track_number = (int(cand_track_number) if int(cand_track_number) > 0 else None)

            tags = TagSchema(
                artist=final_artist,
                title=final_title,
                album=final_album,
                track_number=final_track_number,
                year=final_year,
                medium_format=None,
                medium_number=None,
            )

            try:
                write_tags(record.filepath, tags)

                record.artist = final_artist
                record.title = final_title
                if final_album is not None:
                    record.album = final_album
                if final_year is not None:
                    record.year = final_year
                if final_track_number is not None:
                    record.track_number = final_track_number

                record.status = "processed"

                db.add(
                    OperationLog(
                        action="batch_acoustid_identified",
                        details=f"AcoustID auto-updated tags for {record.filename}",
                        log_metadata=json.dumps(
                            {
                                "artist": {"current": current_artist, "candidate": cand_artist, "final": final_artist},
                                "title": {"current": current_title, "candidate": cand_title, "final": final_title},
                                "album": {"current": current_tags.album or "", "candidate": cand_album, "final": final_album},
                                "year": {"current": current_tags.year or "", "candidate": cand_year, "final": final_year},
                                "track_number": {"current": current_tags.track_number or 0, "candidate": cand_track_number, "final": final_track_number},
                            }
                        ),
                    )
                )
            except Exception as e:
                record.status = "error"
                db.add(OperationLog(action="error", details=f"{record.filename}: {e}"))

            task.processed_items = i + 1
            db.commit()
            if (i + 1) % 5 == 0:
                await asyncio.sleep(0)

    async def _run_batch_ollama_generate(self, db: Session, task: Task):
        """Batch ID3 update using Ollama only (filename -> metadata)."""
        from app.id3_handler import read_tags, write_tags
        from app.models import TagSchema
        from app.ollama_handler import extract_tags_from_filename

        def normalize_for_compare(s: str) -> str:
            t = (s or "").strip()
            if not t:
                return ""
            return t.rstrip(". ").strip().lower()

        def add_dot_marker(value: str) -> str:
            v = (value or "").strip()
            if not v:
                return "."
            if v.endswith("."):
                return v
            return v + "."

        files = db.query(AudioFile).filter(AudioFile.status == "pending_ollama").all()
        task.total_items = len(files)
        task.processed_items = 0

        for i, record in enumerate(files):
            current_tags = read_tags(record.filepath)
            current_artist = (current_tags.artist or "").strip()
            current_title = (current_tags.title or "").strip()
            current_artist_norm = normalize_for_compare(current_artist)
            current_title_norm = normalize_for_compare(current_title)

            cand_artist = ""
            cand_title = ""
            cand_album = ""
            cand_year = ""
            cand_track_number = 0

            try:
                extracted = await extract_tags_from_filename(record.filename)
                if extracted:
                    cand_artist = extracted.get("artist") or ""
                    cand_title = extracted.get("title") or ""
                    cand_album = extracted.get("album") or ""
                    cand_year = extracted.get("year") or ""
                    cand_track_number = extracted.get("track_number") or 0
            except Exception as e:
                print(f"[batch_ollama_generate] Ollama error for {record.filename}: {e}")

            if not cand_artist.strip():
                final_artist = add_dot_marker(current_artist) if current_artist_norm else "."
            else:
                if current_artist_norm and normalize_for_compare(cand_artist) == current_artist_norm:
                    final_artist = add_dot_marker(current_artist)
                else:
                    final_artist = cand_artist

            if not cand_title.strip():
                final_title = add_dot_marker(current_title) if current_title_norm else "."
            else:
                if current_title_norm and normalize_for_compare(cand_title) == current_title_norm:
                    final_title = add_dot_marker(current_title)
                else:
                    final_title = cand_title

            final_album = cand_album.strip() or None
            final_year = (str(cand_year).strip()[:4] if str(cand_year).strip() else "") or None
            final_track_number = (int(cand_track_number) if int(cand_track_number) > 0 else None)

            tags = TagSchema(
                artist=final_artist,
                title=final_title,
                album=final_album,
                track_number=final_track_number,
                year=final_year,
                medium_format=None,
                medium_number=None,
            )

            try:
                write_tags(record.filepath, tags)

                record.artist = final_artist
                record.title = final_title
                if final_album is not None:
                    record.album = final_album
                if final_year is not None:
                    record.year = final_year
                if final_track_number is not None:
                    record.track_number = final_track_number

                record.status = "processed"

                db.add(
                    OperationLog(
                        action="batch_ollama_generated",
                        details=f"Ollama auto-updated tags for {record.filename}",
                        log_metadata=json.dumps(
                            {
                                "artist": {"current": current_artist, "candidate": cand_artist, "final": final_artist},
                                "title": {"current": current_title, "candidate": cand_title, "final": final_title},
                                "album": {"current": current_tags.album or "", "candidate": cand_album, "final": final_album},
                                "year": {"current": current_tags.year or "", "candidate": cand_year, "final": final_year},
                                "track_number": {"current": current_tags.track_number or 0, "candidate": cand_track_number, "final": final_track_number},
                            }
                        ),
                    )
                )
            except Exception as e:
                record.status = "error"
                db.add(OperationLog(action="error", details=f"{record.filename}: {e}"))

            task.processed_items = i + 1
            db.commit()
            if (i + 1) % 5 == 0:
                await asyncio.sleep(0)


# Global worker instance
worker = Worker()


async def start_worker():
    """Start the background worker."""
    await worker.start()


def get_worker() -> Worker:
    """Get the worker instance."""
    return worker
