# QueueTube — Build Context

## Status
Released and actively maintained. Last round 2026-07-20: bug fixes,
mid-download stop, final-file tracking, UI polish, docs synced to source.
Next planned work lives in BACKLOG.md under "Planned Next".

## Build Log

### 2026-04-13 — Initial Scaffold
Created all source files from scratch:
- `requirements.txt` — yt-dlp, customtkinter
- `config.py` — load/save config.json with defaults
- `downloader.py` — yt-dlp Python API, sequential background thread, progress hooks
- `history.py` — in-memory history model + Treeview widget
- `app.py` — root CTk window, two-column layout, all UI wiring
- `main.py` — entry point
- `run.bat` — double-click launcher (activates venv, runs main.py)

### 2026-04-13 — Bug fixes + UI improvements
**Bugs fixed:**
- `noplaylist` checkbox initialised from raw config value (inverted semantics). Fixed: init with `not config["noplaylist"]`, save writes inverse back.
- Custom args field saved to config but never applied to downloads. Fixed: parsed via `shlex.split` + `yt_dlp.parse_options` in `_build_opts`.
- `embed_metadata` (default ON) added FFmpeg postprocessors even without ffmpeg. Fixed: guarded with `shutil.which("ffmpeg")`.
- Progress bar stuck after Stop. Fixed: "done" event always resets bar to 0.

**UI additions:**
- Clear button — wipes the URL box.
- URL count label — updates live on key/paste, e.g. "(3 URLs)".
- Save location shows full absolute path.
- Right-click history row → "Open containing folder" (disabled if path unknown).
- Update yt-dlp button — runs `pip install -U yt-dlp` in background thread, reports result.

### 2026-04-13 — Cookies from browser
- Added `cookies_from_browser` dropdown (None / Chrome / Firefox / Edge / Brave / Safari / Chromium).
- Persisted to config.json; passed to yt-dlp as `cookiesfrombrowser` tuple when not "None".
- Unlocks age-restricted and login-gated content without exposing passwords.

### 2026-04-13 — Environment banners
- Refactored ffmpeg banner into a stacking banner container (only shown if warnings exist).
- Added JS runtime banner (blue) — warns if neither Deno nor Node.js is in PATH.
- Both banners include the fix command inline (`winget install ...`).
- `_check_ffmpeg` replaced by `_check_environment` covering both checks.

### 2026-04-13 — Remote JS solver
- Added "Remote JS solver" checkbox to sidebar.
- When enabled, passes `--remote-components ejs:github` to yt-dlp via `parse_options`.
- Fixes missing YouTube formats caused by unsolved n-challenges.
- Script is downloaded from GitHub on first use and cached; subsequent runs are instant.

### 2026-04-13 — Transcript-only mode
- Added "Transcript only (.srt)" checkbox with configurable language field.
- Downloads subtitle files without the video (`skip_download: True`).
- Falls back to all available languages if the requested one isn't found.

### 2026-04-13 — Music features
- **SponsorBlock**: checkbox in "Music" sidebar section. Removes sponsors, intros, outros.
- **Embed album art**: standalone thumbnail embedding, independent of `embed_metadata`.
- **Filename template**: dropdown — Title, Artist - Title, Uploader - Title.

### 2026-04-13 — MP4 format options
- Added MP4-specific variants for Best, 1080p, and 720p formats.
- Prefers MP4 video + M4A audio streams, falls back gracefully.

### 2026-04-13 — Pre-release review & cleanup
**Bugs fixed:**
- ANSI terminal colour codes (`[0;31m` etc.) stripped from yt-dlp output before display in raw log. Added `_ANSI_RE` regex in `_QtLogger._clean()`.
- `DownloadError` exceptions now logged to raw log (previously swallowed silently — user saw "Failed" with no explanation).
- `os.startfile` replaced with cross-platform folder opener (Windows/macOS/Linux).
- Update button text restored with `↻` icon after update completes (was losing it).
- `embed_metadata` default changed from `True` to `False` — avoids confusion on fresh installs without ffmpeg.
- Treeview `tag_configure` moved from `add_entry` (called per row) to `_build_tree` (called once).
- Thumbnail files cleaned up after embedding — added `FFmpegThumbnailsConvertor` postprocessor to convert and avoid leftover `.webp` files.
- `yt_dlp.parse_options` made more robust — uses `result[-1]` instead of fragile 4-tuple destructure; failures now logged instead of silently swallowed.
- `import yt_dlp.utils` moved to top of file from inside conditional block.
- Removed unused `import os` from `config.py`.

**Features added:**
- Download speed + ETA shown in status label during active downloads.
- Window title updates to `QueueTube — Downloading 2 of 5…` during active downloads; resets on completion.
- ffmpeg-dependent checkboxes (Embed subtitles, Embed metadata, SponsorBlock, Embed album art) are greyed out and disabled when ffmpeg is not installed.
- URL validation — rejects non-HTTP(S) strings with a clear status message.
- Automatic URL deduplication — duplicate URLs in the queue are silently removed, order preserved.

**Documentation:**
- README fully rewritten with all current features, project structure, Deno/ffmpeg install instructions, and cross-platform notes.

### 2026-07-20 — Bug-fix round
**Bugs fixed:**
- Transcript mode downloaded **every** language: `subtitleslangs: [lang, "all"]`
  is a union in yt-dlp, not a fallback chain. Now requests only the chosen
  language (or `all` if explicitly chosen); a missing language is an honest
  failure instead of a silent fallback.
- Playlists produced one garbled history row (last title, summed sizes). Now
  one row per video keyed by video id; `ignoreerrors` enabled in playlist mode
  so a broken video no longer aborts the rest (summary row when items skipped).
- Invalid or reversed time ranges, and time-slicing without ffmpeg, silently
  downloaded the full video. Download now refuses to start with a status message.
- `config.json` containing valid-but-non-object JSON crashed the app at launch.
- Update button claimed success while the old yt-dlp stayed loaded — now says
  a restart is needed.

### 2026-07-20 — Stop, thumbnails, sidebar redesign
- **Mid-download Stop**: raises `DownloadCancelled` from the progress hook —
  measured ~0.4s from click to full stop; partial `.part` files resume on
  retry. Interrupted video shows "■ Stopped" (amber) in history; completed
  playlist entries keep their success rows.
- **Save thumbnail file** checkbox (off by default) — thumbnails are no longer
  written on every download. Embedding fetches its own and keeps the file only
  if the checkbox is on (`already_have_thumbnail`).
- Subtitle language field now applies to embedded subtitles too (was
  hardcoded `en`).
- Sidebar reorganized into Format / Output / Subtitles / Music / Advanced
  sections; URL placeholder, red active Stop, percent readout, zebra history.

### 2026-07-20 — Final-file tracking, honest transcripts, playlist progress
- History records the **final** output path via the `MoveFiles` postprocessor
  hook (probed empirically) — post-merge/conversion path and real on-disk
  size, plus right-click → **Open file**.
- Transcript-only reports Failed with a log warning when no subtitles matched;
  successes show real title, `.srt` path and size.
- Status line shows per-item playlist progress ("playlist video 7 of 40").
- GUI polish: "Queue" header, optional time fields without fake `0:00`,
  left-aligned history headers (flat, no 3D bevel), Title column stretches,
  empty-state hint, save path middle-elided (Tk can't wrap at ZWSP).
- CLAUDE.md corrected: real design goals documented (lightweight, no server);
  CustomTkinter noted as current choice, not a mandate.

## Key Decisions
- Sequential downloads in one background thread (not one thread per URL) — keeps UI responsive, clean stop between URLs
- Progress fed via `threading.Queue` — UI thread never blocked by downloader
- Raw log uses a custom yt-dlp logger class with ANSI stripping — no subprocess stdout capture
- History is in-memory only — resets on relaunch by design
- config.json written on every settings change — no explicit save button needed
- Remote JS solver opt-in by default — yt-dlp intentionally doesn't auto-download remote code
- `has_ffmpeg` checked once at startup and stored — avoids repeated `shutil.which` calls during builds
- `embed_metadata` defaults to False — prevents silent no-op on machines without ffmpeg
- Stop cancels via `DownloadCancelled` raised from the progress hook — safe, no mid-file kill, partial files resumable
- History rows keyed by video id; final path/size from the `MoveFiles` postprocessor hook — the one hook that carries the definitive output path
- Design goal clarified (2026-07-20): lightweight GUI for a CLI tool with **no server process**; CustomTkinter is the current choice, not a mandate — see CLAUDE.md Design Goals

## Known Limitations
- No packaging — run directly via `run.bat` or `python main.py`
- History does not persist between sessions
- Time-slicing cuts at the nearest keyframe — cut points may be off by a few seconds
- See BACKLOG.md for future ideas
