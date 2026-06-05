"""Text-to-speech for German vocabulary — cross-platform.

Uses each OS's built-in speech so there are no heavy dependencies:
  • macOS   → the `say` command
  • Windows → System.Speech (SAPI) via PowerShell
  • Linux   → espeak-ng / espeak (or speech-dispatcher's spd-say)
If none is available, audio simply degrades gracefully (the app keeps working silently).
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

# Matches a vocab item the tutor marks, e.g. "🔤 das Beispiel (-e) — example".
# The separator must have surrounding spaces so the hyphen inside "(-e)" never matches.
_VOCAB_RE = re.compile(r"🔤\s*(.+?)\s+(?:[—–]|-)\s+(.+)")
# Parenthetical hints like "(-e)" or "(der)" — spoken aloud they're just noise.
_PAREN_RE = re.compile(r"\([^)]*\)")


@dataclass
class Vocab:
    german: str  # cleaned form, good for display
    english: str

    @property
    def spoken(self) -> str:
        """The German text to actually pronounce (parentheticals removed)."""
        return _PAREN_RE.sub("", self.german).strip()


def extract_vocab(text: str) -> list[Vocab]:
    """Pull out every 🔤-marked vocabulary item from an assistant reply."""
    items: list[Vocab] = []
    for line in text.splitlines():
        m = _VOCAB_RE.search(line)
        if m:
            german = _PAREN_RE.sub("", m.group(1)).strip() or m.group(1).strip()
            items.append(Vocab(german=german, english=m.group(2).strip()))
    return items


class TTSBackend:
    """Interface every voice backend implements."""

    name = "base"

    def available(self) -> bool:
        raise NotImplementedError

    def speak(self, text: str, *, rate: int | None = None) -> None:
        raise NotImplementedError


class MacSayBackend(TTSBackend):
    """macOS's built-in `say` command — free, offline, instant."""

    name = "macos-say"

    def __init__(self, voice: str = "Anna (Premium)", rate: int = 170):
        self.voice = voice
        self.rate = rate

    def available(self) -> bool:
        return platform.system() == "Darwin" and shutil.which("say") is not None

    def speak(self, text: str, *, rate: int | None = None) -> None:
        if not text.strip():
            return
        cmd = ["say", "-v", self.voice, "-r", str(rate or self.rate), text]
        try:
            subprocess.run(cmd, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            subprocess.run(["say", text], check=False)  # fall back to the default voice


class WindowsSapiBackend(TTSBackend):
    """Windows System.Speech (SAPI) driven through PowerShell — no extra install."""

    name = "win-sapi"

    def __init__(self, voice: str = "", rate: int = 170):
        self.voice = voice
        self.rate = rate

    def _ps(self) -> str | None:
        return shutil.which("powershell") or shutil.which("pwsh")

    def available(self) -> bool:
        return os.name == "nt" and self._ps() is not None

    def speak(self, text: str, *, rate: int | None = None) -> None:
        if not text.strip():
            return
        wpm = rate or self.rate
        sapi_rate = max(-10, min(10, round((wpm - 200) / 12)))  # SAPI rate is -10..10
        select = f"$s.SelectVoice('{self.voice}');" if self.voice else ""
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f"try{{{select}}}catch{{}}"
            f"$s.Rate={sapi_rate};"
            "$s.Speak([Console]::In.ReadToEnd())"
        )
        try:
            subprocess.run([self._ps(), "-NoProfile", "-Command", script],
                           input=text, text=True, check=False)
        except Exception:
            pass


class LinuxBackend(TTSBackend):
    """Linux speech via espeak-ng / espeak, falling back to speech-dispatcher."""

    name = "linux-espeak"

    def __init__(self, lang: str = "de", voice: str = "", rate: int = 170):
        self.lang = lang
        self.voice = voice
        self.rate = rate

    def _exe(self) -> str | None:
        return shutil.which("espeak-ng") or shutil.which("espeak")

    def available(self) -> bool:
        return self._exe() is not None or shutil.which("spd-say") is not None

    def speak(self, text: str, *, rate: int | None = None) -> None:
        if not text.strip():
            return
        wpm = rate or self.rate
        exe = self._exe()
        try:
            if exe:
                voice = self.voice or self.lang  # a named espeak voice, or just "de"/"en"
                subprocess.run([exe, "-v", voice, "-s", str(wpm), text], check=False)
            elif shutil.which("spd-say"):
                subprocess.run(["spd-say", "-w", "-l", self.lang, text], check=False)
        except Exception:
            pass


def get_tts(cfg: dict, lang: str = "de") -> TTSBackend:
    """Build the right TTS backend for this OS, configured for the given language."""
    rate = int(cfg.get("speech_rate", 170))
    voice = (cfg.get("voice_en") if lang == "en" else cfg.get("voice")) or ""
    if sys.platform == "darwin":
        default = "Samantha" if lang == "en" else "Anna (Premium)"
        return MacSayBackend(voice=voice or default, rate=rate)
    if os.name == "nt":
        return WindowsSapiBackend(voice=voice, rate=rate)
    return LinuxBackend(lang=lang, voice=voice, rate=rate)


# --- voice discovery (per platform) ------------------------------------------
def _mac_voices(lang: str) -> list[str]:
    if not shutil.which("say"):
        return []
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True).stdout
    voices = []
    for line in out.splitlines():
        m = re.match(r"(.+?)\s{2,}([a-z]{2}_[A-Z]{2})", line)
        if m and m.group(2).startswith(lang):
            voices.append(m.group(1).strip())
    return voices


def _win_voices(lang: str) -> list[str]:
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        return []
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices()|"
        "%{ $_.VoiceInfo }|%{ \"$($_.Name)`t$($_.Culture)\" }"
    )
    out = subprocess.run([ps, "-NoProfile", "-Command", script],
                         capture_output=True, text=True, check=True).stdout
    voices = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].strip().lower().startswith(lang):
            voices.append(parts[0].strip())
    return voices


def _linux_voices(lang: str) -> list[str]:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        return []
    out = subprocess.run([exe, "--voices=" + lang], capture_output=True, text=True,
                         check=False).stdout
    voices = []
    for line in out.splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 4:
            voices.append(cols[3])
    return voices


def list_voices(lang: str = "de") -> list[str]:
    """Installed voices for a language ("de"/"en") on this OS, for the settings pickers."""
    try:
        if sys.platform == "darwin":
            return _mac_voices(lang)
        if os.name == "nt":
            return _win_voices(lang)
        return _linux_voices(lang)
    except Exception:
        return []


def stop_all() -> None:
    """Best-effort: interrupt any in-progress speech (used by the Listen drill's Pause)."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["killall", "say"], check=False, capture_output=True)
        elif os.name == "nt":
            subprocess.run(["taskkill", "/F", "/IM", "powershell.exe"],
                           check=False, capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "espeak"], check=False, capture_output=True)
            subprocess.run(["killall", "spd-say"], check=False, capture_output=True)
    except Exception:
        pass
