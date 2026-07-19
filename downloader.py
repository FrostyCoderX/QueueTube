import re
import shlex
import shutil
import threading
import queue
from pathlib import Path

import yt_dlp
import yt_dlp.utils as ydl_utils

from config import FORMAT_MAP, FILENAME_TEMPLATES

# Strip ANSI terminal colour codes from yt-dlp output
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class _QtLogger:
    """Redirects yt-dlp log output to the raw log queue."""

    def __init__(self, log_queue: queue.Queue):
        self._q = log_queue

    def _clean(self, msg: str) -> str:
        return _ANSI_RE.sub("", msg)

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug]"):
            return
        self._q.put(("log", self._clean(msg)))

    def info(self, msg: str) -> None:
        self._q.put(("log", self._clean(msg)))

    def warning(self, msg: str) -> None:
        self._q.put(("log", f"[WARNING] {self._clean(msg)}"))

    def error(self, msg: str) -> None:
        self._q.put(("log", f"[ERROR] {self._clean(msg)}"))


class Downloader:
    """
    Manages a single background thread that downloads URLs sequentially.
    Communicates with the UI via a queue of event tuples:

        ("progress", float)          — 0.0–1.0
        ("status",   str)            — status label text
        ("log",      str)            — raw log line
        ("history",  dict)           — completed item metadata
        ("done",)                    — all URLs finished
    """

    def __init__(self):
        self.event_queue: queue.Queue = queue.Queue()
        self._stop_flag = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, urls: list[str], config: dict, start_time: str, end_time: str) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(urls, config, start_time, end_time),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_flag.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self, urls: list[str], config: dict, start_time: str, end_time: str) -> None:
        total = len(urls)
        for idx, url in enumerate(urls, start=1):
            if self._stop_flag.is_set():
                break

            self.event_queue.put(("status", f"Downloading {idx} of {total}…"))
            self.event_queue.put(("progress", 0.0))

            opts = self._build_opts(config, start_time, end_time)
            fmt_string = FORMAT_MAP.get(config.get("format", "Best Available"), "")
            success = True
            # One meta dict per completed video, keyed by video id — a playlist
            # URL yields multiple entries, each getting its own history row.
            entries: dict[str, dict] = {}
            # The video currently being downloaded — on cancel, this is the one
            # entry that must not be reported as a success.
            current: dict = {"vid": None, "title": None}

            def progress_hook(d: dict) -> None:
                if d["status"] == "downloading":
                    if self._stop_flag.is_set():
                        raise ydl_utils.DownloadCancelled("Stopped by user")
                    info = d.get("info_dict", {})
                    current["vid"] = info.get("id")
                    current["title"] = info.get("title") or current["title"]
                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes", 0)
                    if total_bytes:
                        self.event_queue.put(("progress", downloaded / total_bytes))
                    speed = d.get("speed")
                    eta = d.get("eta")
                    parts = []
                    if speed:
                        parts.append(f"{_fmt_size(speed)}/s")
                    if eta is not None:
                        parts.append(f"ETA {_fmt_eta(eta)}")
                    if parts:
                        self.event_queue.put(
                            ("status", f"Downloading {idx} of {total}… {' — '.join(parts)}")
                        )
                elif d["status"] == "finished":
                    self.event_queue.put(("progress", 1.0))
                    info = d.get("info_dict", {})
                    vid = info.get("id") or url
                    meta = entries.setdefault(vid, {
                        "url": url, "title": url, "size": "—",
                        "resolution": "—", "path": "", "_bytes": 0,
                    })
                    meta["title"] = info.get("title", url)
                    # Only update resolution from a stream that has video height;
                    # audio-only streams fire "finished" too and would overwrite it.
                    if info.get("height"):
                        meta["resolution"] = f"{info.get('width', '?')}×{info['height']}"
                    elif meta["resolution"] == "—":
                        # Audio-only: show the requested target codec (MP3/OPUS),
                        # not the source stream codec (which YouTube serves as opus
                        # internally regardless of what we asked for).
                        if fmt_string and fmt_string.startswith("audio:"):
                            meta["resolution"] = fmt_string.split(":")[1].upper()
                        else:
                            meta["resolution"] = info.get("acodec", "audio")
                    # Accumulate size across streams (video + audio downloaded separately)
                    meta["_bytes"] += info.get("filesize") or info.get("filesize_approx") or 0
                    meta["size"] = _fmt_size(meta["_bytes"])
                    meta["path"] = d.get("filename", "")

            opts["progress_hooks"] = [progress_hook]

            raised = False
            cancelled = False
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ret = ydl.download([url])
                    if ret != 0:
                        success = False
                        self.event_queue.put(("log", f"[ERROR] yt-dlp returned error code {ret}"))
            except ydl_utils.DownloadCancelled:
                success = False
                cancelled = True
                self.event_queue.put(("log", "[INFO] Download stopped by user"))
            except yt_dlp.utils.DownloadError as exc:
                success = False
                raised = True
                self.event_queue.put(("log", f"[ERROR] {_ANSI_RE.sub('', str(exc))}"))
            except Exception as exc:
                success = False
                raised = True
                self.event_queue.put(("log", f"[ERROR] Unexpected error: {exc}"))

            # Emit one history row per video. On cancel, only the video that was
            # mid-download is marked stopped — earlier entries completed fine.
            # On error, collected entries didn't survive postprocessing.
            for vid, meta in entries.items():
                meta.pop("_bytes", None)
                if cancelled and vid == current["vid"]:
                    meta["status"] = "■ Stopped"
                elif raised:
                    meta["status"] = "✗ Failed"
                else:
                    meta["status"] = "✓ Success"
                self.event_queue.put(("history", meta))

            if cancelled:
                if current["vid"] not in entries:
                    self.event_queue.put(("history", {
                        "url": url, "title": current["title"] or url, "size": "—",
                        "resolution": "—", "path": "", "status": "■ Stopped",
                    }))
            elif not entries:
                # Nothing downloaded: transcript-only mode is the one legitimate
                # case (skip_download never fires the finished hook).
                status = "✓ Success" if success and config.get("transcript_only") else "✗ Failed"
                self.event_queue.put(("history", {
                    "url": url, "title": url, "size": "—",
                    "resolution": "—", "path": "", "status": status,
                }))
            elif not success and not raised:
                # Playlist finished with some entries skipped (ignoreerrors)
                self.event_queue.put(("history", {
                    "url": url, "title": f"{url} — some items failed", "size": "—",
                    "resolution": "—", "path": "", "status": "✗ Failed",
                }))

        status_text = "Stopped." if self._stop_flag.is_set() else "All done."
        self.event_queue.put(("status", status_text))
        self.event_queue.put(("progress", 0.0))
        self.event_queue.put(("done",))

    def _build_opts(self, config: dict, start_time: str, end_time: str) -> dict:
        fmt = config.get("format", "Best Available")
        fmt_string = FORMAT_MAP.get(fmt)

        save_dir = config.get("save_location", str(Path.home() / "Downloads"))
        tmpl_key = config.get("filename_template", "Title")
        filename = FILENAME_TEMPLATES.get(tmpl_key, "%(title)s")
        if config.get("auto_subfolders"):
            outtmpl = f"%(uploader)s/{filename}.%(ext)s"
        else:
            outtmpl = f"{filename}.%(ext)s"

        has_ffmpeg = shutil.which("ffmpeg") is not None
        save_thumb = bool(config.get("save_thumbnail", False))

        opts: dict = {
            "outtmpl":          outtmpl,
            "paths":            {"home": save_dir},
            "noplaylist":       config.get("noplaylist", True),
            "logger":           _QtLogger(self.event_queue),
            "quiet":            True,
            "no_warnings":      False,
            "writethumbnail":   save_thumb,
        }

        # In playlist mode, skip broken entries instead of aborting the whole
        # playlist. download() returns nonzero so we still detect the failure.
        if not config.get("noplaylist", True):
            opts["ignoreerrors"] = True

        if fmt_string and fmt_string.startswith("audio:"):
            codec = fmt_string.split(":")[1]
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key":            "FFmpegExtractAudio",
                "preferredcodec": codec,
            }]
        else:
            opts["format"] = fmt_string or "bestvideo+bestaudio/best"

        if config.get("transcript_only"):
            lang = config.get("transcript_lang", "en").strip() or "en"
            opts["skip_download"]       = True
            opts["writesubtitles"]      = True
            opts["writeautomaticsub"]   = True
            opts["subtitleslangs"]      = ["all"] if lang == "all" else [lang]
            opts["subtitlesformat"]     = "srt"
        elif config.get("embed_subtitles") and has_ffmpeg:
            lang = config.get("transcript_lang", "en").strip() or "en"
            opts["writesubtitles"] = True
            opts["subtitleslangs"] = ["all"] if lang == "all" else [lang]
            opts["embedsubtitles"] = True

        # Thumbnail embedding — shared by "Embed metadata" and "Embed album art".
        # already_have_thumbnail keeps the thumbnail file on disk after embedding
        # when the user also wants it saved standalone.
        if (config.get("embed_metadata") or config.get("embed_thumbnail")) and has_ffmpeg:
            opts["embedthumbnail"] = True
            opts["writethumbnail"] = True
            pps = []
            if config.get("embed_metadata"):
                opts["embedmetadata"] = True
                pps.append({"key": "FFmpegMetadata"})
            pps += [
                {"key": "EmbedThumbnail", "already_have_thumbnail": save_thumb},
                {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
            ]
            opts["postprocessors"] = opts.get("postprocessors", []) + pps

        # SponsorBlock — removes sponsored segments, intros, outros
        if config.get("sponsorblock") and has_ffmpeg:
            opts["sponsorblock_remove"] = ["sponsor", "intro", "outro"]

        # Time-slicing (the UI validates before starting; None here means invalid)
        if (start_time or end_time) and has_ffmpeg:
            start_s = parse_time(start_time) if start_time else 0.0
            end_s = parse_time(end_time) if end_time else float("inf")
            if start_s is not None and end_s is not None:
                opts["download_ranges"] = ydl_utils.download_range_func(
                    None, [(start_s, end_s)]
                )
                # Disabled force_keyframes_at_cuts — it re-encodes the entire segment
                # which is extremely slow. Without it, cuts snap to the nearest keyframe
                # (off by a few seconds) but finish in seconds instead of minutes.

        # Cookies from browser
        browser = config.get("cookies_from_browser", "None")
        if browser and browser != "None":
            opts["cookiesfrombrowser"] = (browser.lower(),)

        # Remote JS challenge solver
        if config.get("remote_components"):
            try:
                self._merge_parsed_opts(opts, ["--remote-components", "ejs:github"])
            except Exception as exc:
                self.event_queue.put(("log", f"[WARNING] Could not parse --remote-components: {exc}"))

        # Custom args
        custom = config.get("custom_args", "").strip()
        if custom:
            try:
                self._merge_parsed_opts(opts, shlex.split(custom))
            except Exception as exc:
                self.event_queue.put(("log", f"[WARNING] Could not parse custom args: {exc}"))

        return opts

    @staticmethod
    def _merge_parsed_opts(opts: dict, args: list[str]) -> None:
        """Merge only non-default values from parse_options into opts.

        yt_dlp.parse_options returns a full defaults dict — blindly updating
        with it would overwrite our paths, outtmpl, etc. with empty values.
        Compare against a bare defaults parse to find what actually changed.
        """
        defaults = yt_dlp.parse_options([])[-1]
        parsed = yt_dlp.parse_options(args)[-1]
        for key, value in parsed.items():
            if value != defaults.get(key):
                opts[key] = value


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _fmt_size(n: int | float) -> str:
    if not n:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _fmt_eta(seconds: int | float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m"


def parse_time(t: str) -> float | None:
    """Convert H:MM:SS, M:SS, or SS to seconds. Returns None if invalid."""
    parts = t.strip().split(":")
    if not 1 <= len(parts) <= 3:
        return None
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if any(n < 0 for n in nums):
        return None
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60 + n
    return seconds
