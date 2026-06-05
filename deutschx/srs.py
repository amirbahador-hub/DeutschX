"""Spaced-repetition vocabulary deck using the SM-2 algorithm.

Words the tutor introduces are captured as cards in data/vocab.json. Each card
carries SM-2 scheduling state so due words resurface over time and you don't forget
what you learned in earlier topics.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from . import config


def today() -> date:
    return date.today()


def _norm(german: str) -> str:
    """Normalize a German term to a dedup key (lowercase, collapse spaces)."""
    return re.sub(r"\s+", " ", german.strip().lower())


@dataclass
class Card:
    german: str
    english: str
    topic: str = ""  # originating topic slug
    example: str = ""
    added_at: str = ""
    # --- SM-2 state ---
    ease: float = 2.5  # easiness factor (>= 1.3)
    interval: int = 0  # days until next review
    reps: int = 0  # number of consecutive correct reviews
    lapses: int = 0  # times forgotten
    due: str = ""  # ISO date the card is next due
    last_reviewed: str = ""

    def is_due(self, on: date | None = None) -> bool:
        on = on or today()
        return self.due <= on.isoformat()


def schedule(card: Card, quality: int, on: date | None = None) -> Card:
    """Apply one SM-2 review with quality 0–5 and update the card in place.

    quality: 0–2 = forgotten (lapse), 3 = hard, 4 = good, 5 = easy.
    """
    on = on or today()
    quality = max(0, min(5, quality))

    if quality < 3:
        card.reps = 0
        card.lapses += 1
        card.interval = 1
    else:
        card.reps += 1
        if card.reps == 1:
            card.interval = 1
        elif card.reps == 2:
            card.interval = 6
        else:
            card.interval = round(card.interval * card.ease)
        # Update easiness factor (SM-2 formula), floored at 1.3.
        card.ease = max(
            1.3,
            card.ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)),
        )

    card.due = (on + timedelta(days=card.interval)).isoformat()
    card.last_reviewed = on.isoformat()
    return card


class Deck:
    """All vocabulary cards, persisted to data/vocab.json (keyed by german)."""

    def __init__(self, cards: dict[str, Card]):
        self.cards = cards

    # --- persistence ---
    @classmethod
    def load(cls) -> "Deck":
        config.ensure_dirs()
        path = config.DATA_DIR / "vocab.json"
        if not path.exists():
            return cls({})
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls({k: Card(**v) for k, v in raw.items()})

    def save(self) -> None:
        config.ensure_dirs()
        path = config.DATA_DIR / "vocab.json"
        data = {k: asdict(c) for k, c in self.cards.items()}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- operations ---
    def add(self, german: str, english: str, *, topic: str = "", example: str = "") -> bool:
        """Add a new card. Returns True if it was new (False if already known)."""
        key = _norm(german)
        if not key or key in self.cards:
            return False
        t = today().isoformat()
        self.cards[key] = Card(
            german=german.strip(),
            english=english.strip(),
            topic=topic,
            example=example,
            added_at=t,
            due=t,  # due immediately the first time
        )
        return True

    def due(self, on: date | None = None) -> list[Card]:
        """Cards due for review, soonest-due first."""
        items = [c for c in self.cards.values() if c.is_due(on)]
        items.sort(key=lambda c: (c.due, c.added_at))
        return items

    def stats(self) -> dict:
        total = len(self.cards)
        due = len(self.due())
        learned = sum(1 for c in self.cards.values() if c.reps >= 3)
        return {"total": total, "due": due, "learned": learned}
