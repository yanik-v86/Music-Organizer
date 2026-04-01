import yaml
import os
from urllib.parse import quote
from urllib.parse import urlparse
from pathlib import Path
from pydantic import BaseModel
from typing import Optional


class GotifyConfig(BaseModel):
    url: str = ""
    token: str = ""


class AcoustidConfig(BaseModel):
    api_key: str = ""


class OllamaConfig(BaseModel):
    url: str = "http://localhost:11434"
    model: str = "tinyllama"


class AppConfig(BaseModel):
    source_dir: str = "./source"
    output_dir: str = "./output"
    database: str = "./music_organizer.db"
    path_template: str = "{Artist Name}/{Album Title} ({Release Year})/{track:00} {Track Title}"
    extensions: list[str] = [".mp3", ".flac", ".m4a", ".wav", ".ogg", ".wma", ".aac", ".opus"]
    gotify: GotifyConfig = GotifyConfig()
    acoustid: AcoustidConfig = AcoustidConfig()
    ollama: OllamaConfig = OllamaConfig()
    scan_interval: int = 30
    proxy_url: str = ""
    proxy_type: str = "http"
    proxy_host: str = ""
    proxy_port: int = 0
    proxy_username: str = ""
    proxy_password: str = ""
    mobile_player_only: bool = False

#CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.yaml")
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
CONFIG_PATH = os.environ.get("CONFIG_PATH", str(_DEFAULT_CONFIG_PATH))


def load_config() -> AppConfig:
    path = Path(CONFIG_PATH)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return AppConfig(**data)
    return AppConfig()


def should_bypass_proxy_for_url(url: str) -> bool:
    """Return True for loopback/local destinations that should skip proxy."""
    target = (url or "").strip()
    if not target:
        return False
    try:
        parsed = urlparse(target if "://" in target else f"http://{target}")
    except Exception:
        return False

    host = (parsed.hostname or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def get_httpx_client_kwargs(target_url: str = "") -> dict:
    """Build shared AsyncClient kwargs with optional proxy."""
    if should_bypass_proxy_for_url(target_url):
        return {}

    proxy_url = get_effective_proxy_url()
    if proxy_url:
        return {"proxy": proxy_url}
    return {}


def get_effective_proxy_url() -> str:
    """Return explicit proxy_url or build it from structured proxy fields."""
    direct = (config.proxy_url or "").strip()
    if direct:
        return direct

    host = (config.proxy_host or "").strip()
    if not host:
        return ""

    scheme = (config.proxy_type or "http").strip().lower()
    if scheme not in {"http", "https", "socks4", "socks5"}:
        scheme = "http"

    port = int(config.proxy_port or 0)
    auth = ""
    username = (config.proxy_username or "").strip()
    password = config.proxy_password or ""
    if username:
        auth = quote(username, safe="")
        if password:
            auth += ":" + quote(password, safe="")
        auth += "@"

    port_part = f":{port}" if port > 0 else ""
    return f"{scheme}://{auth}{host}{port_part}"


config = load_config()
