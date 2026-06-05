"""Persistent learning state stored as plain local files.

Each topic lives in its own JSON file under data/topics/<slug>.json and holds the
full conversation transcript so a session can be resumed with complete context.
A lightweight index (data/topics.json) lists every topic for quick browsing.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from . import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(name: str, max_len: int = 60) -> str:
    """Turn a topic name into a filesystem-safe slug (umlauts transliterated).

    Capped to `max_len` characters so an over-long name can't blow past the
    filesystem's filename limit.
    """
    replacements = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    text = "".join(replacements.get(ch, ch) for ch in name.lower())
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text or "topic"


@dataclass
class Topic:
    slug: str
    name: str
    status: str = "active"  # "active" | "learned"
    created_at: str = field(default_factory=_now)
    last_studied: str = field(default_factory=_now)
    summary: str = ""
    # Full conversation transcript: list of {"role", "content"} dicts.
    messages: list[dict] = field(default_factory=list)
    # The next exercise that's been generated but not yet revealed to the learner.
    pending_next: str = ""

    @property
    def path(self):
        return config.TOPICS_DIR / f"{self.slug}.json"

    def save(self) -> None:
        config.ensure_dirs()
        self.last_studied = _now()
        self.path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _update_index(self)

    @classmethod
    def load(cls, slug: str) -> "Topic | None":
        path = config.TOPICS_DIR / f"{slug}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)


def _update_index(topic: Topic) -> None:
    index = _read_index()
    index[topic.slug] = {
        "slug": topic.slug,
        "name": topic.name,
        "status": topic.status,
        "created_at": topic.created_at,
        "last_studied": topic.last_studied,
        "turns": len([m for m in topic.messages if m["role"] == "user"]),
    }
    config.TOPICS_INDEX.write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _read_index() -> dict:
    if config.TOPICS_INDEX.exists():
        return json.loads(config.TOPICS_INDEX.read_text(encoding="utf-8"))
    return {}


def list_topics() -> list[dict]:
    """Return topic index entries, most recently studied first."""
    entries = list(_read_index().values())
    entries.sort(key=lambda e: e.get("last_studied", ""), reverse=True)
    return entries


def get_or_create(name: str) -> tuple[Topic, bool]:
    """Return (topic, created). Reuses an existing topic with the same slug."""
    slug = slugify(name)
    existing = Topic.load(slug)
    if existing:
        return existing, False
    topic = Topic(slug=slug, name=name.strip())
    topic.save()
    return topic, True


# --- Session log -------------------------------------------------------------
def log_session(slug: str, turns: int) -> None:
    """Append a short record of a finished study session."""
    sessions = []
    if config.SESSIONS_FILE.exists():
        sessions = json.loads(config.SESSIONS_FILE.read_text(encoding="utf-8"))
    sessions.append({"slug": slug, "turns": turns, "ended_at": _now()})
    config.SESSIONS_FILE.write_text(
        json.dumps(sessions, indent=2, ensure_ascii=False), encoding="utf-8"
    )
