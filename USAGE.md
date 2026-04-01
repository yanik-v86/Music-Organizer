# 📚 Complete Music Organizer Usage Guide

## 📋 Table of Contents

1. [What the service does](#what-the-service-does)
2. [Installation](#installation)
3. [First launch](#first-launch)
4. [Main interface](#main-interface)
5. [Step-by-step guide](#step-by-step-guide)
6. [Track auto-identification](#track-auto-identification)
7. [Working with tags](#working-with-tags)
8. [Moving files](#moving-files)
9. [Settings](#settings)
10. [Frequently asked questions](#frequently-asked-questions)

---

## 🎯 What the service does

Music Organizer is a web application for automatic music library organization. It:

- ✅ Reads metadata tags from audio files (MP3, FLAC, M4A, OGG, and others)
- ✅ Identifies tracks by audio fingerprint (even when tags are missing)
- ✅ Sorts files into folders: Artist/Album/Year
- ✅ Extracts album artwork
- ✅ Lets you edit metadata tags
- ✅ Sends operation status notifications

---

## 🛠️ Installation

### Step 1: System requirements

```bash
# Update packages
sudo apt-get update

# Install Python and dependencies
sudo apt-get install -y python3 python3-pip

# Install fingerprint tool (required for auto-identification)
sudo apt-get install -y chromaprint-tools

# Verify installation
fpcalc -version

# (Optional) Install Ollama for AI analysis
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.2  # or tinyllama, mistral
```

### Step 2: Install the app

```bash
# Go to the app directory
cd /home/user/music-organizer

# Create a virtual environment
python3 -m venv venv

# Activate the environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure

```bash
# Copy example config
cp config.yaml.bak config.yaml

# Open config for editing
nano config.yaml
```

**Minimum configuration:**

```yaml
# Folder with unorganized files
source_dir: /home/user/music-organizer/source

# Folder for organized files
output_dir: /home/user/music-organizer/output

# API key for identification (get one at https://acoustid.org/api-key)
acoustid:
  api_key: YOUR_ACOUSTID_KEY
```

---

## 🚀 First launch

```bash
# Virtual environment should be active
source venv/bin/activate

# Start server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8181 --reload
```

Open in browser: `http://your-server:8181`

---

## 🖥️ Main interface

### Tabs

| Tab | Description |
|-----|-------------|
| **Files** | File list, tags, and operations |
| **Logs** | Operation history |
| **Settings** | Application settings |

### Controls in the Files tab

- **Scan** — scan source folder
- **Move Selected** — move selected files
- **Action for Processed** — actions for already processed items
- **✨ Auto-Fill Tags** — autofill tags for selected files
- **Filters** — search by artist, album, year

---

## 📖 Step-by-step guide

### Step 1: Add files

```bash
# Copy music files into source_dir
cp /path/to/music/*.mp3 /home/user/music-organizer/source/
```

Or from the web interface:
1. Open the **Files** tab
2. Click **Scan**
3. Files appear with status **New**

### Step 2: Review tags

1. Click a file in the list
2. In the right panel you will see detected tags:
   - Artist
   - Album
   - Title
   - Track #
   - Year

### Step 3: Fix tags (if needed)

**If tags are empty:**

1. Click **ℹ️** next to the file
2. Click **🎵 Auto-Identify (AcoustID)**
3. Wait for identification (5-10 seconds)
4. Review suggested tags
5. Edit if needed
6. Click **✅ Apply Tags**

**Alternative: parse filename**

1. Click **✨ Parse Filename**
2. Tags will be extracted from the file name
3. Example: `01 Artist - Title.mp3` → Artist + Title

### Step 4: Edit tags manually (optional)

1. Select a file
2. Change fields in the right panel
3. Click **Save Tags**

**Batch editing:**
1. Select multiple files (checkboxes)
2. Edit common tags in the right panel
3. Click **Batch Save**

### Step 5: Move files

1. Select files to move
2. Click **Move Selected**
3. Confirm operation
4. Files are moved into `output_dir`

**Resulting structure example:**
```
output/
├── Artist Name/
│   └── Album Title (2024)/
│       ├── 01 Track Title.mp3
│       ├── 01 Track Title.jpg  ← Cover art
│       └── 02 Another Track.mp3
```

---

## 🔍 Track auto-identification

### When to use

- ✅ Tags are missing or incorrect
- ✅ Filenames are unclear
- ✅ You need accurate metadata

### How it works

1. **fpcalc** generates an audio fingerprint
2. **AcoustID** searches for matches
3. **MusicBrainz** returns metadata:
   - Artist
   - Title
   - Album
   - Release year
   - Release list

### Identification flow

```
┌─────────────────────────────────────┐
│ 1. Click ℹ️ on a file               │
│ 2. Click 🎵 Auto-Identify           │
│ 3. AcoustID analyzes (5-10 sec)     │
│ 4. If not found → Ollama LLM        │
│ 5. Found tags are displayed          │
│ 6. Review and edit                   │
│ 7. Click ✅ Apply Tags               │
└─────────────────────────────────────┘
```

**Identification methods (in order):**

1. **AcoustID** (audio fingerprint) — most accurate, often >90% confidence
2. **Ollama LLM** (AI filename analysis) — fallback when AcoustID fails
3. **Filename parsing** — simple heuristic fallback

### Confidence levels

| Confidence | Action |
|------------|--------|
| > 80% | Tags are auto-filled |
| 60-80% | Tags are suggested for review |
| < 60% | Current tags are shown |

### If identification fails

- Try **✨ Parse Filename**
- Edit tags manually
- Check AcoustID API key in settings

---

## 🏷️ Working with tags

### Supported tag formats

| Format | Tags |
|--------|------|
| MP3 | ID3v1, ID3v2 |
| FLAC | Vorbis Comments |
| M4A | MP4 Tags |
| OGG | Vorbis Comments |

### Tag fields

| Field | Description | Example |
|-------|-------------|---------|
| Artist | Performer name | The Beatles |
| Album | Album title | Abbey Road |
| Title | Track title | Come Together |
| Track # | Track number | 1 |
| Year | Release year | 1969 |
| Medium Format | Media format | CD, Digital Media |
| Medium # | Disc number | 1 |

### Batch tag operations

**Auto-fill selected files:**

1. Select files (checkboxes)
2. Click **✨ Auto-Fill Tags**
3. Confirm operation
4. Tags are extracted from filenames

**Batch edit:**

1. Select files
2. Fill common tags (Artist, Album, Year)
3. Click **Batch Save**
4. Tags are applied to all selected files

---

## 📁 Moving files

### Path template

Default template:
```
{Artist Name}/{Album Title} ({Release Year})/{track:00} {Track Title}
```

### Available tokens

| Token | Description | Example |
|-------|-------------|---------|
| `{Artist Name}` | Artist name | Pink Floyd |
| `{Album Title}` | Album title | The Wall |
| `{track:00}` | 2-digit track number | 01, 02, 10 |
| `{Track Title}` | Track title | Another Brick in the Wall |
| `{Release Year}` | Release year | 1979 |
| `{Medium Format}` | Media format | CD, Digital Media |
| `{medium:00}` | 2-digit disc number | 01, 02 |

### Output examples

**Single disc:**
```
output/
└── Pink Floyd/
    └── The Wall (1979)/
        ├── 01 In the Flesh?.mp3
        ├── 02 The Thin Ice.mp3
        └── 03 Another Brick in the Wall.mp3
```

**Multiple discs:**
```
output/
└── The Beatles/
    └── The White Album (1968)/
        ├── CD1/
        │   ├── 01 Back in the U.S.S.R..mp3
        │   └── 02 Dear Prudence.mp3
        └── CD2/
            ├── 01 Revolution 1.mp3
            └── 02 Honey Pie.mp3
```

### Undo a move

If a file was moved incorrectly:

1. Open file details (**ℹ️**)
2. Click **↩️ Move Back**
3. File returns to source folder
4. Status changes to **Processed**

---

## ⚙️ Settings

### Settings tab

#### Source Directory
Folder for unorganized files. Default: `./source`

#### Output Directory
Folder for organized files. Default: `./output`

#### Path Template
Template for folder/file structure. Use supported tokens.

#### Extensions
Supported file extensions (comma-separated).

#### Gotify URL / Token
Notification settings (optional).

#### AcoustID API Key
Key used for auto-identification. Get one at https://acoustid.org/api-key

#### Scan Interval
Auto-scan interval in seconds. `0` = disabled.

### Test notifications

1. Fill in Gotify URL and Token
2. Click **Test Notifications**
3. Confirm notification is received

### Ollama settings (optional)

**Ollama URL**: `http://localhost:11434`  
**Ollama Model**: `llama3.2` (or `tinyllama`, `mistral`)

Install example:
```bash
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.2
```

Click **Test Ollama Connection** to verify.

---

## ❓ Frequently asked questions

### Files do not appear after scan

**Check:**
- `source_dir` exists
- File extensions are supported
- Files were not already imported earlier

**Fix:**
```bash
# Check source folder
ls -la /path/to/source

# Check extensions
ls /path/to/source/*.mp3
```

### Identification fails

**Possible issues:**
- `fpcalc` is not installed
- Invalid AcoustID API key
- No internet connection

**Fix:**
```bash
# Check fpcalc
which fpcalc

# Check API key
# Open Settings → AcoustID API Key
# Get a new key at https://acoustid.org/api-key
```

### Tags are not saved

**Possible causes:**
- File is write-protected
- Unsupported format
- Permission issue

**Fix:**
```bash
# Check permissions
ls -l file.mp3

# Update permissions
chmod 644 file.mp3
```

### Move operation does not work

**Check:**
- `output_dir` exists and is writable
- Enough free disk space
- No filename conflicts

**Fix:**
```bash
# Create output folder
mkdir -p /path/to/output

# Check disk space
df -h /path/to/output
```

### How to update the application

```bash
# Stop server (Ctrl+C)

# Update dependencies
pip install -r requirements.txt --upgrade

# Start again
python -m uvicorn app.main:app --host 0.0.0.0 --port 8181 --reload
```

### Database backup

```bash
# Backup database
cp music_organizer.db music_organizer.db.backup

# Backup config
cp config.yaml config.yaml.backup
```

---

## 📞 Support

If you run into issues:

1. Check logs in the **Logs** tab
2. Check server console output
3. Verify all dependencies are installed
4. Verify directory permissions

---

## 🎯 Quick reference

| Action | Button/Command |
|--------|----------------|
| Add files | Copy to `source_dir` + Scan |
| Identify tags | ℹ️ → 🎵 Auto-Identify |
| Parse filename | ℹ️ → ✨ Parse Filename |
| Edit tags | Click file → Edit → Save |
| Batch edit | Select files → Batch Save |
| Move files | Select files → Move Selected |
| Move file back | ℹ️ → ↩️ Move Back |
| Open settings | **Settings** tab |

---

**Guide version:** 1.1  
**Last updated:** 2026
