# Music Organizer

![music-manager](music-manager.png)

A powerful web-based music file organizer with automatic tag reading, file organization, and audio fingerprint identification.

## Features

- 🎵 **Automatic Tag Reading** - Reads ID3, Vorbis, and MP4 tags from audio files
- 📁 **Smart File Organization** - Organizes files by artist, album, year using customizable templates
- 🔍 **Audio Fingerprint Identification** - Identifies tracks using AcoustID/MusicBrainz (even with empty tags)
- 🤖 **AI-Powered Analysis** - Uses local Ollama LLM to analyze filenames when other methods fail
- 🎨 **Cover Art Extraction** - Automatically extracts and saves album artwork
- 📊 **Batch Operations** - Edit tags and move multiple files at once
- 🔔 **Gotify Notifications** - Get notified about operations status
- 🌐 **Web Interface** - Modern, responsive web UI
- ⚡ **Background Processing** - Non-blocking operations with task queue

## Supported Formats

- MP3 (ID3 tags)
- FLAC (Vorbis comments)
- M4A/AAC (MP4 tags)
- OGG (Vorbis comments)
- WAV
- WMA
- OPUS

## Installation

### Prerequisites

- Python 3.10+
- pip
- fpcalc (for audio fingerprinting)
- Ollama (optional, for AI-based analysis)

### 1. Install System Dependencies

```bash
# Debian/Ubuntu
sudo apt-get update
sudo apt-get install -y python3-pip chromaprint-tools

# Install Ollama (optional, for AI filename analysis)
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.2  # or tinyllama, mistral
```

### 2. Clone and Setup

```bash
cd /path/to/music-organizer

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 3. Configure

```bash
# Copy example config
cp config.yaml.bak config.yaml

# Edit configuration
nano config.yaml
```

**Required settings:**
- `source_dir` - Directory with unorganized music files
- `output_dir` - Directory where organized files will be moved
- `acoustid.api_key` - Get free key at https://acoustid.org/api-key

### 4. Run

```bash
# Development mode
python -m uvicorn app.main:app --host 0.0.0.0 --port 8181 --reload

# Production mode
python -m uvicorn app.main:app --host 0.0.0.0 --port 8181 --workers 4
```

Access the web interface at: `http://your-server:8181`

## Usage

### Quick Start

1. **Add music files**
   - Copy audio files to your configured `source_dir`
   - Click **Scan** (or wait for auto-scan)

2. **Review imported files**
   - Open the **Files** tab and check items with status **New**
   - Verify detected metadata: Artist, Album, Title, Track, Year

3. **Identify files with missing metadata**
   - Open file details (`ℹ️`)
   - Click **🎵 Auto-Identify (AcoustID)** for fingerprint-based matching
   - If needed, use **✨ Parse Filename** as a fallback
   - Confirm with **✅ Apply Tags**

4. **Edit tags (optional)**
   - Select a file and edit metadata in the right panel
   - Save changes with **Save Tags**
   - For multiple files, use batch selection and apply shared fields

5. **Move and organize files**
   - Select one or more files
   - Click **Move Selected**
   - Files are moved to `output_dir` using your `path_template`
   - Album artwork is extracted and saved alongside tracks

### Recommended Workflow

1. Scan `source_dir`
2. Auto-identify unknown tracks
3. Manually review low-confidence matches
4. Save or batch-apply tags
5. Move selected files to the organized library

### Path Template

Default template:
```
{Artist Name}/{Album Title} ({Release Year})/{track:00} {Track Title}
```

Example output:
```
output/
├── Pink Floyd/
│   └── The Dark Side of the Moon (1973)/
│       ├── 01 Speak to Me.mp3
│       ├── 01 Speak to Me.jpg    ← Cover art
│       ├── 02 Breathe.mp3
│       ├── 02 Breathe.jpg
│       └── ...
├── The Beatles/
│   └── Abbey Road (1969)/
│       ├── 01 Come Together.mp3
│       ├── 01 Come Together.jpg
│       └── ...
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/files` | List files with filters |
| GET | `/api/files/{id}` | Get file details |
| GET | `/api/files/{id}/detail` | Get extended file info |
| GET | `/api/files/{id}/tags` | Get file tags |
| PUT | `/api/files/{id}/tags` | Update tags |
| POST | `/api/files/{id}/identify` | Identify track (AcoustID) |
| POST | `/api/files/{id}/analyze-llm` | Analyze filename (Ollama LLM) |
| POST | `/api/files/{id}/apply-tags` | Apply confirmed tags |
| GET | `/api/ollama/status` | Check Ollama availability |
| POST | `/api/files/move` | Move selected files |
| POST | `/api/scan` | Scan source directory |
| GET | `/api/tasks` | List background tasks |
| GET | `/api/logs` | Operation logs |
| GET | `/api/config` | Get configuration |
| PUT | `/api/config` | Update configuration |

## Configuration

### config.yaml

```yaml
# Database
database: ./music_organizer.db

# Audio extensions
extensions: [.mp3, .flac, .m4a, .wav, .ogg]

# Gotify notifications
gotify:
  url: https://gotify.example.com/
  token: YOUR_TOKEN

# AcoustID for audio identification
acoustid:
  api_key: YOUR_ACOUSTID_KEY

# Directories
source_dir: /music/unorganized
output_dir: /music/organized

# Path template
path_template: '{Artist Name}/{Album Title} ({Release Year})/{track:00} {Track Title}'

# Auto-scan interval (seconds, 0 = disabled)
scan_interval: 30

# Optional proxy for external services
# (Gotify, AcoustID, MusicBrainz, Ollama checks)
proxy_url: ""  # optional explicit URL, e.g. socks5://user:pass@127.0.0.1:1080
proxy_type: socks5   # http | https | socks4 | socks5
proxy_host: 127.0.0.1
proxy_port: 1080
proxy_username: ""
proxy_password: ""
```

## Background Tasks

The application uses a background worker for:
- Scanning source directory
- Moving files (prevents UI freezing)
- Batch tag operations

Tasks are shown in the "Active Tasks" panel with progress.

## Troubleshooting

### Files not appearing after scan
- Check `source_dir` path is correct
- Verify file extensions are in the `extensions` list
- Check logs for errors

### AcoustID identification fails
- Ensure `fpcalc` is installed: `which fpcalc`
- Check API key in Settings → AcoustID API Key
- Test key at https://acoustid.org/api-key

### Move operation fails
- Check `output_dir` is writable
- Verify disk space
- Check logs for specific errors

### Tags not saving
- Ensure file is not write-protected
- Check file format is supported
- Try restarting the application

## License

MIT License

## Credits

- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Mutagen](https://github.com/quodlibet/mutagen) - Audio tag handling
- [AcoustID](https://acoustid.org/) - Audio fingerprinting
- [MusicBrainz](https://musicbrainz.org/) - Music metadata
- [Gotify](https://gotify.net/) - Notifications
