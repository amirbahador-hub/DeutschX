"""Interactive terminal UI for DeutschX."""
from __future__ import annotations

import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from . import config, i18n, memory, srs
from .audio import stt as stt_mod
from .audio import tts as tts_mod
from .exercises import Grader, grade_pronunciation_local
from .i18n import t
from .memory import Topic
from .prompt import read as read_input
from .service import CONTINUE_MSG, NEXT_RE, QUESTION_WRAP, split_next
from .tutor import Tutor, name_topic

console = Console()

# QUESTION_WRAP / CONTINUE_MSG / split_next live in deutschx.service (shared with the API).

# Slash-commands offered as Tab-completions at the lesson prompt.
LESSON_COMMANDS = [
    "/question", "/read", "/repeat", "/slow", "/speak", "/say", "/translate",
    "/auto", "/focus", "/next", "/done", "/menu", "/mute", "/unmute",
]


def _cue(label: str, color: str = "32") -> str:
    """Build a colored ANSI prompt cue (e.g. a bold green 'You: ')."""
    return f"\x1b[1;{color}m{label}\x1b[0m: "


def _focus_clear(subtitle: str = "") -> None:
    """Clear the screen for a distraction-free view, with an optional slim header."""
    console.clear()
    if subtitle:
        console.print(f"[dim]📖 {subtitle}[/]\n")


def _focus_pause() -> None:
    """Wait for Enter so feedback is read before the next screen-clear."""
    try:
        Prompt.ask(f"[dim]{t('continue_enter')}[/]", default="")
    except (EOFError, KeyboardInterrupt):
        pass


def _report_api_error(exc: Exception) -> None:
    """Print a friendly message, calling out an invalid API key specifically."""
    msg = str(exc).lower()
    if "authentication" in msg or "401" in msg or "invalid x-api-key" in msg:
        console.print(f"[red]{t('auth_error')}[/]")
    else:
        console.print(f"[red]{t('reply_error')}[/] {exc}")


def session_help() -> str:
    return (
        f"[dim]{t('you')}: type your answer + Enter • empty Enter = next exercise (clears page)\n"
        "Shift/Alt+Enter or Ctrl-J = newline • multi-line paste = one message • /done • /menu\n"
        "❓ /question <q> = ask without moving on • 🔊 /read = hear current item • /slow\n"
        "🎤 /speak • /say <text> • 🌐 /translate (/t) • /auto • /focus[/]"
    )


def check_api_key() -> bool:
    if config.api_key():
        return True
    console.print(
        Panel(
            "[red]ANTHROPIC_API_KEY is not set.[/]\n\n"
            "1. Copy [bold].env.example[/] to [bold].env[/]\n"
            "2. Add your key from https://console.anthropic.com/\n"
            "3. Restart DeutschX.",
            title="No API key",
            border_style="red",
        )
    )
    return False


def show_topics() -> list[dict]:
    topics = memory.list_topics()
    if not topics:
        console.print(f"[dim]{t('no_topics')}[/]")
        return topics
    table = Table(title=t("topics_title"), show_lines=False)
    table.add_column("#", style="cyan", justify="right")
    table.add_column(t("col_topic"), style="bold")
    table.add_column(t("col_status"))
    table.add_column(t("col_turns"), justify="right")
    table.add_column(t("col_last"))
    for i, top in enumerate(topics, 1):
        if top["status"] == "active":
            status = f"[green]{t('status_active')}[/]"
        else:
            status = f"[blue]{t('status_learned')}[/]"
        last = top.get("last_studied", "")[:10]
        table.add_row(str(i), top["name"], status, str(top.get("turns", 0)), last)
    console.print(table)
    return topics


# --- a lesson session --------------------------------------------------------
def run_session(topic: Topic, *, is_new: bool, initial_message: str | None = None) -> None:
    """Run an interactive teaching loop for one topic until the user exits.

    `initial_message` is the learner's first request to the tutor for a brand-new
    topic (e.g. a pasted exercise). When omitted, a generic opening line is used.
    """
    tutor = Tutor(topic)
    cfg = config.load_config()
    tts = tts_mod.get_tts(cfg)
    voice = _VoiceState(tts, enabled=cfg.get("tts_enabled", True) and tts.available())
    deck = srs.Deck.load()
    pron = {"stt": None, "grader": None}  # built lazily on first /speak
    state = {"auto_translate": cfg.get("auto_translate", False),
             "focus": cfg.get("focus_mode", False),
             "pending_next": None,  # stashed next exercise, revealed on Enter
             "current_view": None}  # what's on screen now (for /read, /translate, /question)

    console.print()
    console.print(Panel(t("topic_label", name=topic.name), border_style="cyan"))
    console.print(session_help())
    if not voice.enabled and cfg.get("tts_enabled", True):
        console.print(f"[dim]{t('no_tts')}[/]")
    console.print()

    if is_new or not topic.messages:
        tutor.add_user(initial_message or tutor.opening_line())
        _assistant_turn(tutor, voice, deck, state, hold_next=False)
    else:
        console.print(f"[dim]{t('welcome_back')}[/]\n")
        last = tutor.last_assistant_text()
        if last:
            shown, _ = _split_next(last)
            state["current_view"] = shown
            console.print(Markdown(shown))
            voice.remember(tts_mod.extract_vocab(shown))
            console.print()

    while True:
        try:
            user_input = read_input(_cue(t("you")), commands=LESSON_COMMANDS).strip()
        except (EOFError, KeyboardInterrupt):
            console.print(f"\n[dim]{t('session_paused')}[/]")
            break

        cmd = user_input.lower()
        # Empty Enter (or "next"/"weiter") = "I'm done here — go to the next exercise".
        # Reveals the stashed next exercise on a clean page (no extra API call).
        if user_input == "" or cmd in ("/next", "next", "/weiter", "weiter"):
            _advance(tutor, voice, deck, state)
            continue

        if cmd in ("/menu", "/exit", "/quit"):
            break
        if cmd == "/done":
            topic.status = "learned"
            topic.save()
            console.print(f"[blue]{t('marked_learned', name=topic.name)}[/]")
            break
        if cmd in ("/read", "/repeat", "/hören", "/hoeren", "/wiederholen"):
            _read_last(tutor, voice, state)
            continue
        if cmd in ("/slow", "/langsam"):
            _read_last(tutor, voice, state, rate=110)  # ~35% slower
            continue
        if cmd in ("/speak", "/aussprache"):
            _lesson_speak(voice, cfg, pron)
            continue
        if cmd in ("/translate", "/t", "/übersetzen"):
            _translate_last(tutor, state)
            continue
        if cmd in ("/auto", "/autotranslate"):
            state["auto_translate"] = not state["auto_translate"]
            key = "auto_on" if state["auto_translate"] else "auto_off"
            console.print(f"[dim]{t(key, lang=tutor.native_language)}[/]")
            continue
        if cmd == "/focus":
            state["focus"] = not state["focus"]
            console.print(f"[dim]{t('focus_on') if state['focus'] else t('focus_off')}[/]")
            continue
        parts = user_input.split(maxsplit=1)
        if parts[0].lower() in ("/question", "/q", "/frage", "/ask"):
            question = parts[1].strip() if len(parts) > 1 else ""
            if not question:
                console.print(f"[dim]{t('question_usage')}[/]")
                continue
            tutor.add_user(QUESTION_WRAP.format(q=question))
            # Keep the current exercise as the /read & /translate target, and don't clear.
            _assistant_turn(tutor, voice, deck, state,
                            hold_next=False, update_view=False, clear=False)
            continue
        if _handle_voice_command(user_input, voice):
            continue

        # A normal answer to the current exercise → feedback now, next exercise stashed.
        tutor.add_user(user_input)
        _assistant_turn(tutor, voice, deck, state, hold_next=True)

    topic.save()
    memory.log_session(topic.slug, len([m for m in topic.messages if m["role"] == "user"]))
    console.print(f"[dim]{t('progress_saved')}[/]\n")


class _VoiceState:
    """Per-session speech state: backend, on/off, and the last new words."""

    def __init__(self, backend: tts_mod.TTSBackend, *, enabled: bool):
        self.backend = backend
        self.enabled = enabled
        self.last_vocab: list[tts_mod.Vocab] = []

    def remember(self, vocab: list[tts_mod.Vocab]) -> None:
        if vocab:
            self.last_vocab = vocab

    def speak_vocab(self, vocab: list[tts_mod.Vocab], *, rate: int | None = None) -> None:
        if not vocab:
            return
        # Show each new word WITH its meaning, e.g. "der Anwalt — lawyer".
        words = " · ".join(f"{v.german} — {v.english}" if v.english else v.german
                           for v in vocab)
        console.print(f"[dim]{t('new_words', words=words)}[/]")
        if self.enabled:
            for v in vocab:
                self.backend.speak(v.spoken, rate=rate)


def _read_last(tutor: Tutor, voice: _VoiceState, state: dict,
               *, rate: int | None = None) -> None:
    """Read the German from what's currently on screen, with translations."""
    view = state.get("current_view") or tutor.last_assistant_text()
    if not view:
        console.print(f"[dim]{t('no_german')}[/]")
        return
    try:
        with console.status(t("reading")):
            items = tutor.extract_readables(view)
    except Exception as exc:
        _report_api_error(exc)
        return
    if not items:
        console.print(f"[dim]{t('no_german')}[/]")
        return
    for it in items:
        line = f"🗣️  [bold]{it['de']}[/]"
        if it["meaning"]:
            line += f"\n    [dim]→ {it['meaning']}[/]"
        console.print(line)
        if voice.enabled:
            voice.backend.speak(it["de"], rate=rate)


def _handle_voice_command(text: str, voice: _VoiceState) -> bool:
    """Handle /say, /mute, /unmute. Returns True if handled."""
    low = text.lower()
    if low.startswith("/say"):
        phrase = text[4:].strip()
        if phrase:
            voice.backend.speak(phrase)
        else:
            console.print(f"[dim]{t('say_usage')}[/]")
        return True
    if low == "/mute":
        voice.enabled = False
        console.print(f"[dim]{t('muted')}[/]")
        return True
    if low == "/unmute":
        voice.enabled = voice.backend.available()
        console.print(f"[dim]{t('unmuted') if voice.enabled else t('no_voice')}[/]")
        return True
    return False


def _translate_last(tutor: Tutor, state: dict) -> None:
    """Translate what's currently on screen into the native language."""
    view = state.get("current_view") or tutor.last_assistant_text()
    if not view:
        console.print(f"[dim]{t('no_new_words')}[/]")
        return
    try:
        translation = tutor.translate(view)
    except Exception as exc:
        _report_api_error(exc)
        return
    console.print(Panel(Markdown(translation),
                        title=f"🌐 {t('translation')} ({tutor.native_language})",
                        border_style="blue"))


def _lesson_speak(voice: _VoiceState, cfg: dict, pron: dict) -> None:
    """Practice pronouncing the most recent new words from within a lesson."""
    if not voice.last_vocab:
        console.print(f"[dim]{t('no_practice_words')}[/]")
        return
    if pron["stt"] is None:
        stt, reason = _make_stt(cfg)
        if stt is None:
            console.print(f"[yellow]{reason}[/]")
            return
        pron["stt"], pron["grader"] = stt, Grader()
    for v in voice.last_vocab:
        try:
            _practice_word(v.german, v.english, voice.backend, pron["stt"],
                           pron["grader"], speak=voice.enabled)
        except (EOFError, KeyboardInterrupt):
            console.print(f"\n[dim]{t('pron_ended')}[/]")
            break


_NEXT_RE = NEXT_RE  # shared with deutschx.service
_split_next = split_next


def _generate(tutor: Tutor) -> tuple[str, bool]:
    """Get a full reply while showing a 'thinking' spinner (no rendering yet)."""
    text = ""
    try:
        with console.status(t("thinking"), spinner="dots"):
            def on_text(tok: str) -> None:
                nonlocal text
                text += tok
            reply = tutor.stream_reply(on_text)
        if not text:
            text = reply
    except Exception as exc:  # network/API errors shouldn't crash the session
        _report_api_error(exc)
        return "", False
    return text, True


def _show(text: str, voice: _VoiceState, deck: srs.Deck, tutor: Tutor, state: dict,
          *, update_view: bool = True) -> None:
    """Render a piece of tutor text: Markdown, optional translation, vocab + audio."""
    text = _NEXT_RE.sub("", text).strip()
    if update_view:
        state["current_view"] = text
    console.print(f"[bold cyan]{t('teacher')}[/]:")
    console.print(Markdown(text))
    console.print()

    if state.get("auto_translate"):
        try:
            console.print(Panel(Markdown(tutor.translate(text)),
                                title=f"🌐 {t('translation')} ({tutor.native_language})",
                                border_style="blue"))
        except Exception:
            pass  # translation is a nicety; never break the lesson over it

    vocab = tts_mod.extract_vocab(text)
    voice.remember(vocab)
    voice.speak_vocab(vocab)
    added = sum(deck.add(v.german, v.english, topic=tutor.topic.slug) for v in vocab)
    if added:
        deck.save()
        console.print(f"[dim]{t('vocab_saved', n=added)}[/]")


def _assistant_turn(tutor: Tutor, voice: _VoiceState, deck: srs.Deck, state: dict,
                    *, hold_next: bool = False, update_view: bool = True,
                    clear: bool = True) -> None:
    """Generate a reply, store it, and show it.

    When `hold_next` is set (i.e. this is feedback on an answer), the part after the
    [[NEXT]] marker — the next exercise — is stashed and revealed only when the learner
    presses Enter, so they get to review/ask about the answer first. `clear=False` keeps
    the current screen (used for /question so the answer appears below the exercise).
    """
    if clear and state.get("focus"):
        _focus_clear(tutor.topic.name)
    reply, ok = _generate(tutor)
    if not ok:
        return
    tutor.add_assistant(reply)  # store the full reply (with marker) for model context
    tutor.topic.save()

    before, after = _split_next(reply)
    if hold_next and after:
        state["pending_next"] = after
        _show(before, voice, deck, tutor, state, update_view=update_view)
    else:
        state["pending_next"] = None
        combined = before if not after else f"{before}\n\n{after}".strip()
        _show(combined, voice, deck, tutor, state, update_view=update_view)


def _advance(tutor: Tutor, voice: _VoiceState, deck: srs.Deck, state: dict) -> None:
    """Learner is ready for the next item: clear the page and reveal it.

    If the next exercise was already produced (and stashed), just show it — no API call.
    Otherwise ask the tutor to continue.
    """
    _focus_clear(tutor.topic.name)
    pending = state.get("pending_next")
    if pending:
        state["pending_next"] = None
        _show(pending, voice, deck, tutor, state)
    else:
        tutor.add_user(CONTINUE_MSG)
        _assistant_turn(tutor, voice, deck, state, hold_next=False)


# --- review ------------------------------------------------------------------
def run_review() -> None:
    """Quiz the learner on all due vocabulary and reschedule each card via SM-2."""
    deck = srs.Deck.load()
    due = deck.due()
    if not due:
        if deck.stats()["total"] == 0:
            console.print(f"[dim]{t('no_vocab')}[/]")
        else:
            console.print(f"[green]{t('all_reviewed')}[/]")
        return

    cfg = config.load_config()
    tts = tts_mod.get_tts(cfg)
    speak = cfg.get("tts_enabled", True) and tts.available()
    focus = cfg.get("focus_mode", False)
    grader = Grader()

    console.print()
    console.print(Panel(t("review_title", n=len(due)), border_style="magenta"))
    console.print(f"[dim]{t('review_help')}[/]\n")

    reviewed = correct = 0
    for i, card in enumerate(due, 1):
        if focus:
            _focus_clear(f"{t('m_review')}  ·  {i}/{len(due)}")
        console.print(f"[magenta]{i}/{len(due)}[/] " + t("review_q", meaning=card.english))
        try:
            answer = read_input(_cue(t("you")), commands=["/skip", "/stop"]).strip()
        except (EOFError, KeyboardInterrupt):
            console.print(f"\n[dim]{t('session_paused')}[/]")
            break

        if answer.lower() == "/stop":
            break
        if answer.lower() == "/skip":
            console.print(f"[dim]{t('answer_was', german=card.german)}[/]\n")
            continue

        result = grader.grade(card, answer, direction="en2de")
        mark = "[green]✓[/]" if result["correct"] else "[red]✗[/]"
        console.print(f"{mark} [bold]{card.german}[/] — {result['feedback']}")
        if speak:
            tts.speak(card.german)

        srs.schedule(card, result["quality"])
        deck.save()
        reviewed += 1
        correct += int(result["correct"])
        console.print(f"[dim]{t('next_in', n=card.interval)}[/]")
        if focus and i < len(due):
            _focus_pause()
        else:
            console.print()

    if reviewed:
        console.print(Panel(t("review_done", correct=correct, total=reviewed),
                            border_style="magenta"))


# --- pronunciation -----------------------------------------------------------
def _practice_word(german: str, english: str, tts, stt, grader, *, speak: bool) -> bool:
    """One pronunciation attempt. Returns True if it counted as correct, else False."""
    console.print(t("repeat_after", german=german, meaning=english))
    # Let the learner hear the word as many times as they want before speaking.
    while True:
        if speak:
            tts.speak(german)
        choice = Prompt.ask(f"[dim]{t('pron_choose')}[/]", default="").strip().lower()
        if choice in ("r", "repeat") and speak:
            continue  # hear it again
        if choice in ("s", "skip"):
            console.print(f"[dim]{t('skipped')}[/]\n")
            return False
        break
    heard = stt.listen(prompt=t("speak_now"))
    if not heard:
        console.print(f"[dim]{t('nothing_heard')}[/]\n")
        return False
    console.print(f"[dim]{t('heard', text=heard)}[/]")
    if config.load_config().get("pron_ai_feedback"):
        result = grader.grade_pronunciation(srs.Card(german=german, english=english), heard)
    else:
        result = grade_pronunciation_local(german, heard)
    mark = "[green]✓[/]" if result["correct"] else "[yellow]~[/]"
    console.print(f"{mark} {result['feedback']}")
    if speak:
        tts.speak(german)  # replay the correct pronunciation
    console.print()
    return bool(result["correct"])


def _make_stt(cfg: dict):
    """Build the STT backend, or return (None, reason) if unavailable."""
    if not cfg.get("stt_enabled", True):
        return None, t("pron_disabled")
    if not stt_mod.STT.deps_installed():
        return None, t("pron_no_deps")
    stt = stt_mod.get_stt(cfg)
    if not stt.available():
        return None, t("pron_no_mic")
    return stt, None


def run_pronunciation() -> None:
    """Pronunciation drill over due/recent vocabulary using the microphone."""
    cfg = config.load_config()
    stt, reason = _make_stt(cfg)
    if stt is None:
        console.print(f"[yellow]{reason}[/]")
        return

    deck = srs.Deck.load()
    if not deck.cards:
        console.print(f"[dim]{t('no_vocab')}[/]")
        return
    cards = deck.due() or sorted(deck.cards.values(), key=lambda c: c.added_at, reverse=True)
    cards = cards[:8]

    tts = tts_mod.get_tts(cfg)
    speak = cfg.get("tts_enabled", True) and tts.available()
    focus = cfg.get("focus_mode", False)
    grader = Grader()

    console.print()
    console.print(Panel(t("pron_title", n=len(cards)), border_style="yellow"))
    console.print(f"[dim]{t('pron_help')}[/]\n")

    good = 0
    try:
        for i, card in enumerate(cards, 1):
            if focus:
                _focus_clear(f"{t('m_pron')}  ·  {i}/{len(cards)}")
            console.print(f"[yellow]{i}/{len(cards)}[/]")
            good += _practice_word(card.german, card.english, tts, stt, grader, speak=speak)
            if focus and i < len(cards):
                _focus_pause()
    except (EOFError, KeyboardInterrupt):
        console.print(f"\n[dim]{t('pron_ended')}[/]")
    console.print(Panel(t("pron_done", n=good), border_style="yellow"))


# --- settings & onboarding ---------------------------------------------------
def _choose_ui_language(default: str) -> str:
    console.print(f"[bold]{t('pick_ui')}[/]  [cyan]1[/] English   [cyan]2[/] Deutsch")
    sel = Prompt.ask(t("choose"), choices=["1", "2"], default=("1" if default == "en" else "2"))
    return "en" if sel == "1" else "de"


def _choose_level(default: str) -> str:
    levels = config.LEVELS
    line = "  ".join(f"[cyan]{i}[/] {lv}" for i, lv in enumerate(levels, 1))
    console.print(f"[bold]{t('pick_level')}[/]  {line}")
    default_idx = str(levels.index(default) + 1) if default in levels else "3"
    sel = Prompt.ask(t("choose"), choices=[str(i) for i in range(1, len(levels) + 1)],
                     default=default_idx)
    return levels[int(sel) - 1]


def run_settings() -> None:
    cfg = config.load_config()
    while True:
        console.print()
        console.print(Panel(t("settings_title"), border_style="cyan"))
        auto = t("on") if cfg.get("auto_translate") else t("off")
        focus = t("on") if cfg.get("focus_mode", False) else t("off")
        console.print(
            f"[cyan]1[/] {t('set_ui')}: [bold]{i18n.UI_LANGUAGES.get(cfg['ui_language'])}[/]\n"
            f"[cyan]2[/] {t('set_native')}: [bold]{cfg['native_language']}[/]\n"
            f"[cyan]3[/] {t('set_level')}: [bold]{cfg['level']}[/]\n"
            f"[cyan]4[/] {t('set_voice')}: [bold]{cfg['voice']}[/]\n"
            f"[cyan]5[/] {t('set_autotrans')}: [bold]{auto}[/]\n"
            f"[cyan]6[/] {t('set_focus')}: [bold]{focus}[/]\n"
            f"[cyan]7[/] {t('back')}"
        )
        choice = Prompt.ask(t("choose"), choices=["1", "2", "3", "4", "5", "6", "7"],
                            default="7")

        if choice == "1":
            cfg["ui_language"] = _choose_ui_language(cfg["ui_language"])
            i18n.set_language(cfg["ui_language"])
        elif choice == "2":
            cfg["native_language"] = Prompt.ask(t("set_native"),
                                                default=cfg["native_language"]).strip()
        elif choice == "3":
            cfg["level"] = _choose_level(cfg["level"])
        elif choice == "4":
            cfg["voice"] = Prompt.ask(t("set_voice"), default=cfg["voice"]).strip()
        elif choice == "5":
            cfg["auto_translate"] = not cfg.get("auto_translate", False)
        elif choice == "6":
            cfg["focus_mode"] = not cfg.get("focus_mode", False)
        else:
            config.save_config(cfg)
            console.print(f"[dim]{t('set_saved')}[/]")
            return
        config.save_config(cfg)


def run_onboarding(cfg: dict) -> dict:
    """First-run setup: ask interface language, native language, and level."""
    console.print(Panel("Welcome to DeutschX! / Willkommen bei DeutschX!",
                        border_style="green"))
    cfg["ui_language"] = _choose_ui_language(cfg.get("ui_language", "en"))
    i18n.set_language(cfg["ui_language"])
    console.print(f"\n[bold]{t('welcome')}[/]")
    cfg["native_language"] = Prompt.ask(t("pick_native"),
                                        default=cfg.get("native_language", "English")).strip()
    cfg["level"] = _choose_level(cfg.get("level", "A2-B1"))
    config.save_config(cfg)
    console.print(f"[green]{t('setup_done')}[/]")
    return cfg


# --- main menu ---------------------------------------------------------------
def main_menu() -> None:
    while True:
        due_count = srs.Deck.load().stats()["due"]
        due_label = f"  [magenta]({due_count} {t('due')})[/]" if due_count else ""
        console.print()
        console.print(
            f"[bold]{t('menu')}:[/] "
            f"[cyan]1[/] {t('m_new')}  "
            f"[cyan]2[/] {t('m_resume')}  "
            f"[cyan]3[/] {t('m_review')}{due_label}  "
            f"[cyan]4[/] {t('m_pron')}  "
            f"[cyan]5[/] {t('m_topics')}  "
            f"[cyan]6[/] {t('m_settings')}  "
            f"[cyan]7[/] {t('m_quit')}"
        )
        choice = Prompt.ask(t("choose"), choices=[str(i) for i in range(1, 8)], default="1")

        if choice == "1":
            console.print(f"[dim]{t('back_hint')}[/]")
            try:
                name = read_input(_cue(t("ask_topic"), "36"), commands=["/back"]).strip()
            except (EOFError, KeyboardInterrupt):
                name = ""
            if not name or name.lower() in ("/back", "/menu"):
                console.print(f"[dim]{t('back_to_menu')}[/]")
                continue
            topic_name, initial = _resolve_topic(name)
            topic, created = memory.get_or_create(topic_name)
            if not created:
                console.print(f"[dim]{t('topic_exists')}[/]")
                initial = None  # resuming an existing topic — don't re-seed
            run_session(topic, is_new=created, initial_message=initial)
        elif choice == "2":
            topics = show_topics()
            if not any(top["status"] == "active" for top in topics):
                console.print(f"[dim]{t('no_active')}[/]")
                continue
            console.print(f"[dim]{t('back_hint')}[/]")
            try:
                sel = read_input(_cue(t("which_resume"), "36"), commands=["/back"]).strip()
            except (EOFError, KeyboardInterrupt):
                sel = ""
            if not sel or sel.lower() in ("/back", "/menu"):
                console.print(f"[dim]{t('back_to_menu')}[/]")
                continue
            topic = _pick(topics, sel)
            if topic:
                run_session(topic, is_new=False)
        elif choice == "3":
            run_review()
        elif choice == "4":
            run_pronunciation()
        elif choice == "5":
            show_topics()
        elif choice == "6":
            run_settings()
        elif choice == "7":
            console.print(f"[cyan]{t('bye')}[/]")
            return


def _resolve_topic(raw: str) -> tuple[str, str | None]:
    """Turn the learner's input into (topic_name, initial_message).

    A short, clean input is used directly as the name. A long or multi-line input
    (e.g. a pasted exercise) gets an AI-generated concise name, and the full text
    becomes the first message sent to the tutor.
    """
    detailed = ("\n" in raw) or (len(raw) > 60)
    if not detailed:
        return raw, None
    with console.status(t("naming")):
        name = name_topic(raw)
    console.print(f"[dim]{t('named', name=name)}[/]")
    return name, raw


def _pick(topics: list[dict], selection: str) -> Topic | None:
    if not selection.isdigit():
        console.print(f"[red]{t('enter_number')}[/]")
        return None
    idx = int(selection) - 1
    if not (0 <= idx < len(topics)):
        console.print(f"[red]{t('invalid_number')}[/]")
        return None
    return Topic.load(topics[idx]["slug"])


def main() -> None:
    config.ensure_dirs()
    config.ensure_api_key()  # honour a key saved in settings (not just the env/.env)
    first_run = not config.CONFIG_FILE.exists()
    cfg = config.load_config()
    i18n.set_language(cfg.get("ui_language", "en"))

    console.print(Panel(f"[bold cyan]DeutschX[/] — {t('subtitle')} 🇩🇪", border_style="cyan"))
    if not check_api_key():
        sys.exit(1)
    if first_run:
        run_onboarding(cfg)
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print(f"\n[cyan]{t('bye')}[/]")


if __name__ == "__main__":
    main()
