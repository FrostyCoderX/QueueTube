# QueueTube — Backlog

Ideas and improvements deferred from V1. Roughly ordered by impact vs. effort.

---

## Planned Next

**Settings-window split** *(agreed 2026-07-20)*
The sidebar carries too much: cookies, remote JS solver, custom args, updater,
and filename template are set-once configuration, not per-download options.
Move them into a ⚙ Settings dialog (`CTkToplevel`); the sidebar keeps only what
you touch while queueing. Removes sidebar scrolling and shrinks the
CTkScrollableFrame widget count, which also helps window-resize sluggishness.

**Clipboard watcher (opt-in)**
A checkbox that auto-adds any URL copied to the clipboard to the queue while
the app is open. Must be opt-in — it means polling the clipboard.

**Release housekeeping**
- Pin `customtkinter>=5.2` floor in requirements.txt (yt-dlp stays unpinned on purpose)
- Rename `_QtLogger` in downloader.py — there is no Qt anywhere
- Bind `<Button-2>` alongside `<Button-3>` in history.py for macOS right-click
- Consider tagging v1.0 on GitHub

---

## Small / High Impact

**System notification on queue completion**
Fire a Windows toast notification when all downloads finish, so you know it's done
if you walked away. Can use `plyer` or the built-in `winsound` for a simple beep.

---

## Medium Effort

**Drag and drop URLs**
Allow dragging a link from a browser directly onto the URL box.
Requires `tkinterdnd2` as an additional dependency.

**URL validation / preview**
Before starting a download, call `yt-dlp --dump-json` on each URL to fetch title
and duration. Show a preview list so the user knows what they're about to download.
Also catches bad URLs early with a friendly error rather than a failed history entry.

---

## Larger Scope

**UI layer upgrade** *(considered 2026-07-20, parked)*
CustomTkinter's known costs: software-rendered resize (sluggish vs native apps)
and no native tooltips/accordions. If the ceiling ever chafes, first choice is
**pywebview** — HTML/CSS/JS view with an in-process Python bridge. It satisfies
the no-server design goal (see CLAUDE.md), keeps `downloader.py` untouched, and
stays `python main.py`. Further options: Tauri or C#/WinUI (Windows-only).
Electron rejected as too heavy. Not urgent — CTk works fine for the current scope.

**Queue management**
Let users see, reorder, and remove individual URLs from the queue before starting.
Currently it's just a text box — a proper list widget with up/down/remove controls
would be more powerful.

**History persistence (opt-in)**
Optionally save the download history to a local JSON file so it survives restarts.
Should be off by default — in-memory is simpler and private.

**Per-download format override**
Currently all URLs in a batch use the same format. Would be useful to right-click
a URL in the queue and set a different format for that one item.

**Thumbnail preview**
Show the video thumbnail in the history row (or a tooltip) after a successful download.

**Browser extension / bookmarklet**
A one-click "Send to QueueTube" from the browser. Requires a local HTTP listener —
⚠ this conflicts with the no-server design goal (see CLAUDE.md), so it would need
an explicit decision to relax that constraint. The clipboard watcher above gets
80% of the value with none of the conflict.

---

## Shipped

Implemented since the original backlog was written (see CONTEXT.md for details):

- Download speed + ETA in status label *(2026-04)*
- Grey out ffmpeg-dependent options when ffmpeg is missing *(2026-04)*
- Window title progress *(2026-04)*
- Subtitle language selection — single configurable language shared by
  embedding and transcript mode *(2026-07)*
- Mid-download Stop with resumable partial files *(2026-07)*
- Per-video playlist history rows and per-item playlist progress *(2026-07)*
- Final-file tracking: history shows the real post-conversion path and size,
  right-click → Open file *(2026-07)*
