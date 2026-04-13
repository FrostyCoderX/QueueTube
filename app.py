import ctypes
import shutil
import subprocess
import sys
import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

# Set Windows taskbar icon to our own instead of default Python icon
if sys.platform == "win32":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("queuetube.app")

from config import FORMAT_MAP, BROWSER_OPTIONS, FILENAME_TEMPLATES, load_config, save_config
from downloader import Downloader
from history import HistoryTable

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

POLL_INTERVAL_MS = 150

# Minimal URL validation — must look like an HTTP(S) link
_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("QueueTube")
        self.geometry("1000x700")
        self.minsize(800, 550)

        icon_path = Path(__file__).parent / "icon.ico"
        if icon_path.exists():
            self.iconbitmap(str(icon_path))

        self._config = load_config()
        self._downloader = Downloader()
        self._has_ffmpeg = shutil.which("ffmpeg") is not None

        self._build_ui()
        self._check_environment()
        self._poll()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # Banner container — only gridded if at least one warning is active
        self._banner_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._banner_frame.grid_columnconfigure(0, weight=1)

        self._ffmpeg_banner = ctk.CTkLabel(
            self._banner_frame,
            text="⚠  ffmpeg not found in PATH — time-slicing, subtitles, and metadata embedding will not work.  Run: winget install ffmpeg",
            fg_color="#5a3e00",
            text_color="#ffcc44",
            corner_radius=0,
            anchor="w",
            padx=12,
            pady=6,
        )

        self._js_banner = ctk.CTkLabel(
            self._banner_frame,
            text="⚠  No JS runtime found (Deno or Node.js) — some YouTube formats may be missing.  Run: winget install DenoLand.Deno",
            fg_color="#1e3a5a",
            text_color="#66aaff",
            corner_radius=0,
            anchor="w",
            padx=12,
            pady=6,
        )

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=0)
        main.grid_rowconfigure(0, weight=1)

        self._build_left(main)
        self._build_right(main)

    def _build_left(self, parent: ctk.CTkFrame) -> None:
        left = ctk.CTkFrame(parent, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        left.grid_columnconfigure(0, weight=1)

        # URL input header with live count
        url_header = ctk.CTkFrame(left, fg_color="transparent")
        url_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ctk.CTkLabel(url_header, text="URLs  (one per line)", anchor="w").pack(side="left")
        self._url_count_label = ctk.CTkLabel(
            url_header, text="", anchor="w", text_color="#666666"
        )
        self._url_count_label.pack(side="left", padx=(8, 0))

        self._url_box = ctk.CTkTextbox(left, height=120, wrap="none")
        self._url_box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self._url_box.bind("<KeyRelease>", lambda _: self._update_url_count())
        self._url_box.bind("<<Paste>>",    lambda _: self.after(50, self._update_url_count))

        # Time range
        time_row = ctk.CTkFrame(left, fg_color="transparent")
        time_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(time_row, text="Start").pack(side="left")
        self._start_time = ctk.CTkEntry(time_row, width=90, placeholder_text="0:00")
        self._start_time.pack(side="left", padx=(6, 12))
        self._start_time.bind("<FocusOut>", lambda _: self._format_time_field(self._start_time))
        ctk.CTkLabel(time_row, text="End").pack(side="left")
        self._end_time = ctk.CTkEntry(time_row, width=90, placeholder_text="0:00")
        self._end_time.pack(side="left", padx=(6, 6))
        self._end_time.bind("<FocusOut>", lambda _: self._format_time_field(self._end_time))
        ctk.CTkLabel(time_row, text="(M:SS or H:MM:SS)", text_color="#666666",
                     font=("Segoe UI", 10)).pack(side="left", padx=(6, 0))

        # Action buttons
        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._download_btn = ctk.CTkButton(
            btn_row, text="↓  Download Queue", command=self._start_download, width=175
        )
        self._download_btn.pack(side="left")
        self._stop_btn = ctk.CTkButton(
            btn_row,
            text="■  Stop",
            command=self._stop_download,
            width=80,
            fg_color="#555",
            hover_color="#333",
            state="disabled",
        )
        self._stop_btn.pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            btn_row,
            text="×  Clear",
            command=self._clear_urls,
            width=80,
            fg_color="#444",
            hover_color="#333",
        ).pack(side="left", padx=(8, 0))

        # Progress
        self._progress_bar = ctk.CTkProgressBar(left)
        self._progress_bar.set(0)
        self._progress_bar.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        self._status_label = ctk.CTkLabel(left, text="Ready", anchor="w", text_color="#aaaaaa")
        self._status_label.grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 8))

        # History table
        ctk.CTkLabel(left, text="History", anchor="w").grid(
            row=6, column=0, sticky="w", pady=(0, 4)
        )
        self._history = HistoryTable(left, fg_color="transparent")
        self._history.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
        left.grid_rowconfigure(7, weight=1)

        # Raw log toggle
        self._log_visible = False
        self._log_toggle_btn = ctk.CTkButton(
            left,
            text="≡  Show Logs",
            command=self._toggle_log,
            width=120,
            fg_color="#333",
            hover_color="#444",
        )
        self._log_toggle_btn.grid(row=8, column=0, sticky="w", pady=(0, 4))

        self._log_box = ctk.CTkTextbox(
            left,
            height=120,
            font=("Courier New", 11),
            fg_color="#1a1a1a",
            state="disabled",
            wrap="none",
        )

    def _build_right(self, parent: ctk.CTkFrame) -> None:
        right = ctk.CTkScrollableFrame(parent, width=200)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.grid_columnconfigure(0, weight=1)

        row = 0

        def label(text: str, pady_top: int = 8) -> None:
            nonlocal row
            ctk.CTkLabel(right, text=text, anchor="w", text_color="#aaaaaa").grid(
                row=row, column=0, sticky="w", padx=12, pady=(pady_top, 2)
            )
            row += 1

        def next_row() -> int:
            nonlocal row
            r = row
            row += 1
            return r

        # Track checkboxes that need ffmpeg so we can disable them
        self._ffmpeg_checkboxes: list[ctk.CTkCheckBox] = []

        # Generic checkbox helper
        def checkbox(text: str, key: str, needs_ffmpeg: bool = False) -> None:
            nonlocal row
            var = ctk.BooleanVar(value=self._config[key])
            state = "normal" if (not needs_ffmpeg or self._has_ffmpeg) else "disabled"
            cb = ctk.CTkCheckBox(
                right,
                text=text,
                variable=var,
                command=lambda: self._save_setting(key, var.get()),
                state=state,
            )
            cb.grid(row=next_row(), column=0, sticky="w", padx=12, pady=4)
            setattr(self, f"_var_{key}", var)
            if needs_ffmpeg:
                self._ffmpeg_checkboxes.append(cb)

        # Format
        label("Format", pady_top=12)
        self._format_var = ctk.StringVar(value=self._config["format"])
        ctk.CTkOptionMenu(
            right,
            values=list(FORMAT_MAP.keys()),
            variable=self._format_var,
            command=lambda _: self._save_setting("format", self._format_var.get()),
        ).grid(row=next_row(), column=0, sticky="ew", padx=12, pady=(0, 4))

        # "Download playlists" is the inverse of yt-dlp's "noplaylist"
        self._var_playlist = ctk.BooleanVar(value=not self._config["noplaylist"])
        ctk.CTkCheckBox(
            right,
            text="Download playlists",
            variable=self._var_playlist,
            command=lambda: self._save_setting("noplaylist", not self._var_playlist.get()),
        ).grid(row=next_row(), column=0, sticky="w", padx=12, pady=4)

        checkbox("Auto-subfolders",         "auto_subfolders")
        checkbox("Embed subtitles",         "embed_subtitles",  needs_ffmpeg=True)
        checkbox("Embed metadata + thumb",  "embed_metadata",   needs_ffmpeg=True)

        # Transcript
        self._var_transcript_only = ctk.BooleanVar(
            value=self._config.get("transcript_only", False)
        )
        ctk.CTkCheckBox(
            right,
            text="Transcript only (.srt)",
            variable=self._var_transcript_only,
            command=lambda: self._save_setting("transcript_only", self._var_transcript_only.get()),
        ).grid(row=next_row(), column=0, sticky="w", padx=12, pady=(4, 2))

        lang_row = ctk.CTkFrame(right, fg_color="transparent")
        lang_row.grid(row=next_row(), column=0, sticky="ew", padx=12, pady=(0, 4))
        ctk.CTkLabel(lang_row, text="Lang:", text_color="#aaaaaa", width=36, anchor="w").pack(side="left")
        self._transcript_lang = ctk.CTkEntry(lang_row, width=60, placeholder_text="en")
        self._transcript_lang.insert(0, self._config.get("transcript_lang", "en"))
        self._transcript_lang.pack(side="left", padx=(4, 0))
        self._transcript_lang.bind(
            "<FocusOut>",
            lambda _: self._save_setting(
                "transcript_lang", self._transcript_lang.get().strip() or "en"
            ),
        )
        ctk.CTkLabel(
            right,
            text='Use "all" to get any\navailable language.',
            anchor="w",
            text_color="#666666",
            font=("Segoe UI", 10),
            justify="left",
        ).grid(row=next_row(), column=0, sticky="w", padx=12, pady=(0, 4))

        # Music
        ctk.CTkFrame(right, height=1, fg_color="#444").grid(
            row=next_row(), column=0, sticky="ew", padx=12, pady=(4, 6)
        )
        label("Music", pady_top=0)

        checkbox("Skip sponsor segments", "sponsorblock", needs_ffmpeg=True)
        ctk.CTkLabel(
            right,
            text="Cuts sponsors, intros & outros.\nRequires ffmpeg.",
            anchor="w",
            text_color="#666666",
            font=("Segoe UI", 10),
            justify="left",
        ).grid(row=next_row(), column=0, sticky="w", padx=12, pady=(0, 4))

        checkbox("Embed album art", "embed_thumbnail", needs_ffmpeg=True)
        ctk.CTkLabel(
            right,
            text="Embeds thumbnail as cover art.\nRequires ffmpeg.",
            anchor="w",
            text_color="#666666",
            font=("Segoe UI", 10),
            justify="left",
        ).grid(row=next_row(), column=0, sticky="w", padx=12, pady=(0, 4))

        label("Filename template")
        self._filename_template_var = ctk.StringVar(
            value=self._config.get("filename_template", "Title")
        )
        ctk.CTkOptionMenu(
            right,
            values=list(FILENAME_TEMPLATES.keys()),
            variable=self._filename_template_var,
            command=lambda _: self._save_setting(
                "filename_template", self._filename_template_var.get()
            ),
        ).grid(row=next_row(), column=0, sticky="ew", padx=12, pady=(0, 8))

        # Save location
        ctk.CTkFrame(right, height=1, fg_color="#444").grid(
            row=next_row(), column=0, sticky="ew", padx=12, pady=(4, 6)
        )
        label("Save location", pady_top=0)
        self._save_loc_label = ctk.CTkLabel(
            right,
            text=self._config["save_location"],
            anchor="w",
            text_color="#dddddd",
            wraplength=180,
        )
        self._save_loc_label.grid(row=next_row(), column=0, sticky="w", padx=12)
        ctk.CTkButton(
            right,
            text="↗  Browse…",
            command=self._pick_folder,
            width=110,
        ).grid(row=next_row(), column=0, sticky="w", padx=12, pady=(4, 8))

        # Custom args
        label("Custom yt-dlp args")
        self._custom_args = ctk.CTkEntry(right, placeholder_text="e.g. --no-mtime")
        self._custom_args.insert(0, self._config.get("custom_args", ""))
        self._custom_args.grid(row=next_row(), column=0, sticky="ew", padx=12, pady=(0, 16))
        self._custom_args.bind(
            "<FocusOut>",
            lambda _: self._save_setting("custom_args", self._custom_args.get()),
        )

        # Cookies from browser
        label("Cookies from browser")
        self._cookies_var = ctk.StringVar(value=self._config.get("cookies_from_browser", "None"))
        ctk.CTkOptionMenu(
            right,
            values=BROWSER_OPTIONS,
            variable=self._cookies_var,
            command=lambda _: self._save_setting("cookies_from_browser", self._cookies_var.get()),
        ).grid(row=next_row(), column=0, sticky="ew", padx=12, pady=(0, 4))
        ctk.CTkLabel(
            right,
            text="For age-restricted or login-\ngated content. Log in via\nyour browser first.",
            anchor="w",
            text_color="#666666",
            font=("Segoe UI", 10),
            justify="left",
        ).grid(row=next_row(), column=0, sticky="w", padx=12, pady=(0, 8))

        # Remote JS solver
        self._var_remote_components = ctk.BooleanVar(
            value=self._config.get("remote_components", False)
        )
        ctk.CTkCheckBox(
            right,
            text="Remote JS solver",
            variable=self._var_remote_components,
            command=lambda: self._save_setting(
                "remote_components", self._var_remote_components.get()
            ),
        ).grid(row=next_row(), column=0, sticky="w", padx=12, pady=(0, 2))
        ctk.CTkLabel(
            right,
            text="Fixes missing YouTube formats.\nDownloads solver script from\nGitHub on first use.",
            anchor="w",
            text_color="#666666",
            font=("Segoe UI", 10),
            justify="left",
        ).grid(row=next_row(), column=0, sticky="w", padx=12, pady=(0, 8))

        # Separator
        ctk.CTkFrame(right, height=1, fg_color="#444").grid(
            row=next_row(), column=0, sticky="ew", padx=12, pady=(0, 8)
        )

        # Update yt-dlp
        label("Updater", pady_top=0)
        self._update_btn = ctk.CTkButton(
            right,
            text="↻  Update yt-dlp",
            command=self._update_ytdlp,
            width=150,
        )
        self._update_btn.grid(row=next_row(), column=0, sticky="w", padx=12, pady=(0, 4))
        self._update_status_label = ctk.CTkLabel(
            right, text="", anchor="w", text_color="#aaaaaa", font=("Segoe UI", 11)
        )
        self._update_status_label.grid(row=next_row(), column=0, sticky="w", padx=12)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _start_download(self) -> None:
        urls = self._get_urls()
        if not urls:
            self._status_label.configure(text="No URLs entered.")
            return

        # Validate URLs
        invalid = [u for u in urls if not _URL_RE.match(u)]
        if invalid:
            self._status_label.configure(text=f"Invalid URL: {invalid[0][:60]}")
            return

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        urls = unique

        self._download_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._history.clear()
        self._clear_log()

        self._downloader.start(
            urls=urls,
            config=self._build_download_config(),
            start_time=self._start_time.get().strip(),
            end_time=self._end_time.get().strip(),
        )

    def _stop_download(self) -> None:
        self._downloader.stop()
        self._stop_btn.configure(state="disabled")

    def _clear_urls(self) -> None:
        self._url_box.delete("1.0", "end")
        self._update_url_count()

    def _build_download_config(self) -> dict:
        return dict(self._config)

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(
            initialdir=self._config.get("save_location", str(Path.home() / "Downloads"))
        )
        if folder:
            self._save_setting("save_location", folder)
            self._save_loc_label.configure(text=folder)

    def _toggle_log(self) -> None:
        if self._log_visible:
            self._log_box.grid_forget()
            self._log_toggle_btn.configure(text="≡  Show Logs")
        else:
            self._log_box.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 8))
            self._log_toggle_btn.configure(text="≡  Hide Logs")
        self._log_visible = not self._log_visible

    def _append_log(self, text: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", text + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _update_url_count(self) -> None:
        urls = self._get_urls()
        if urls:
            self._url_count_label.configure(text=f"({len(urls)} URL{'s' if len(urls) != 1 else ''})")
        else:
            self._url_count_label.configure(text="")

    def _update_ytdlp(self) -> None:
        self._update_btn.configure(state="disabled", text="Updating…")
        self._update_status_label.configure(text="")
        threading.Thread(target=self._run_ytdlp_update, daemon=True).start()

    def _run_ytdlp_update(self) -> None:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                if "already satisfied" in result.stdout.lower():
                    msg = "Already up to date."
                else:
                    msg = "Updated successfully!"
            else:
                msg = "Update failed — check logs."
                self.after(0, lambda: self._append_log(result.stderr))
        except Exception as exc:
            msg = "Update failed."
            self.after(0, lambda: self._append_log(f"[ERROR] {exc}"))

        self.after(0, lambda: self._update_btn.configure(state="normal", text="↻  Update yt-dlp"))
        self.after(0, lambda: self._update_status_label.configure(text=msg))

    # ------------------------------------------------------------------
    # Event queue polling
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        q = self._downloader.event_queue
        try:
            while True:
                event = q.get_nowait()
                kind = event[0]
                if kind == "progress":
                    self._progress_bar.set(event[1])
                elif kind == "status":
                    self._status_label.configure(text=event[1])
                    # Update window title during downloads
                    if event[1].startswith("Downloading"):
                        self.title(f"QueueTube — {event[1]}")
                    elif event[1] in ("All done.", "Stopped.", "Ready"):
                        self.title("QueueTube")
                elif kind == "log":
                    self._append_log(event[1])
                elif kind == "history":
                    self._history.add_entry(event[1])
                elif kind == "done":
                    self._download_btn.configure(state="normal")
                    self._stop_btn.configure(state="disabled")
                    self._progress_bar.set(0)
                    self.title("QueueTube")
        except queue.Empty:
            pass
        self.after(POLL_INTERVAL_MS, self._poll)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_time_field(entry: ctk.CTkEntry) -> None:
        """Auto-format a time entry: '130' → '1:30', '90' → '1:30', '3661' → '1:01:01'."""
        raw = entry.get().strip()
        if not raw:
            return
        # Already has colons — leave it alone
        if ":" in raw:
            return
        try:
            total = int(raw)
        except ValueError:
            return
        if total < 60:
            formatted = f"0:{total:02d}"
        elif total < 3600:
            formatted = f"{total // 60}:{total % 60:02d}"
        else:
            h = total // 3600
            m = (total % 3600) // 60
            s = total % 60
            formatted = f"{h}:{m:02d}:{s:02d}"
        entry.delete(0, "end")
        entry.insert(0, formatted)

    def _get_urls(self) -> list[str]:
        raw = self._url_box.get("1.0", "end")
        return [u.strip() for u in raw.splitlines() if u.strip()]

    def _save_setting(self, key: str, value) -> None:
        self._config[key] = value
        save_config(self._config)

    def _check_environment(self) -> None:
        warnings = []
        if not self._has_ffmpeg:
            warnings.append(self._ffmpeg_banner)
        has_js = shutil.which("deno") or shutil.which("node") or shutil.which("nodejs")
        if not has_js:
            warnings.append(self._js_banner)
        if warnings:
            self._banner_frame.grid(row=0, column=0, sticky="ew")
            for w in warnings:
                w.pack(fill="x")
