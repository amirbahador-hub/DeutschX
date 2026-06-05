"""The teaching brain: wraps the Claude API into a resumable tutoring loop."""
from __future__ import annotations

from anthropic import Anthropic

from . import config
from .memory import Topic

MAX_TOKENS = 1500

# Levels at or below this lean more heavily on the learner's native language.
_LOWER_LEVELS = {"A1", "A2", "A2-B1"}


def build_system_prompt(level: str, native_language: str) -> str:
    """Build a teaching prompt tuned to the learner's level and native language."""
    if level in _LOWER_LEVELS:
        balance = (
            f"Since the learner is at a lower level ({level}), use SIMPLE German and "
            f"lean on {native_language} generously: introduce each idea in German, then "
            f"explain it in {native_language}. Keep German sentences short."
        )
    else:
        balance = (
            f"The learner is at {level}, so speak mostly in German at that level and "
            f"only drop into {native_language} for genuinely tricky points."
        )
    return f"""\
You are "DeutschX", a patient, encouraging German teacher. The learner wants to study
a specific topic. The learner's German level is {level} and their native language is
{native_language}.

How you teach:
- {balance}
- Teach the topic step by step with concrete example sentences.
- Regularly ask the learner short comprehension questions and WAIT for the answer
  before continuing. Never dump too much at once.
- When the learner makes a mistake, correct it kindly: show the right form, briefly
  say why (in {native_language} if helpful), and give another example.

Working through exercises (very important):
- Work through exercises ONE item at a time. Never present several items to solve at once.
- NEVER reveal the answer to an item before the learner has attempted it. When introducing
  a new pattern you may show ONE fully worked example, but the item you then ask the
  learner to do must be a DIFFERENT one that you leave unsolved.
- After the learner answers, give your feedback and the correct form for THAT item.

Output protocol (MANDATORY):
- Whenever your message ends by giving the learner a NEW single exercise to answer, put a
  line containing exactly [[NEXT]] immediately BEFORE that exercise. Everything before
  [[NEXT]] is feedback/explanation about the previous item; everything after [[NEXT]] is
  the one new exercise (with any hints/vocab it needs).
- Put only ONE exercise after [[NEXT]].
- If your message does NOT give a new exercise to answer (e.g. you are only answering the
  learner's question), do NOT include [[NEXT]].
- Whenever you introduce an important NEW word, mark it on its own line exactly like:
  "🔤 das Beispiel (-e) — <meaning in {native_language}>" so the learner knows it's new
  and it can be saved for review. Always give the article for nouns.
- Be warm and motivating, and keep replies focused (not too long).

You remember the conversation so far for this topic and continue the lesson seamlessly
when the learner returns.
"""


def name_topic(text: str) -> str:
    """Ask Claude for a short German topic title from the learner's request.

    The request may be a long pasted exercise; we only want a concise title to use
    as the topic name (and filename). Falls back to a trimmed first line on error.
    """
    fallback = (text.splitlines()[0].strip() if text.strip() else "Deutsch-Thema")[:50]
    try:
        client = Anthropic()
        model = config.load_config()["model"]
        resp = client.messages.create(
            model=model,
            max_tokens=40,
            system=[{
                "type": "text",
                "text": ("You name German-learning topics. Given the learner's request "
                         "(which may be an exercise or a long paste), reply with a SHORT, "
                         "clear topic title in German — at most 6 words. Prefer the grammar "
                         "concept or overall theme being practiced (e.g. 'Genitiv: Formen "
                         "bilden'), not one specific example. No surrounding quotes, no "
                         "trailing punctuation. Output only the title."),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": text[:2000]}],
        )
        title = "".join(b.text for b in resp.content if b.type == "text")
        title = title.splitlines()[0].strip().strip("\"'").rstrip(".")
        return title or fallback
    except Exception:
        return fallback or "Deutsch-Thema"


class Tutor:
    """Holds a Claude client and drives one topic's conversation."""

    def __init__(self, topic: Topic):
        self.topic = topic
        self.client = Anthropic()  # reads ANTHROPIC_API_KEY from env
        cfg = config.load_config()
        self.model = cfg["model"]
        self.native_language = cfg.get("native_language", "English")
        self.system_prompt = build_system_prompt(
            cfg.get("level", "A2-B1"), self.native_language
        )

    def _system_blocks(self) -> list[dict]:
        # Cache the (large, static) system prompt to cut cost on every turn.
        return [
            {
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def opening_line(self) -> str:
        """First message when starting a brand-new topic (no history yet)."""
        return (
            f"Ich möchte das Thema „{self.topic.name}“ lernen. "
            f"Bitte fang an und erkläre es mir Schritt für Schritt."
        )

    def stream_reply(self, on_text) -> str:
        """Send the current transcript to Claude and stream the reply.

        `on_text` is called with each text delta (for live printing).
        Returns the full assistant reply text.
        """
        chunks: list[str] = []
        with self.client.messages.stream(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=self._system_blocks(),
            messages=self.topic.messages,
        ) as stream:
            for text in stream.text_stream:
                chunks.append(text)
                on_text(text)
        return "".join(chunks)

    def translate(self, text: str, target_language: str | None = None) -> str:
        """Translate German text into the learner's native language (on demand)."""
        target = target_language or self.native_language
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            system=[{
                "type": "text",
                "text": (f"Translate the user's German text into {target}. "
                         "Output ONLY the translation, preserving line breaks and "
                         "any 🔤 vocabulary markers. Do not add commentary."),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": text}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def extract_readables(self, text: str) -> list[dict]:
        """Pull the German sentences/phrases worth reading aloud, with translations.

        Returns a list of {"de": <German>, "meaning": <translation>} dicts, ignoring
        English explanation, headings and emoji. Returns [] if none are found.
        """
        import json
        import re

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=900,
            system=[{
                "type": "text",
                "text": (
                    "You are given one German-lesson message. Return the SINGLE German "
                    "sentence or phrase the learner most wants to hear aloud right now:\n"
                    "- if the message poses a current exercise/question to answer (often "
                    "after 'your turn', 'try this', a letter like 'c)', or ending with a "
                    "question), return that exercise phrase, e.g. 'die Kosten vom "
                    "Anwalt-Service';\n"
                    "- otherwise (e.g. it's feedback) return the main corrected answer or "
                    "key German example sentence, e.g. 'die Eröffnung des Kontos'.\n"
                    "Prefer a full phrase/sentence over isolated dictionary glosses (lines "
                    "like '🔤 das Wort — meaning'). Ignore headings, English and emoji. "
                    "Quote the German EXACTLY as it appears in the message — never solve, "
                    "transform, complete or correct the exercise. "
                    f"Give a natural translation into "
                    f"{self.native_language}. Return ONLY a JSON array "
                    '[{"de": "...", "meaning": "..."}] — usually one element; [] only if '
                    "there is no German at all."
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": text}],
        )
        raw = "".join(b.text for b in resp.content if b.type == "text")
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
        items = []
        for d in data:
            de = str(d.get("de", "")).strip()
            if de:
                items.append({"de": de, "meaning": str(d.get("meaning", "")).strip()})
        return items

    def last_assistant_text(self) -> str | None:
        for m in reversed(self.topic.messages):
            if m["role"] == "assistant":
                return m["content"]
        return None

    def add_user(self, text: str) -> None:
        self.topic.messages.append({"role": "user", "content": text})

    def add_assistant(self, text: str) -> None:
        self.topic.messages.append({"role": "assistant", "content": text})
