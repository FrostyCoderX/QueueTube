# QueueTube — Backlog

Ideas and improvements deferred from V1. Roughly ordered by impact vs. effort.

---

## Small / High Impact

**Download speed + ETA in status label**
yt-dlp reports `speed` and `eta` in the progress hook — we currently discard them.
Show e.g. `Downloading 2 of 5… 3.2 MB/s — 14s remaining` in the status label.

**Grey out ffmpeg-dependent options when ffmpeg is missing**
"Embed metadata + thumb", "Embed subtitles", and time-slicing fields should be
visually disabled (greyed out) when ffmpeg is not in PATH, instead of silently
doing nothing.

**Window title progress**
Update the title bar to `QueueTube — Downloading 2 of 5` during active downloads.
Free and useful for users who minimise the window.

**System notification on queue completion**
Fire a Windows toast notification when all downloads finish, so you know it's done
if you walked away. Can use `plyer` or the built-in `winsound` for a simple beep.

---

## Medium Effort

**Subtitle language selection**
Currently hardcoded to English (`subtitleslangs: ['en']`).
Add a text field or multi-select so users can specify languages (e.g. `en,fr,de`).

**Drag and drop URLs**
Allow dragging a link from a browser directly onto the URL box.
Requires `tkinterdnd2` as an additional dependency.

**URL validation / preview**
Before starting a download, call `yt-dlp --dump-json` on each URL to fetch title
and duration. Show a preview list so the user knows what they're about to download.
Also catches bad URLs early with a friendly error rather than a failed history entry.

---

## Larger Scope

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
A one-click "Send to QueueTube" from the browser. Requires a local HTTP listener
(small Flask/http.server endpoint). Big scope but a slick UX improvement.
