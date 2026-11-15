"""Loads channels.json: one OAuth client, one entry per language channel."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ChannelConfig:
    key: str  # folder name inside a job, e.g. "ko", "en", "ja"
    token_path: Path
    language: str  # BCP-47 code used for defaultLanguage / captions
    channel_id: Optional[str] = None  # expected channel; upload aborts on mismatch
    name: str = ""
    privacy: str = "private"
    category_id: str = "27"  # 27 = Education
    tags: List[str] = field(default_factory=list)
    description_footer: str = ""
    made_for_kids: bool = False
    contains_synthetic_media: Optional[bool] = None


@dataclass
class AppConfig:
    path: Path
    client_secret: Path
    channels: Dict[str, ChannelConfig]


def _resolve(base: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else (base / p)


def load_config(path: str) -> AppConfig:
    cfg_path = Path(path).expanduser().resolve()
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"Config not found: {cfg_path}\n"
            "Copy channels.example.json to channels.json and fill it in."
        )
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    base = cfg_path.parent

    channels: Dict[str, ChannelConfig] = {}
    for key, ch in data.get("channels", {}).items():
        channels[key] = ChannelConfig(
            key=key,
            token_path=_resolve(base, ch.get("token", f"tokens/{key}.json")),
            language=ch.get("language", key),
            channel_id=ch.get("channel_id") or None,
            name=ch.get("name", ""),
            privacy=ch.get("privacy", "private"),
            category_id=str(ch.get("category_id", "27")),
            tags=list(ch.get("tags", [])),
            description_footer=ch.get("description_footer", ""),
            made_for_kids=bool(ch.get("made_for_kids", False)),
            contains_synthetic_media=ch.get("contains_synthetic_media"),
        )
    if not channels:
        raise ValueError(f"No channels defined in {cfg_path}")

    return AppConfig(
        path=cfg_path,
        client_secret=_resolve(base, data.get("client_secret", "secrets/client_secret.json")),
        channels=channels,
    )
