"""Paste-aware line editor, à la the Claude Code CLI.

Uses prompt_toolkit's bracketed-paste support so that pasting multi-line text is
captured as a SINGLE input instead of being executed line by line. A large paste is
shown collapsed as "[Pasted text #1 +44 lines]" so you can still type before and after
it; pressing Enter once submits the whole thing, and the placeholder is expanded back
to the real content on the way out.
"""
from __future__ import annotations

import re

# A paste of at least this many lines is collapsed to a placeholder.
PASTE_MIN_LINES = 4
_PLACEHOLDER_RE = re.compile(r"\[Pasted text #(\d+) \+\d+ lines\]")


def expand(text: str, pastes: dict[int, str]) -> str:
    """Replace any paste placeholders in `text` with their stored content."""
    return _PLACEHOLDER_RE.sub(
        lambda m: pastes.get(int(m.group(1)), m.group(0)), text
    )


class Reader:
    """Reusable prompt-toolkit reader with bracketed-paste collapsing."""

    def __init__(self, *, input=None, output=None):
        self._session = None
        self._kb = None
        self._pastes: dict[int, str] = {}
        self._counter = 0
        self._input = input  # for tests; None = real terminal
        self._output = output

    def _ensure_session(self):
        if self._session is not None:
            return self._session
        from prompt_toolkit import PromptSession
        from prompt_toolkit.input import ansi_escape_sequences as aes
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.keys import Keys

        # Terminals that distinguish Shift+Enter send a CSI-u / modifyOtherKeys code.
        # By default prompt_toolkit collapses those to plain Enter, so remap them to an
        # otherwise-unused key (F24) that we bind to "insert newline" below.
        for seq in ("\x1b[13;2u", "\x1b[27;2;13~"):
            aes.ANSI_SEQUENCES[seq] = Keys.F24

        kb = KeyBindings()

        @kb.add(Keys.BracketedPaste)
        def _(event):
            # Pasted text may use CRLF or bare CR line endings; normalize to LF so
            # line counting and the inserted text are correct (no stray ^M).
            data = event.data.replace("\r\n", "\n").replace("\r", "\n")
            n_lines = data.count("\n") + 1
            if n_lines >= PASTE_MIN_LINES:
                self._counter += 1
                self._pastes[self._counter] = data
                event.current_buffer.insert_text(
                    f"[Pasted text #{self._counter} +{n_lines} lines]"
                )
            else:
                event.current_buffer.insert_text(data)

        # Insert a literal newline (Enter still submits). Multiple bindings so it works
        # across terminals: Shift+Enter (remapped to F24), Option/Alt+Enter, and Ctrl-J.
        def _newline(event):
            event.current_buffer.insert_text("\n")

        kb.add(Keys.F24)(_newline)
        kb.add("escape", "enter")(_newline)  # Option/Alt+Enter (also Esc then Enter)
        kb.add("c-j")(_newline)  # Ctrl-J, and Shift+Enter on terminals that send \n

        self._kb = kb
        self._session = PromptSession(key_bindings=kb,
                                      input=self._input, output=self._output)
        return self._session

    def _completer(self, commands: list[str]):
        """A completer that suggests slash-commands once the input starts with '/'."""
        from prompt_toolkit.completion import Completer, Completion

        cmds = sorted(set(commands))

        class _SlashCompleter(Completer):
            def get_completions(self, document, complete_event):
                text = document.text_before_cursor
                if " " in text or not text.startswith("/"):
                    return  # only complete the leading command token
                for c in cmds:
                    if c.startswith(text) and c != text:
                        yield Completion(c, start_position=-len(text))

        return _SlashCompleter()

    def read(self, message: str, commands: list[str] | None = None) -> str:
        """Prompt for input. `message` may contain ANSI escape codes for color.

        If `commands` is given, typing '/' offers them as Tab-completions.
        Returns the full text with any pasted blocks expanded. Raises EOFError /
        KeyboardInterrupt on Ctrl-D / Ctrl-C, like input().
        """
        self._pastes = {}
        self._counter = 0
        try:
            from prompt_toolkit.formatted_text import ANSI

            session = self._ensure_session()
            kwargs = {}
            if commands:
                kwargs["completer"] = self._completer(commands)
                kwargs["complete_while_typing"] = True
            text = session.prompt(ANSI(message), **kwargs)
        except (EOFError, KeyboardInterrupt):
            raise
        except Exception:
            # Non-interactive / unsupported terminal: fall back to plain input.
            plain = re.sub(r"\x1b\[[0-9;]*m", "", message)
            text = input(plain)
        return expand(text, self._pastes)


# Shared singleton — one editing history/session for the whole app.
reader = Reader()


def read(message: str, commands: list[str] | None = None) -> str:
    return reader.read(message, commands)
