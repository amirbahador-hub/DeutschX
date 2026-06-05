"""UI-agnostic lesson orchestration — the shared brain behind every frontend.

The CLI, the local API (and therefore the desktop / future web & mobile apps) all go
through these functions instead of duplicating the lesson logic. Everything here is
plain data in / plain data out, so it has no idea whether a terminal, an HTTP request,
or a native window is calling it.
"""
from __future__ import annotations

import re
import sys

from . import config, courses, srs, words
from .audio import stt as stt_mod
from .audio import tts as tts_mod
from .exercises import Grader, grade_pronunciation_local
from .memory import Topic, get_or_create, list_topics as _list_topics
from .tutor import Tutor, name_topic

# --- shared lesson constants -------------------------------------------------
NEXT_RE = re.compile(r"\[\[\s*NEXT\s*\]\]", re.IGNORECASE)

# Wraps a side-question so the tutor answers it but stays on the current item.
QUESTION_WRAP = (
    "[The learner has a question about the current point. Answer it clearly in the usual "
    "teaching style and languages, but do NOT move on to a new exercise, do NOT reveal "
    "the answer to the current exercise, and keep the current exercise active so the "
    "learner can still answer it afterwards. End by inviting them to answer the same "
    "current exercise.]\nQuestion: {q}"
)
# Sent when the learner is ready for the next item.
CONTINUE_MSG = "[The learner is ready to continue. Please present the next single exercise.]"


def split_next(text: str) -> tuple[str, str | None]:
    """Split a reply on the [[NEXT]] marker into (shown_now, next_exercise|None)."""
    m = NEXT_RE.search(text)
    if not m:
        return text.strip(), None
    before = text[: m.start()].strip()
    after = NEXT_RE.sub("", text[m.end():]).strip()
    return before, (after or None)


def _display_user(content: str) -> str | None:
    """Turn an internally-wrapped user message into what a learner should see."""
    if content.startswith("[The learner is ready"):
        return None  # the "continue" signal isn't shown
    m = re.match(r"\[The learner has a question.*?\]\nQuestion: (.*)", content, re.DOTALL)
    if m:
        return m.group(1).strip()
    return content


# --- helpers -----------------------------------------------------------------
def _generate(tutor: Tutor) -> str:
    """Run one tutor turn and return the full reply text."""
    chunks: list[str] = []
    tutor.stream_reply(lambda tok: chunks.append(tok))
    return "".join(chunks)


def _capture_vocab(text: str, slug: str, deck: srs.Deck) -> list[dict]:
    """Extract 🔤 vocab from text, add new cards to the deck, return all of them."""
    vocab = tts_mod.extract_vocab(text)
    added = sum(deck.add(v.german, v.english, topic=slug) for v in vocab)
    if added:
        deck.save()
    return [{"german": v.german, "meaning": v.english} for v in vocab]


def _reply_payload(shown: str, slug: str, *, pending: bool) -> dict:
    deck = srs.Deck.load()
    return {
        "shown": NEXT_RE.sub("", shown).strip(),
        "vocab": _capture_vocab(shown, slug, deck),
        "pending": pending,
    }


# --- public API --------------------------------------------------------------
def list_topics() -> list[dict]:
    return _list_topics()


def get_topic(slug: str) -> dict | None:
    topic = Topic.load(slug)
    if topic is None:
        return None
    last_ass = max((i for i, m in enumerate(topic.messages)
                    if m["role"] == "assistant"), default=-1)
    messages: list[dict] = []
    for i, m in enumerate(topic.messages):
        if m["role"] == "user":
            disp = _display_user(m["content"])
            if disp:
                messages.append({"role": "user", "content": disp})
        else:
            before, after = split_next(m["content"])
            if i == last_ass and topic.pending_next:
                content = before
            else:
                content = before + (f"\n\n{after}" if after else "")
            messages.append({"role": "assistant", "content": content.strip()})
    return {
        "slug": topic.slug,
        "name": topic.name,
        "status": topic.status,
        "pending": bool(topic.pending_next),
        "messages": messages,
    }


def create_topic(raw: str) -> dict:
    """Create (or reuse) a topic from a short name or a long pasted exercise."""
    raw = raw.strip()
    detailed = ("\n" in raw) or (len(raw) > 60)
    name = name_topic(raw) if detailed else raw
    initial = raw if detailed else None

    topic, created = get_or_create(name)
    reply = None
    if created or not topic.messages:
        tutor = Tutor(topic)
        tutor.add_user(initial or tutor.opening_line())
        full = _generate(tutor)
        tutor.add_assistant(full)
        before, after = split_next(full)
        topic.pending_next = ""
        shown = before + (f"\n\n{after}" if after else "")
        topic.save()
        reply = _reply_payload(shown, topic.slug, pending=False)
    return {"slug": topic.slug, "name": topic.name, "created": created, "reply": reply}


def post_message(slug: str, text: str, mode: str = "answer") -> dict:
    """Drive one lesson turn. mode: 'answer' | 'question' | 'continue'."""
    topic = Topic.load(slug)
    if topic is None:
        raise KeyError(slug)
    tutor = Tutor(topic)

    if mode == "continue":
        if topic.pending_next:  # reveal the already-generated next exercise (no API call)
            shown = topic.pending_next
            topic.pending_next = ""
            topic.save()
            return _reply_payload(shown, slug, pending=False)
        tutor.add_user(CONTINUE_MSG)
        hold = False
    elif mode == "question":
        tutor.add_user(QUESTION_WRAP.format(q=text))
        hold = False
    else:  # answer
        tutor.add_user(text)
        hold = True

    full = _generate(tutor)
    tutor.add_assistant(full)
    before, after = split_next(full)
    if hold and after:
        topic.pending_next = after
        shown = before
    else:
        topic.pending_next = ""
        shown = before + (f"\n\n{after}" if after else "")
    topic.save()
    return _reply_payload(shown, slug, pending=bool(hold and after))


# --- vocabulary & spaced-repetition review -----------------------------------
def _card_view(card: srs.Card) -> dict:
    return {
        "german": card.german,
        "english": card.english,
        "topic": card.topic,
        "reps": card.reps,
        "interval": card.interval,
        "due": card.due,
        "added_at": card.added_at,
        "is_due": card.is_due(),
    }


def _topic_filter(cards, topic: str | None) -> list:
    """Keep only cards first learned in `topic` (all cards when topic is falsy)."""
    cards = list(cards)
    return [c for c in cards if c.topic == topic] if topic else cards


def _stats(cards: list) -> dict:
    return {
        "total": len(cards),
        "due": sum(1 for c in cards if c.is_due()),
        "learned": sum(1 for c in cards if c.reps >= 3),
    }


def vocab_stats(topic: str | None = None) -> dict:
    return _stats(_topic_filter(srs.Deck.load().cards.values(), topic))


def list_vocab(topic: str | None = None) -> dict:
    """Cards with SM-2 state (optionally one topic), soonest-due first, plus stats."""
    deck = srs.Deck.load()
    cards = _topic_filter(deck.cards.values(), topic)
    cards.sort(key=lambda c: (c.due, c.added_at))
    return {"stats": _stats(cards), "cards": [_card_view(c) for c in cards]}


def review_due(topic: str | None = None) -> dict:
    """Cards due for review now (optionally scoped to one topic)."""
    due = _topic_filter(srs.Deck.load().due(), topic)
    return {"cards": [{"german": c.german, "english": c.english} for c in due]}


def add_vocab(german: str, english: str, topic: str = "") -> dict:
    """Add a word (e.g. a family member from word study) to the SRS deck."""
    deck = srs.Deck.load()
    added = deck.add(german, english, topic=topic)
    if added:
        deck.save()
    return {"added": added}


def check_vocab(text: str, meaning: str = "") -> dict:
    """AI-correct a vocab entry (article/spelling/meaning) before the learner saves it."""
    return words.check(text, meaning)


# --- word study --------------------------------------------------------------
def word_lookup(word: str, refresh: bool = False) -> dict:
    """Morphology + word family + conjugation for a word (cached to disk, AI on miss)."""
    return words.lookup(word, refresh=refresh)


def course(slug: str | None, name: str | None = None, refresh: bool = False) -> dict:
    """Progressive Paul-Noble-style sentence course for a topic (cached to disk)."""
    return courses.course(slug, name, refresh=refresh)


def review_grade(german: str, answer: str, direction: str = "en2de") -> dict:
    """Grade one review answer, reschedule the card via SM-2, persist, return result."""
    deck = srs.Deck.load()
    card = deck.cards.get(srs._norm(german))
    if card is None:
        raise KeyError(german)
    result = Grader().grade(card, answer, direction=direction)
    srs.schedule(card, result["quality"])
    deck.save()
    return {**result, "german": card.german, "english": card.english,
            "interval": card.interval}


# --- pronunciation (mic, via the sidecar host) -------------------------------
_recorder = stt_mod.Recorder()
_stt: stt_mod.STT | None = None


def pron_status() -> dict:
    """Whether mic pronunciation is available here, with a reason code if not."""
    cfg = config.load_config()
    if not cfg.get("stt_enabled", True):
        return {"available": False, "reason": "disabled"}
    if not stt_mod.STT.deps_installed():
        return {"available": False, "reason": "deps"}
    if not stt_mod.get_stt(cfg).available():
        return {"available": False, "reason": "no_mic"}
    return {"available": True, "reason": ""}


def pron_words(topic: str | None = None, limit: int = 8) -> dict:
    """Words to drill (optionally one topic): due cards first, else most recent."""
    deck = srs.Deck.load()
    pool = _topic_filter(deck.due(), topic) or _topic_filter(
        sorted(deck.cards.values(), key=lambda c: c.added_at, reverse=True), topic)
    return {"words": [{"german": c.german, "english": c.english} for c in pool[:limit]]}


def pron_start() -> dict:
    """Begin recording from the microphone (raises if mic is unavailable)."""
    status = pron_status()
    if not status["available"]:
        raise RuntimeError(status["reason"])
    _recorder.start()
    return {"recording": True}


def pron_stop(german: str, english: str = "") -> dict:
    """Stop recording, transcribe locally with Whisper, and grade the attempt.

    Grading is FREE by default: Whisper's transcription is compared to the target word
    locally (no API call). Only if `pron_ai_feedback` is enabled in settings do we ask
    Claude for detailed articulation tips (which costs credits).
    """
    global _stt
    cfg = config.load_config()
    audio = _recorder.stop()
    if _stt is None:
        _stt = stt_mod.get_stt(cfg)
    heard = _stt.transcribe(audio)
    if cfg.get("pron_ai_feedback"):
        result = Grader().grade_pronunciation(srs.Card(german=german, english=english), heard)
    else:
        result = grade_pronunciation_local(german, heard)
    return {**result, "heard": heard, "german": german}


# --- settings & audio --------------------------------------------------------
_SETTING_KEYS = ("ui_language", "native_language", "level", "voice", "voice_en",
                 "speech_rate", "tts_enabled", "stt_enabled", "pron_ai_feedback",
                 "auto_translate", "focus_mode")


def get_settings() -> dict:
    cfg = config.load_config()
    out = {k: cfg.get(k) for k in _SETTING_KEYS}
    out["levels"] = config.LEVELS
    out["has_api_key"] = bool(config.api_key())  # never expose the key itself
    out["platform"] = sys.platform
    return out


def set_api_key(key: str, validate: bool = True) -> dict:
    """Save the Anthropic API key; optionally verify it with a tiny test call."""
    config.set_api_key(key)
    if not key.strip():
        return {"saved": True, "valid": False}
    return {"saved": True, "valid": _validate_key() if validate else None}


def _validate_key() -> bool:
    try:
        from anthropic import Anthropic
        Anthropic().messages.create(
            model=config.load_config()["model"],
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        return True
    except Exception:
        return False


def update_settings(patch: dict) -> dict:
    """Merge known settings keys into the saved config and return the new settings."""
    cfg = config.load_config()
    for k, v in patch.items():
        if k in _SETTING_KEYS:
            cfg[k] = v
    config.save_config(cfg)
    return get_settings()


def list_voices(lang: str = "de") -> dict:
    """Installed TTS voices for a language ("de"/"en") on this OS, for the settings pickers."""
    return {"voices": tts_mod.list_voices(lang)}


def speak(text: str, rate: int | None = None, lang: str = "de") -> dict:
    """Speak text aloud on the host. lang 'de' uses the German voice, 'en' the English voice
    (so the Listen drill's English prompts aren't mangled by a German voice). Cross-platform."""
    cfg = config.load_config()
    backend = tts_mod.get_tts(cfg, lang)
    clean = re.sub(r"[*_`]", " ", text).strip()  # drop stray markdown before speaking
    available = backend.available()
    if available and clean:
        backend.speak(clean, rate=rate)
    return {"ok": True, "spoken": available}


def stop_speaking() -> dict:
    """Interrupt any in-progress TTS (used by the Listen drill's Pause for an instant stop)."""
    tts_mod.stop_all()
    return {"ok": True}
