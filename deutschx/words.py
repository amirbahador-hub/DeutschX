"""Deep word study: morphology, word family, conjugation — cached to disk.

A lot of German vocabulary is best understood by its *parts* and its *family*:
`Versicherung` = ver- + sicher + -ung, and it sits next to `sicher` (adj), `sichern`
(verb), `die Sicherheit` (noun), `sicherlich` (adv). Claude generates that breakdown
once per word and we cache it to data/words/<slug>.json, so a word is only ever paid
for once — every later lookup is instant and free. We also add deep links to Linguee
(real bilingual examples) and Wiktionary (official conjugation/declension tables).
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote

from anthropic import Anthropic

from . import config

WORDS_DIR = config.DATA_DIR / "words"

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

SYSTEM = """\
You are a German lexicographer for language learners. Given ONE German word (it may \
arrive inflected, lowercased, or with stray markdown), analyse its DICTIONARY HEADWORD \
and return a rich, accurate breakdown.

Explain meanings in {native}. Be precise about German grammar (articles, plurals, \
separable prefixes, strong/weak verbs). For the morpheme breakdown, split the word into \
its real parts (prefix(es), root/stem, suffix(es)) and say what EACH part contributes to \
the meaning — e.g. ver- (transforms/provides), sicher (safe/sure), -ung (makes a noun: \
the act/result). For the family, list the most useful related words across parts of \
speech (noun, verb, adjective, adverb) that share the root.

Respond with ONLY this JSON (no markdown fences, no commentary):
{{
  "word": "<dictionary headword, correctly capitalised>",
  "pos": "<noun|verb|adjective|adverb|other>",
  "translation": "<meaning in {native}>",
  "article": "<der|die|das, or empty if not a noun>",
  "plural": "<plural form for nouns, else empty>",
  "morphemes": [
    {{"part": "<surface piece, e.g. ver->", "type": "<prefix|root|suffix|linking>", "meaning": "<what it contributes, in {native}>"}}
  ],
  "family": [
    {{"word": "<related word, with article if noun>", "pos": "<noun|verb|adjective|adverb>", "meaning": "<meaning in {native}>"}}
  ],
  "conjugation": {{
    "infinitive": "<for verbs, else empty>",
    "present_3sg": "<er/sie/es form, else empty>",
    "praeteritum_3sg": "<simple past 3sg, else empty>",
    "perfect_3sg": "<auxiliary + Partizip II, e.g. 'hat versichert', else empty>",
    "participle": "<Partizip II, else empty>"
  }},
  "examples": [
    {{"de": "<natural German example sentence>", "translation": "<{native} translation>"}}
  ],
  "note": "<one short extra tip, or empty>"
}}
Give 4-6 family items and 2-3 examples. Leave conjugation fields empty for non-verbs.
"""


def _clean(word: str) -> str:
    """Strip markdown/whitespace noise from an incoming word."""
    return re.sub(r"\s+", " ", word.replace("*", " ").replace("_", " ")).strip()


def _slug(word: str) -> str:
    """Filesystem-safe cache key (umlauts transliterated)."""
    s = word.strip().lower()
    s = s.replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "wort"


def _links(headword: str) -> dict:
    """Deep links to real examples (Linguee) and official tables (Wiktionary)."""
    q = quote(headword)
    return {
        "linguee_url": f"https://www.linguee.com/german-english/search?source=german&query={q}",
        "wiktionary_url": f"https://en.wiktionary.org/wiki/{q}#German",
    }


def _with_links(data: dict) -> dict:
    head = data.get("word") or ""
    return {**data, **_links(head)}


def _normalize(data: dict, fallback_word: str) -> dict:
    """Fill in any missing keys so the frontend can rely on a stable shape."""
    conj = data.get("conjugation") or {}
    return {
        "word": str(data.get("word") or fallback_word).strip(),
        "pos": str(data.get("pos") or "other").strip(),
        "translation": str(data.get("translation") or "").strip(),
        "article": str(data.get("article") or "").strip(),
        "plural": str(data.get("plural") or "").strip(),
        "morphemes": [
            {"part": str(m.get("part", "")).strip(),
             "type": str(m.get("type", "")).strip(),
             "meaning": str(m.get("meaning", "")).strip()}
            for m in data.get("morphemes", []) if m.get("part")
        ],
        "family": [
            {"word": str(f.get("word", "")).strip(),
             "pos": str(f.get("pos", "")).strip(),
             "meaning": str(f.get("meaning", "")).strip()}
            for f in data.get("family", []) if f.get("word")
        ],
        "conjugation": {
            "infinitive": str(conj.get("infinitive", "")).strip(),
            "present_3sg": str(conj.get("present_3sg", "")).strip(),
            "praeteritum_3sg": str(conj.get("praeteritum_3sg", "")).strip(),
            "perfect_3sg": str(conj.get("perfect_3sg", "")).strip(),
            "participle": str(conj.get("participle", "")).strip(),
        },
        "examples": [
            {"de": str(e.get("de", "")).strip(),
             "translation": str(e.get("translation", "")).strip()}
            for e in data.get("examples", []) if e.get("de")
        ],
        "note": str(data.get("note") or "").strip(),
    }


def _generate(word: str) -> dict:
    """One Claude call → a structured word breakdown (raises on API/parse failure)."""
    native = config.load_config().get("native_language", "English")
    model = config.load_config()["model"]
    client = Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=1300,
        system=[{"type": "text", "text": SYSTEM.format(native=native),
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": word}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError(f"no JSON in word breakdown: {text!r}")
    return _normalize(json.loads(m.group(0)), word)


CHECK_SYSTEM = """\
You help a learner add a German vocabulary item. Given their input (a German word that may \
be misspelled, missing its article, wrongly capitalised, an inflected form, or even written \
in {native}), return the correct German DICTIONARY form and its meaning.

Rules:
- For nouns, ALWAYS include the article (der/die/das) and capitalise the noun.
- Fix spelling and capitalisation; prefer the base/dictionary form.
- Give the meaning in {native}. If the learner supplied a meaning, keep it unless it is wrong.

Respond with ONLY this JSON:
{{"german": "<corrected German, with article for nouns>", "meaning": "<meaning in {native}>", \
"note": "<very short note on what you fixed, in {native}; empty if nothing changed>"}}
"""


def check(text: str, meaning: str = "") -> dict:
    """Cheap AI pass to correct a vocab entry (article, spelling, meaning) before saving."""
    text = _clean(text)
    if not text:
        raise ValueError("empty word")
    cfg = config.load_config()
    native = cfg.get("native_language", "English")
    user = f"Input: {text}"
    if meaning.strip():
        user += f"\nLearner's meaning: {meaning.strip()}"
    resp = Anthropic().messages.create(
        model=cfg["model"],
        max_tokens=200,
        system=[{"type": "text", "text": CHECK_SYSTEM.format(native=native),
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    raw = "".join(b.text for b in resp.content if b.type == "text")
    m = _JSON_RE.search(raw)
    if not m:
        raise ValueError(f"no JSON in check: {raw!r}")
    d = json.loads(m.group(0))
    return {
        "german": str(d.get("german") or text).strip(),
        "meaning": str(d.get("meaning") or "").strip(),
        "note": str(d.get("note") or "").strip(),
    }


def lookup(word: str, *, refresh: bool = False) -> dict:
    """Return the breakdown for `word`, from cache when possible (free), else generate."""
    word = _clean(word)
    if not word:
        raise ValueError("empty word")
    WORDS_DIR.mkdir(parents=True, exist_ok=True)
    path = WORDS_DIR / f"{_slug(word)}.json"
    if path.exists() and not refresh:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _with_links({**data, "cached": True})
    data = _generate(word)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return _with_links({**data, "cached": False})
