# QueueTube — Claude Code Briefing

## Project Overview

**QueueTube** is a standalone local Python desktop application that provides a clean GUI for `yt-dlp`.
Built with `CustomTkinter`. No web server, no Electron, no packaging complexity — just a runnable Python app.

## Environment Setup

This project uses a virtual environment. Always activate it before running or installing anything.

```bash
# First-time setup
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install yt-dlp customtkinter

# Run
source venv/bin/activate
python main.py
```

> **Claude Code note:** All `pip install` and `python` commands must be run inside the activated venv.
> Never install packages to the system Python.
> If a dependency is missing, install it with `pip install <package>` inside the venv — do not suggest global installs.

## Tech Stack

- **UI:** CustomTkinter (dark theme preferred)
- **Downloader:** yt-dlp (Python API, not subprocess)
- **Media processing:** ffmpeg (system PATH, checked at startup)
- **Config persistence:** JSON (`config.json` in app directory)
- **Threading:** Python `threading` module for background downloads

## Project Structure

```
queuetube/
├── main.py               # Entry point — launches the CTk app
├── app.py                # Root CTk window, layout orchestration
├── downloader.py         # All yt-dlp logic, threading, progress hooks
├── config.py             # Load/save config.json, defaults
├── history.py            # History log model + Treeview widget wrapper
├── config.json           # Auto-generated on first run (gitignored)
└── requirements.txt      # yt-dlp, customtkinter
```

## UI Layout

Single window. Two-column layout:

```
┌─────────────────────────────────┬─────────────────────┐
│  URL INPUT AREA (multi-line)    │  SETTINGS SIDEBAR   │
│  [Start HH:MM:SS] [End HH:MM:SS]│                     │
│─────────────────────────────────│  Format dropdown    │
│  [Download Queue] button        │  Playlist checkbox  │
│─────────────────────────────────│  Auto-subfolders    │
│  Progress bar + status label    │  Embed subtitles    │
│─────────────────────────────────│  Embed metadata     │
│  HISTORY TABLE (Treeview)       │  Save location      │
│  [Show/Hide Raw Log] toggle     │  Custom args field  │
│  RAW LOG (collapsible textbox)  │                     │
└─────────────────────────────────┴─────────────────────┘
```

## Feature Spec

### URL Input
- Multi-line `CTkTextbox`, one URL per line
- Two optional fields below: `Start Time` and `End Time` (HH:MM:SS format)
- If both are blank → full video download
- If filled → passed to `yt-dlp` `download_ranges` + requires ffmpeg

### Settings Sidebar (persisted to config.json)

| Setting | UI Element | yt-dlp mapping |
|---|---|---|
| Format | Dropdown | See format map below |
| Download playlists | Checkbox (default OFF) | `noplaylist: True/False` |
| Auto-subfolders | Checkbox | `outtmpl` includes `%(uploader)s/` prefix |
| Embed subtitles | Checkbox | `writesubtitles`, `subtitleslangs: ['en']`, `embedsubtitles` |
| Embed metadata + thumbnail | Checkbox | `embedmetadata`, `embedthumbnail`, `writethumbnail` |
| Save location | Folder picker button | `paths: {'home': selected_dir}` |
| Custom args | Single-line text input | Appended raw (parsed carefully) |

**Format dropdown map:**
```python
FORMAT_MAP = {
    "Best Available":  "bestvideo+bestaudio/best",
    "1080p Limit":     "bestvideo[height<=1080]+bestaudio/best",
    "720p Limit":      "bestvideo[height<=720]+bestaudio/best",
    "Audio Only (MP3)": None,  # triggers extract_audio + audio_format: mp3
}
```

### Download Engine (`downloader.py`)
- Use `yt-dlp` Python API (`yt_dlp.YoutubeDL`), not subprocess
- Parse URL textarea on download start → strip blank lines
- Download URLs **sequentially** in a single background thread (do not spawn one thread per URL)
- Progress hook function passed to `ydl_opts` → emits progress back to UI via queue or callback
- On completion of each URL, fire a callback to update history table
- Thread must be stoppable (set a flag; check between URLs — do not kill mid-download)

### Progress Feedback
- `CTkProgressBar` — updates per `progress_hook` `downloaded_bytes / total_bytes`
- Status label below bar: shows current filename or URL being processed
- On idle: "Ready" / on active: "Downloading 2 of 5..." / on done: "All done."

### History Table (`history.py`)
- `ttk.Treeview` (CTk-compatible styling acceptable) inside a scrollable frame
- Columns: `Title`, `Size`, `Resolution`, `Status`
- Status values: `✓ Success` (green) or `✗ Failed` (red)
- Populated by callbacks from `downloader.py` after each URL completes
- Populated data is NOT persisted between sessions (in-memory only, reset on relaunch)

### Raw Log (collapsible)
- `CTkTextbox` (read-only, monospace, dark bg)
- Hidden by default; toggled by a `Show Logs / Hide Logs` button
- Captures all yt-dlp stdout/stderr via a custom logger class passed to `yt_dlp.YoutubeDL`
- Auto-scrolls to bottom on new output

### Config (`config.py`)
- Loads `config.json` on startup; writes on every settings change (or on app close)
- If file missing or malformed → silently fall back to defaults
- Defaults:
```python
DEFAULTS = {
    "format": "Best Available",
    "noplaylist": True,
    "auto_subfolders": False,
    "embed_subtitles": False,
    "embed_metadata": True,
    "save_location": "~/Downloads",
    "custom_args": ""
}
```

### ffmpeg Check
- On app startup, run `shutil.which("ffmpeg")`
- If not found → show a non-blocking warning banner at the top of the UI:
  `"⚠ ffmpeg not found in PATH. Time-slicing and subtitle embedding will not work."`
- Do not block the app — features that require ffmpeg simply fail gracefully with an error in the Raw Log

## Key Commands

```bash
# Install dependencies
pip install yt-dlp customtkinter

# Run
python main.py
```

## Constraints & Notes

- No packaging (PyInstaller etc.) required at this stage
- No network calls other than those made by yt-dlp itself
- Do not use subprocess to call yt-dlp — use the Python API only
- CustomTkinter theme: `dark`, color theme: `blue` (default)
- Python 3.10+ assumed
- The app must remain responsive during downloads — all blocking work stays in the background thread
- Do not use `after()` polling loops tighter than 100ms
