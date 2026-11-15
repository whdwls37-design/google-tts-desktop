"""A job is one video in several languages:

    jobs/<slug>/
      ko/  video.mp4  script.txt  [meta.json] [thumbnail.jpg] [*.srt]
      en/  ...
      ja/  ...

Each language folder name must match a channel key in channels.json.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .config import ChannelConfig

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi")
THUMB_NAMES = ("thumbnail.jpg", "thumbnail.jpeg", "thumbnail.png")
SCRIPT_NAMES = ("script.txt", "script.md")
CAPTION_EXTS = (".srt", ".vtt", ".sbv")

META_FILE = "meta.json"
RESULT_FILE = "upload_result.json"

TITLE_MAX = 100
DESCRIPTION_MAX_BYTES = 5000
TAGS_MAX_CHARS = 500
PRIVACY_VALUES = ("private", "unlisted", "public")


@dataclass
class Meta:
    title: str
    description: str
    tags: List[str] = field(default_factory=list)
    category_id: Optional[str] = None
    privacy: Optional[str] = None
    publish_at: Optional[str] = None  # ISO 8601 with timezone, e.g. 2026-11-20T18:00:00+09:00
    made_for_kids: Optional[bool] = None
    contains_synthetic_media: Optional[bool] = None

    @classmethod
    def from_file(cls, path: Path) -> "Meta":
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        if "title" not in known or "description" not in known:
            raise ValueError(f"{path}: 'title' and 'description' are required")
        return cls(**known)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class LangItem:
    key: str
    folder: Path
    video: Optional[Path]
    script: Optional[Path]
    thumbnail: Optional[Path]
    captions: List[Path]

    @property
    def meta_path(self) -> Path:
        return self.folder / META_FILE

    @property
    def result_path(self) -> Path:
        return self.folder / RESULT_FILE

    def read_script(self) -> str:
        return self.script.read_text(encoding="utf-8") if self.script else ""


def _find_video(folder: Path) -> Optional[Path]:
    videos = sorted(p for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXTS)
    if len(videos) > 1:
        names = ", ".join(v.name for v in videos)
        raise ValueError(f"{folder}: more than one video file ({names}); keep exactly one")
    return videos[0] if videos else None


def _first(folder: Path, names) -> Optional[Path]:
    for n in names:
        if (folder / n).exists():
            return folder / n
    return None


def scan_job(job_dir: Path) -> List[LangItem]:
    if not job_dir.is_dir():
        raise FileNotFoundError(f"Job folder not found: {job_dir}")
    items = []
    for sub in sorted(p for p in job_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        items.append(
            LangItem(
                key=sub.name,
                folder=sub,
                video=_find_video(sub),
                script=_first(sub, SCRIPT_NAMES),
                thumbnail=_first(sub, THUMB_NAMES),
                captions=sorted(p for p in sub.iterdir() if p.suffix.lower() in CAPTION_EXTS),
            )
        )
    return items


def sanitize_text(text: str) -> str:
    # YouTube rejects '<' and '>' in titles and descriptions.
    return text.replace("<", "‹").replace(">", "›")


def truncate_bytes(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip()


def fit_tags(tags: List[str]) -> List[str]:
    """Keep tags in order until YouTube's ~500-character total is reached."""
    out, total = [], 0
    for t in (t.strip().replace("<", "").replace(">", "") for t in tags):
        if not t:
            continue
        cost = len(t) + (2 if " " in t else 0) + (1 if out else 0)  # quotes for spaces, comma
        if total + cost > TAGS_MAX_CHARS:
            break
        out.append(t)
        total += cost
    return out


def fallback_meta(script: str) -> Meta:
    """No AI: first non-empty line = title, the script itself = description."""
    lines = [ln.strip() for ln in script.splitlines()]
    title = next((ln.lstrip("#").strip() for ln in lines if ln), "Untitled")
    return Meta(title=title, description=script.strip())


def _check_publish_at(value: str) -> str:
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"publish_at {value!r} is not ISO 8601 (e.g. 2026-11-20T18:00:00+09:00)")
    if when.tzinfo is None:
        raise ValueError(f"publish_at {value!r} needs a timezone, e.g. +09:00")
    if when <= datetime.now(timezone.utc):
        raise ValueError(f"publish_at {value!r} is in the past")
    return when.isoformat()


def finalize(meta: Meta, channel: ChannelConfig) -> dict:
    """Merge job meta with channel defaults and apply YouTube limits.
    Returns the request body for videos.insert."""
    description = meta.description.strip()
    if channel.description_footer:
        description = f"{description}\n\n{channel.description_footer.strip()}"

    privacy = meta.privacy or channel.privacy
    if privacy not in PRIVACY_VALUES:
        raise ValueError(f"privacy must be one of {PRIVACY_VALUES}, got {privacy!r}")

    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": (
            meta.made_for_kids if meta.made_for_kids is not None else channel.made_for_kids
        ),
    }
    if meta.publish_at:
        # Scheduled publishing only works on private videos.
        status["privacyStatus"] = "private"
        status["publishAt"] = _check_publish_at(meta.publish_at)
    synthetic = (
        meta.contains_synthetic_media
        if meta.contains_synthetic_media is not None
        else channel.contains_synthetic_media
    )
    if synthetic is not None:
        status["containsSyntheticMedia"] = bool(synthetic)

    return {
        "snippet": {
            "title": sanitize_text(meta.title.strip())[:TITLE_MAX],
            "description": truncate_bytes(sanitize_text(description), DESCRIPTION_MAX_BYTES),
            "tags": fit_tags(list(meta.tags) + list(channel.tags)),
            "categoryId": meta.category_id or channel.category_id,
            "defaultLanguage": channel.language,
            "defaultAudioLanguage": channel.language,
        },
        "status": status,
    }
