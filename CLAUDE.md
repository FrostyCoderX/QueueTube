# QueueTube — Claude Code Briefing

## Project Overview

**QueueTube** is a standalone local Python desktop application that provides a clean GUI for `yt-dlp`.

## Design Goals

The actual goals, in priority order — these outrank any implementation detail below:

1. A simple GUI wrapper around a command-line tool (yt-dlp)
2. Lightweight — minimal dependencies, fast start, small footprint
3. **No server process** — the app runs as a plain local program; nothing listens on a port
4. No Electron, no packaging complexity — just a runnable Python app

CustomTkinter is the *current* UI choice, made for convenience — it is **not a
requirement**. Any lightweight GUI approach that honors the no-server constraint
is acceptable (e.g. pywebview's in-process bridge would qualify; Electron or a
localhost web server would not). See BACKLOG.md for the considered upgrade path.

## Environment Setup

This project uses a virtual environment. Always activate it before running or installing anything.

```bash
# First-time setup
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run
source venv/bin/activate
python main.py
```

> **Claude Code note:** All `pip install` and `python` commands must be run inside the activated venv.
> Never install packages to the system Python.
> If a dependency is missing, install it with `pip install <package>` inside the venv — do not suggest global installs.

## Tech Stack

- **UI:** CustomTkinter (dark theme preferred) — current choice, not a mandate; see Design Goals
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
│  QUEUE (multi-line URL box)     │  SETTINGS SIDEBAR   │
│  [Start] [End]  (optional)      │  (scrollable)       │
│─────────────────────────────────│                     │
│  [Download Queue][Stop][Clear]  │  FORMAT             │
│─────────────────────────────────│  OUTPUT             │
│  Progress bar    + percent      │  SUBTITLES          │
│  Status label                   │  MUSIC              │
│─────────────────────────────────│  ADVANCED           │
│  HISTORY TABLE (Treeview)       │                     │
│  [Show/Hide Raw Log] toggle     │  (sections hold the │
│  RAW LOG (collapsible textbox)  │   settings below)   │
└─────────────────────────────────┴─────────────────────┘
```

## Feature Spec

> **Note:** Last synced to the source on 2026-07-20. If they ever differ, the
> source code is authoritative — see CONTEXT.md for the build log. Keep the
> code-level constants (format map, defaults) in config.py only; this file
> deliberately does not duplicate them.

### URL Input
- Multi-line `CTkTextbox`, one URL per line
- Two optional fields below: `Start Time` and `End Time` (HH:MM:SS format)
- If both are blank → full video download
- If filled → passed to `yt-dlp` `download_ranges` + requires ffmpeg

### Settings Sidebar (persisted to config.json)

| Setting | UI Element | yt-dlp mapping |
|---|---|---|
| Format | Dropdown | `FORMAT_MAP` in config.py (8 entries incl. MP4 variants and Audio Only MP3/Opus) |
| Download playlists | Checkbox (default OFF) | `noplaylist: True/False` (+ `ignoreerrors` when ON) |
| Skip sponsor segments | Checkbox | `sponsorblock_remove: [sponsor, intro, outro]` |
| Filename template | Dropdown | `FILENAME_TEMPLATES` in config.py |
| Auto-subfolders | Checkbox | `outtmpl` includes `%(uploader)s/` prefix |
| Save thumbnail file | Checkbox (default OFF) | `writethumbnail` |
| Embed metadata + thumbnail | Checkbox | `embedmetadata`, `embedthumbnail` + postprocessors |
| Embed subtitles | Checkbox | `writesubtitles`, `embedsubtitles`, language from the shared Language field |
| Transcript only (.srt) | Checkbox + Language field | `skip_download`, `writesubtitles`, `writeautomaticsub`, `subtitleslangs` |
| Embed album art | Checkbox | `embedthumbnail` + `EmbedThumbnail` postprocessor |
| Save location | Folder picker button | `paths: {'home': selected_dir}` |
| Cookies from browser | Dropdown | `cookiesfrombrowser` |
| Remote JS solver | Checkbox (default OFF) | `--remote-components ejs:github` via `parse_options` |
| Custom args | Single-line text input | `shlex.split` + `parse_options`, only non-default values merged |

The authoritative format map and defaults live in `config.py`
(`FORMAT_MAP`, `FILENAME_TEMPLATES`, `DEFAULTS`) — do not copy values
from this file into code; read config.py instead.

### Download Engine (`downloader.py`)
- Use `yt-dlp` Python API (`yt_dlp.YoutubeDL`), not subprocess
- Parse URL textarea on download start → strip blank lines
- Download URLs **sequentially** in a single background thread (do not spawn one thread per URL)
- Progress hook function passed to `ydl_opts` → emits progress back to UI via queue or callback
- On completion of each URL, fire a callback to update history table
- Thread must be stoppable; Stop cancels the in-progress download safely by
  raising `DownloadCancelled` from the progress hook (partial `.part` files
  resume on retry)

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
- Loads `config.json` on startup; writes on every settings change
- If file missing, malformed, or not a JSON object → silently fall back to defaults
- Missing keys are backfilled from `DEFAULTS` (so new settings never crash old configs)
- The authoritative `DEFAULTS` dict lives in `config.py` — every new setting
  must be added there with a sensible default

### ffmpeg Check
- On app startup, run `shutil.which("ffmpeg")`
- If not found → show a non-blocking warning banner at the top of the UI:
  `"⚠ ffmpeg not found in PATH. Time-slicing and subtitle embedding will not work."`
- Do not block the app — features that require ffmpeg simply fail gracefully with an error in the Raw Log

## Key Commands

```bash
# Install dependencies (inside the venv)
pip install -r requirements.txt

# Run
python main.py
```

## Verification Pattern

How changes get verified in this project (established 2026-07-20):

- **Compile check**: `py_compile` on all five modules after every edit batch.
- **Stub tests**: replace `downloader.yt_dlp.YoutubeDL` with a fake class whose
  `download()` replays scripted progress/postprocessor hook events, then assert
  on the history/status events drained from `Downloader.event_queue`. This
  covers playlist, cancel, transcript, and failure branches without network.
- **Real E2E**: download `https://www.youtube.com/watch?v=jNQXAC9IVRw`
  ("Me at the zoo", 19s — small and stable) into the session scratchpad, and
  assert on history events and files on disk. Clean up the files afterwards.
- **GUI construction test**: instantiate `App()`, call `.update()`, assert on
  widget state, then `.destroy()` — catches wiring errors without a visual check.
- **Visual checks**: ask the user for a Win+Shift+S snip of the window rather
  than capturing the desktop.
- On Windows use `./venv/Scripts/python.exe` and set `PYTHONIOENCODING=utf-8`
  when test output contains ✓/✗/■ glyphs (cp1252 console chokes otherwise).

## Constraints & Notes

- No packaging (PyInstaller etc.) required at this stage
- No network calls other than those made by yt-dlp itself
- Do not use subprocess to call yt-dlp — use the Python API only
- CustomTkinter theme: `dark`, color theme: `blue` (default)
- Python 3.10+ assumed
- The app must remain responsive during downloads — all blocking work stays in the background thread
- Do not use `after()` polling loops tighter than 100ms
