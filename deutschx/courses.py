"""Progressive sentence drills (Paul-Noble-style) — generated once, cached to disk.

A course for a theme is an ORDERED list of steps that starts trivially simple and grows
more complex. Crucially, every German word is first introduced as its own "block" step
(native → German) BEFORE it appears in a sentence, and sentences are built up cumulatively
— each new one reuses known pieces and adds one new element. Claude generates the course
once; we cache it to data/courses/<slug>.json so a theme is only ever paid for once.
"""
from __future__ import annotations

import json
import re

from anthropic import Anthropic

from . import config

COURSES_DIR = config.DATA_DIR / "courses"

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

SYSTEM = """\
You design progressive German listening drills in the style of Paul Noble, for a learner \
whose native language is {native} and whose German level is {level}. Given a THEME, produce \
an ordered course that teaches by building up, not by memorising lists.

Hard rules:
- Start TRIVIALLY simple and short, then gradually increase complexity as the course goes \
on: first tiny sentences, then longer ones, then add tenses, modal verbs, negation, and \
connectors (weil, dass, wenn) / subordinate clauses near the end.
- BEFORE any German word is first used in a sentence, introduce it as its own "block" step \
(a single word or small chunk: the {native} side, then the German). Reuse earlier blocks; \
never use a word in a sentence before its block has appeared.
- Build sentences CUMULATIVELY: each new sentence reuses pieces the learner already heard \
and adds only ONE new element.
- Stay on the THEME. Keep all German correct and natural for the {level} level.

Output ONLY this JSON (no prose, no markdown fences):
{{
  "steps": [
    {{"type": "block",    "en": "<{native} word/chunk>", "de": "<German>"}},
    {{"type": "sentence", "en": "<{native} sentence>",   "de": "<German sentence>"}}
  ]
}}
Interleave blocks so each appears JUST before it's first needed. Provide roughly 8-12 \
blocks and 12-18 sentences, ordered from simplest to most complex. "en" is the prompt the \
learner hears first (in {native}); "de" is the German answer they should produce.
"""


def _slug(name: str) -> str:
    s = name.strip().lower()
    s = s.replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "kurs"


def _normalize(data: dict) -> list[dict]:
    steps: list[dict] = []
    for s in data.get("steps", []):
        en = str(s.get("en", "")).strip()
        de = str(s.get("de", "")).strip()
        if not en or not de:
            continue
        kind = "block" if str(s.get("type", "")).strip().lower() == "block" else "sentence"
        steps.append({"type": kind, "en": en, "de": de})
    return steps[:48]


def _generate(theme: str) -> dict:
    cfg = config.load_config()
    native = cfg.get("native_language", "English")
    level = cfg.get("level", "A2-B1")
    client = Anthropic()
    resp = client.messages.create(
        model=cfg["model"],
        max_tokens=2600,
        system=[{"type": "text", "text": SYSTEM.format(native=native, level=level),
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"THEME: {theme}"}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError(f"no JSON in course: {text!r}")
    steps = _normalize(json.loads(m.group(0)))
    return {"theme": theme, "level": level, "steps": steps}


def course(slug: str | None, name: str | None = None, *, refresh: bool = False) -> dict:
    """Return the cached course for a topic (by slug), generating it once on a miss.

    `slug` keys the cache (None → a general beginner course); `name` is the human theme
    used in the prompt.
    """
    key = slug or "_general"
    theme = (name or "").strip() or "Alltagsdeutsch — simple everyday German basics"
    COURSES_DIR.mkdir(parents=True, exist_ok=True)
    path = COURSES_DIR / f"{_slug(key)}.json"
    if path.exists() and not refresh:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {**data, "cached": True}
    data = _generate(theme)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {**data, "cached": False}
