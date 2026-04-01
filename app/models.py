from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, create_engine, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from pydantic import BaseModel
from typing import Optional

from app.config import config

Base = declarative_base()
engine = create_engine(f"sqlite:///{config.database}", echo=False)
SessionLocal = sessionmaker(bind=engine)


class AudioFile(Base):
    __tablename__ = "audio_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False, unique=True)
    original_filepath = Column(String, default="")  # Original path before move
    artist = Column(String, default="")
    album = Column(String, default="")
    title = Column(String, default="")
    track_number = Column(Integer, default=0)
    year = Column(String, default="")
    medium_format = Column(String, default="")
    medium_number = Column(Integer, default=1)
    status = Column(String, default="new")  # new | processed | moved | error
    file_size = Column(Integer, default=0)  # File size in bytes
    bitrate = Column(String, default="")  # Bitrate info
    sample_rate = Column(String, default="")  # Sample rate info
    duration = Column(String, default="")  # Duration info
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String, nullable=False)
    details = Column(Text, default="")
    log_metadata = Column(Text, default="")  # JSON metadata for detailed info
    timestamp = Column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_type = Column(String, nullable=False)  # scan | move | batch_tags
    status = Column(String, default="pending")  # pending | running | completed | failed
    total_items = Column(Integer, default=0)
    processed_items = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    error_message = Column(Text, default="")


def init_db():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Pydantic Schemas ---

class TagSchema(BaseModel):
    artist: Optional[str] = None
    album: Optional[str] = None
    title: Optional[str] = None
    track_number: Optional[int] = None
    year: Optional[str] = None
    medium_format: Optional[str] = None
    medium_number: Optional[int] = None


class AudioFileSchema(BaseModel):
    id: int
    filename: str
    filepath: str
    original_filepath: str
    artist: str
    album: str
    title: str
    track_number: int
    year: str
    medium_format: str
    medium_number: int
    status: str
    file_size: int
    bitrate: str
    sample_rate: str
    duration: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AudioFileDetailSchema(BaseModel):
    """Extended file information for modal display."""
    id: int
    filename: str
    filepath: str
    original_filepath: str
    artist: str
    album: str
    title: str
    track_number: int
    year: str
    medium_format: str
    medium_number: int
    status: str
    file_size: int
    file_size_formatted: str
    bitrate: str
    sample_rate: str
    duration: str
    extension: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BatchTagUpdate(BaseModel):
    ids: list[int]
    tags: TagSchema


class MoveRequest(BaseModel):
    ids: list[int]
    mode: Optional[str] = "move"


class StatusUpdate(BaseModel):
    status: str


class BatchStatusUpdate(BaseModel):
    ids: list[int]
    status: str


class LogSchema(BaseModel):
    id: int
    action: str
    details: str
    timestamp: datetime

    class Config:
        from_attributes = True


class ConfigUpdate(BaseModel):
    source_dir: Optional[str] = None
    output_dir: Optional[str] = None
    path_template: Optional[str] = None
    extensions: Optional[list[str]] = None
    gotify_url: Optional[str] = None
    gotify_token: Optional[str] = None
    acoustid_api_key: Optional[str] = None
    scan_interval: Optional[int] = None
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    proxy_url: Optional[str] = None
    proxy_type: Optional[str] = None
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None
    mobile_player_only: Optional[bool] = None


class TaskSchema(BaseModel):
    id: int
    task_type: str
    status: str
    total_items: int
    processed_items: int
    created_at: datetime
    updated_at: datetime
    error_message: str = ""

    class Config:
        from_attributes = True
