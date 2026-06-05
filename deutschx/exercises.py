"""Quiz generation and AI grading for vocabulary review.

Claude grades a learner's answer leniently (tolerating typos/capitalization) while
still caring about the things that matter in German — like the correct article —
and returns an SM-2 quality score that feeds the scheduler.
"""
from __future__ import annotations

import difflib
import json
import re

from anthropic import Anthropic

from . import config
from .srs import Card

# German articles to ignore when matching a spoken noun ("der Mann" ≈ "Mann").
_ARTICLES = {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einen",
             "einem", "einer", "eines"}


def _norm_spoken(s: str) -> str:
    """Lowercase, strip markdown/punctuation, collapse spaces — for fuzzy matching."""
    s = s.lower().replace("ß", "ss")
    s = re.sub(r"[*_.,!?;:()\"'„“”»«\-–—]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _core(s: str) -> str:
    """The spoken string minus any leading/standalone articles."""
    return " ".join(t for t in _norm_spoken(s).split() if t not in _ARTICLES)


def grade_pronunciation_local(german: str, heard: str) -> dict:
    """Grade a spoken attempt with NO API call — compares Whisper's text to the target.

    Returns {"correct", "quality", "feedback"} just like the AI grader, using string
    similarity (difflib) on both the full phrase and its article-stripped core.
    """
    if not heard.strip():
        return {"correct": False, "quality": 0,
                "feedback": "Ich habe nichts verstanden — bitte nochmal versuchen."}

    # Weight the article-stripped core word heavily: a shared "der/die/das" must not
    # make two different nouns (Frau vs. Frage) look alike. The article only adds a
    # little credit on top.
    full = difflib.SequenceMatcher(None, _norm_spoken(german), _norm_spoken(heard)).ratio()
    core_t = _core(german)
    if core_t:
        core = difflib.SequenceMatcher(None, core_t, _core(heard)).ratio()
        score = 0.7 * core + 0.3 * full
    else:
        score = full

    if score >= 0.9:
        quality, msg = 5, "Perfekt ausgesprochen! 🎉"
    elif score >= 0.78:
        quality, msg = 4, "Sehr gut — fast perfekt."
    elif score >= 0.6:
        quality, msg = 3, f"Ganz okay. Ich habe „{heard}“ gehört."
    elif score >= 0.4:
        quality, msg = 2, f"Noch nicht ganz — ich habe „{heard}“ gehört. Versuch es nochmal."
    else:
        quality, msg = 1, f"Das klang eher wie „{heard}“. Hör nochmal zu und versuch es."
    return {"correct": score >= 0.72, "quality": quality, "feedback": msg}

GRADE_SYSTEM = """\
Du bist ein fairer, aber präziser Prüfer für deutschen Wortschatz. Du bewertest \
die Antwort eines Lernenden (Niveau B1–B2) auf eine Vokabelfrage.

Regeln:
- Sei nachsichtig bei Groß-/Kleinschreibung und kleinen Tippfehlern.
- Bei deutschen Substantiven ist der Artikel (der/die/das) wichtig: ein falscher \
oder fehlender Artikel senkt die Bewertung, ist aber nicht komplett falsch.
- Akzeptiere sinngleiche Synonyme.

Antworte AUSSCHLIESSLICH mit JSON in genau diesem Format:
{"correct": true/false, "quality": 0-5, "feedback": "<ein kurzer Satz auf Deutsch, \
englische Erklärung in Klammern wenn nötig>"}

quality-Skala: 5 = perfekt, 4 = richtig mit Kleinigkeit, 3 = knapp richtig/zögerlich, \
2 = fast, aber falsch, 1 = größtenteils falsch, 0 = keine Ahnung/leer.
"""

PRONUNCIATION_SYSTEM = """\
Du bewertest die Aussprache eines Deutschlernenden (B1–B2). Der Lernende hat ein \
Zielwort laut ausgesprochen, und eine Spracherkennung (Whisper) hat daraus Text \
gemacht. Du vergleichst den erkannten Text mit dem Zielwort.

Hinweise:
- Wenn der erkannte Text das Zielwort genau (oder als klare Beugung) enthält, war \
die Aussprache wahrscheinlich gut → hohe Bewertung.
- Wenn ein ähnlich klingendes, aber falsches Wort erkannt wurde, deutet das auf \
einen Aussprachefehler hin → erkläre kurz, worauf zu achten ist (z. B. Umlaute, \
„ch“, „r“, Vokallänge).
- Wenn nichts/Unsinniges erkannt wurde, bitte freundlich um einen neuen Versuch.

Antworte AUSSCHLIESSLICH mit JSON:
{"correct": true/false, "quality": 0-5, "feedback": "<ein kurzer, ermutigender Satz \
auf Deutsch, englische Hinweise in Klammern wenn nötig>"}
"""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class Grader:
    """Wraps the Claude client for grading answers."""

    def __init__(self):
        self.client = Anthropic()
        self.model = config.load_config()["model"]

    def grade(self, card: Card, answer: str, *, direction: str) -> dict:
        """Grade one answer. direction: 'en2de' or 'de2en'.

        Returns {"correct": bool, "quality": int, "feedback": str}.
        """
        answer = answer.strip()
        if not answer:
            return {"correct": False, "quality": 0, "feedback": "Keine Antwort gegeben."}

        if direction == "de2en":
            asked_for, expected, prompt_word = "die englische Bedeutung", card.english, card.german
        else:  # en2de
            asked_for, expected, prompt_word = "das deutsche Wort", card.german, card.english

        user_msg = (
            f"Deutsches Wort: „{card.german}“\n"
            f"Englische Bedeutung: „{card.english}“\n"
            f"Der Lernende sollte {asked_for} zu „{prompt_word}“ angeben.\n"
            f"Erwartete Antwort: „{expected}“\n"
            f"Antwort des Lernenden: „{answer}“\n\n"
            "Bewerte die Antwort und gib NUR das JSON zurück."
        )

        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=200,
                system=[{"type": "text", "text": GRADE_SYSTEM,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_msg}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text")
            return self._parse(text)
        except Exception as exc:
            # On any API/parse failure, fall back to a simple exact-ish check.
            return self._fallback(expected, answer, str(exc))

    def grade_pronunciation(self, card: Card, heard: str) -> dict:
        """Judge a spoken attempt: `heard` is what Whisper transcribed.

        Returns {"correct": bool, "quality": int, "feedback": str}.
        """
        if not heard.strip():
            return {"correct": False, "quality": 0,
                    "feedback": "Ich habe nichts verstanden — bitte nochmal versuchen."}

        user_msg = (
            f"Zielwort: „{card.german}“\n"
            f"Englische Bedeutung: „{card.english}“\n"
            f"Von der Spracherkennung verstanden: „{heard}“\n\n"
            "Bewerte die Aussprache und gib NUR das JSON zurück."
        )
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=200,
                system=[{"type": "text", "text": PRONUNCIATION_SYSTEM,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_msg}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text")
            return self._parse(text)
        except Exception:
            # Offline heuristic: did Whisper hear the target word at all?
            ok = card.german.split()[-1].lower() in heard.lower()
            return {"correct": ok, "quality": 5 if ok else 2,
                    "feedback": (f"Verstanden: „{heard}“." )+ " [offline-Bewertung]"}

    @staticmethod
    def _parse(text: str) -> dict:
        m = _JSON_RE.search(text)
        if not m:
            raise ValueError(f"no JSON in grader reply: {text!r}")
        data = json.loads(m.group(0))
        return {
            "correct": bool(data.get("correct", False)),
            "quality": int(data.get("quality", 0)),
            "feedback": str(data.get("feedback", "")).strip(),
        }

    @staticmethod
    def _fallback(expected: str, answer: str, err: str) -> dict:
        ok = expected.strip().lower() == answer.strip().lower()
        return {
            "correct": ok,
            "quality": 5 if ok else 1,
            "feedback": ("Richtig!" if ok else f"Erwartet: „{expected}“.")
            + " [offline-Bewertung]",
        }
