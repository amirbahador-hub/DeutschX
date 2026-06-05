"""Central configuration: paths, defaults, and persisted settings.

Data (lessons, vocab, settings, the API key) lives entirely on the user's own machine —
nothing is ever uploaded. In a packaged app the program files are read-only, so we keep
all writable data in the per-OS application-data directory.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# --- Paths -------------------------------------------------------------------
def _app_data_dir() -> Path:
    """The per-OS, user-writable folder for DeutschX's data.

    Override with DEUTSCHX_DATA_DIR (handy for development: point it at ./data).
    """
    override = os.getenv("DEUTSCHX_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / "DeutschX"


# Project root is the parent of the `deutschx` package directory.
ROOT = Path(__file__).resolve().parent.parent
_LEGACY_DATA = ROOT / "data"  # where data lived when run from a source checkout

DATA_DIR = _app_data_dir()
TOPICS_DIR = DATA_DIR / "topics"
TOPICS_INDEX = DATA_DIR / "topics.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
CONFIG_FILE = DATA_DIR / "config.json"

# --- Defaults ----------------------------------------------------------------
DEFAULT_CONFIG = {
    "model": os.getenv("DEUTSCHX_MODEL", "claude-sonnet-4-6"),
    "api_key": "",  # Anthropic key; set in-app (env ANTHROPIC_API_KEY still wins)
    "voice": "",  # TTS German voice; "" = the platform's sensible default
    "voice_en": "",  # TTS English voice (Listen-drill prompts); "" = default
    "speech_rate": 170,  # words per minute (a touch slow, good for learners)
    "tts_enabled": True,  # auto-speak new vocabulary
    "stt_enabled": False,  # microphone pronunciation (opt-in; downloads a model)
    "pron_ai_feedback": False,  # use Claude for detailed pronunciation tips (costs credits)
    "stt_model": "base",  # faster-whisper model (tiny/base/small); base ≈ 145 MB
    "level": "A2-B1",  # the learner's German level (configurable)
    "ui_language": "en",  # interface language: "en" or "de"
    "native_language": "English",  # used for explanations & translations (any language)
    "auto_translate": False,  # auto-append a native-language translation after each reply
    "focus_mode": False,  # clear the screen before each step (opt-in; keeps scrollback off)
}

# Supported German levels, easiest first.
LEVELS = ["A1", "A2", "A2-B1", "B1", "B1-B2", "B2", "C1"]


def _migrate_legacy() -> None:
    """Copy data from an old in-repo ./data into the app-data dir, once.

    Preserves an existing user's lessons when they move from a source checkout to the
    app-data location. Non-destructive (copies; never deletes the original).
    """
    if DATA_DIR == _LEGACY_DATA:
        return
    if (DATA_DIR / "config.json").exists():
        return  # already set up at the new location
    if not (_LEGACY_DATA / "config.json").exists():
        return  # nothing to migrate
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for item in _LEGACY_DATA.iterdir():
        dest = DATA_DIR / item.name
        if dest.exists():
            continue
        try:
            shutil.copytree(item, dest) if item.is_dir() else shutil.copy2(item, dest)
        except Exception:
            pass  # a best-effort convenience; never block startup over it


def ensure_dirs() -> None:
    """Create the data directories if they don't yet exist (migrating legacy data once)."""
    _migrate_legacy()
    TOPICS_DIR.mkdir(parents=True, exist_ok=True)


# --- API key -----------------------------------------------------------------
def api_key() -> str | None:
    """The Anthropic API key: the environment wins (dev/CI), else the saved setting."""
    env = os.getenv("ANTHROPIC_API_KEY")
    if env:
        return env
    return load_config().get("api_key") or None


def set_api_key(key: str) -> None:
    """Persist the API key to settings and make it visible to the Anthropic SDK now."""
    cfg = load_config()
    cfg["api_key"] = key.strip()
    save_config(cfg)
    if key.strip():
        os.environ["ANTHROPIC_API_KEY"] = key.strip()


def ensure_api_key() -> None:
    """Export the saved key into the environment (the Anthropic SDK reads it from there)."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        key = load_config().get("api_key")
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key


def load_config() -> dict:
    """Load persisted settings, falling back to (and seeding) defaults."""
    ensure_dirs()
    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return {**DEFAULT_CONFIG, **cfg}  # backfill keys added in newer versions
    save_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
