import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "config.json"

DEFAULTS: dict = {
    "format": "Best Available",
    "noplaylist": True,
    "auto_subfolders": False,
    "embed_subtitles": False,
    "embed_metadata": False,
    "save_location": str(Path.home() / "Downloads"),
    "custom_args": "",
    "cookies_from_browser": "None",
    "remote_components": False,
    "transcript_only": False,
    "transcript_lang": "en",
    "sponsorblock": False,
    "embed_thumbnail": False,
    "filename_template": "Title",
}

FILENAME_TEMPLATES: dict[str, str] = {
    "Title":            "%(title)s",
    "Artist - Title":   "%(artist,uploader)s - %(title)s",
    "Uploader - Title": "%(uploader)s - %(title)s",
}

BROWSER_OPTIONS = ["None", "Chrome", "Firefox", "Edge", "Brave", "Safari", "Chromium"]

FORMAT_MAP: dict[str, str | None] = {
    "Best Available":       "bestvideo+bestaudio/best",
    "Best (MP4)":           "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "1080p Limit":          "bestvideo[height<=1080]+bestaudio/best",
    "1080p Limit (MP4)":    "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
    "720p Limit":           "bestvideo[height<=720]+bestaudio/best",
    "720p Limit (MP4)":     "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
    "Audio Only (MP3)":     "audio:mp3",
    "Audio Only (Opus)":    "audio:opus",
}


def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, value in DEFAULTS.items():
            data.setdefault(key, value)
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULTS)


def save_config(config: dict) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError:
        pass
