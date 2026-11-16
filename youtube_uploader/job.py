"""A job is one video in several languages:

    jobs/<slug>/
      ko/  video.mp4  info.txt  [thumbnail.jpg] [*.srt]
           (or script.txt + meta.json made by `prepare`)
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
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
SCRIPT_NAMES = ("script.txt", "script.md")
CAPTION_EXTS = (".srt", ".vtt", ".sbv")

META_FILE = "meta.json"
INFO_FILE = "info.txt"
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
        data = json.loads(path.read_text(encoding="utf-8-sig"))
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

    @property
    def info_path(self) -> Path:
        return self.folder / INFO_FILE

    def read_script(self) -> str:
        return read_text_any(self.script) if self.script else ""


def read_text_any(path: Path) -> str:
    """Notepad may save UTF-8 (with/without BOM), UTF-16, or Korean ANSI (CP949)."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp949", errors="replace")


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


def _find_thumbnail(folder: Path) -> Optional[Path]:
    """thumbnail.jpg/png, else the only image file in the folder (any name)."""
    exact = _first(folder, THUMB_NAMES)
    if exact:
        return exact
    images = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS
                    and not p.name.endswith(".upload.jpg"))  # our own shrunk copy
    named = [p for p in images if p.stem.lower().startswith(("thumb", "썸네일"))]
    if named:
        return named[0]
    return images[0] if len(images) == 1 else None


def _find_script(folder: Path) -> Optional[Path]:
    """script.txt / script.md, else 'script.txt.txt' (Windows hidden extension),
    else the only .txt/.md file in the folder."""
    exact = _first(folder, SCRIPT_NAMES)
    if exact:
        return exact
    texts = sorted(p for p in folder.iterdir()
                   if p.is_file() and p.suffix.lower() in (".txt", ".md")
                   and not p.name.lower().startswith("info"))
    named = [p for p in texts if p.name.lower().startswith("script")]
    if named:
        return named[0]
    return texts[0] if len(texts) == 1 else None


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
                script=_find_script(sub),
                thumbnail=_find_thumbnail(sub),
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


# ---------------------------------------------------------------- info.txt

INFO_TEMPLATE = """# 이 파일에 제목, 예약 시간, 설명을 적고 저장하세요. ('#'으로 시작하는 줄은 무시됩니다)
# 예약: 비워 두면 예약 없이 올라갑니다. 형식 2026-11-20 18:00 (이 컴퓨터 시간 기준)
#       다른 시간대로 쓰려면 끝에 +09:00 처럼 붙이세요. 예) 2026-11-20 18:00 -05:00
# 태그: 쉼표로 구분 (선택)
# 공개: 비공개 / 일부공개 / 공개 (선택, 예약을 쓰면 무시됨)
# 설명: 은 맨 마지막에 두고, 그 아래 줄부터 끝까지가 설명입니다.

제목:
예약:
태그:
설명:
"""

_KEYS = {
    "제목": "title", "title": "title",
    "예약": "schedule", "schedule": "schedule", "publish_at": "schedule",
    "태그": "tags", "tags": "tags",
    "공개": "privacy", "privacy": "privacy",
    "설명": "description", "description": "description",
}
_PRIVACY = {"비공개": "private", "일부공개": "unlisted", "일부 공개": "unlisted",
            "공개": "public", "private": "private", "unlisted": "unlisted", "public": "public"}
_DATE_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y.%m.%d %H:%M", "%Y/%m/%d %H:%M",
                 "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")


def parse_schedule(value: str) -> str:
    """'2026-11-20 18:00' (this computer's timezone), optionally followed by an
    offset like '+09:00' / '-05:00', or full ISO 8601 -> ISO 8601 with timezone."""
    value = " ".join(value.split())
    base, offset = value, ""
    head, _, tail = value.rpartition(" ")
    if head and tail[:1] in "+-" and ":" in tail:
        base, offset = head, tail
    when = None
    for fmt in _DATE_FORMATS:
        try:
            when = datetime.strptime(base, fmt)
            break
        except ValueError:
            continue
    if when is None:
        try:
            when = datetime.fromisoformat(value)  # e.g. 2026-11-20T18:00:00+09:00
            offset = ""
        except ValueError:
            raise ValueError(f"예약 '{value}' 형식을 모르겠어요. 예) 2026-11-20 18:00")
    if offset:
        when = datetime.fromisoformat(when.strftime("%Y-%m-%dT%H:%M:%S") + offset)
    if when.tzinfo is None:
        when = when.astimezone()  # this computer's local timezone
    return when.isoformat()


def parse_info(path: Path) -> Meta:
    fields = {"title": "", "schedule": "", "tags": "", "privacy": ""}
    description: List[str] = []
    in_description = False
    for line in read_text_any(path).splitlines():
        if in_description:
            description.append(line)
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition(":")
        name = _KEYS.get(key.strip().lower()) if sep else None
        if name == "description":
            in_description = True
            if value.strip():
                description.append(value.strip())
        elif name:
            fields[name] = value.strip()

    title = fields["title"]
    desc = "\n".join(description).strip()
    if not title:
        raise ValueError(f"{path.name}: '제목:' 이 비어 있어요")
    if not desc:
        raise ValueError(f"{path.name}: '설명:' 아래에 설명을 적어 주세요")
    privacy = None
    if fields["privacy"]:
        privacy = _PRIVACY.get(fields["privacy"].replace(" ", "").lower()) or _PRIVACY.get(fields["privacy"])
        if not privacy:
            raise ValueError(f"{path.name}: 공개는 비공개 / 일부공개 / 공개 중 하나로 적어 주세요")
    tags = [t.strip() for t in fields["tags"].replace("#", "").split(",") if t.strip()]
    return Meta(
        title=title,
        description=desc,
        tags=tags,
        privacy=privacy,
        publish_at=parse_schedule(fields["schedule"]) if fields["schedule"] else None,
    )

