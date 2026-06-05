"""Speech-to-text for pronunciation practice.

Records from the microphone with sounddevice and transcribes locally with
faster-whisper (German) — free, offline, no extra API key. Heavy dependencies are
imported lazily so the rest of DeutschX still runs if they aren't installed.
"""
from __future__ import annotations

SAMPLE_RATE = 16000  # what Whisper expects


class STT:
    """Microphone capture + local Whisper transcription. The model is loaded once."""

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._model = None  # lazily loaded WhisperModel

    # --- availability -------------------------------------------------------
    @staticmethod
    def deps_installed() -> bool:
        try:
            import faster_whisper  # noqa: F401
            import sounddevice  # noqa: F401
            return True
        except Exception:
            return False

    def available(self) -> bool:
        if not self.deps_installed():
            return False
        try:
            import sounddevice as sd
            return any(d["max_input_channels"] > 0 for d in sd.query_devices())
        except Exception:
            return False

    # --- model --------------------------------------------------------------
    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            # int8 on CPU is fast and accurate enough for single words/phrases.
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    # --- recording ----------------------------------------------------------
    def record_until_enter(self, prompt: str = "🎤 Sprich jetzt … (Enter zum Stoppen)"):
        """Record from the mic until the user presses Enter. Returns a float32 array."""
        import numpy as np
        import sounddevice as sd

        frames: list = []

        def callback(indata, _frames, _time, _status):
            frames.append(indata.copy())

        print(prompt, flush=True)
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                            dtype="float32", callback=callback):
            try:
                input()  # blocks here while audio accumulates in the callback
            except (EOFError, KeyboardInterrupt):
                pass

        if not frames:
            return np.zeros(0, dtype="float32")
        return np.concatenate(frames, axis=0).flatten()

    # --- transcription ------------------------------------------------------
    def transcribe(self, audio) -> str:
        """Transcribe a float32 audio array as German. Empty string if nothing heard."""
        import numpy as np

        if audio is None or len(audio) < SAMPLE_RATE // 4:  # < ~0.25s = nothing useful
            return ""
        model = self._ensure_model()
        segments, _info = model.transcribe(
            np.asarray(audio, dtype="float32"), language="de", beam_size=5
        )
        return " ".join(s.text for s in segments).strip()

    def listen(self, prompt: str | None = None) -> str:
        """Record until Enter, then transcribe. Convenience wrapper."""
        audio = (self.record_until_enter(prompt) if prompt is not None
                 else self.record_until_enter())
        return self.transcribe(audio)


class Recorder:
    """Start/stop microphone capture for GUI frontends (no stdin involved).

    The CLI's `record_until_enter` blocks on `input()`, which a server can't do.
    Here `start()` opens a background InputStream that accumulates frames, and
    `stop()` closes it and returns the captured float32 audio. One recording at a
    time — `start()` on an already-running recorder restarts it.
    """

    def __init__(self):
        self._stream = None
        self._frames: list = []

    @property
    def active(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        import sounddevice as sd

        self.stop()  # drop any prior recording first
        self._frames = []

        def callback(indata, _frames, _time, _status):
            self._frames.append(indata.copy())

        self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                      dtype="float32", callback=callback)
        self._stream.start()

    def stop(self):
        """Close the stream and return the captured audio (empty array if none)."""
        import numpy as np

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        if not self._frames:
            return np.zeros(0, dtype="float32")
        audio = np.concatenate(self._frames, axis=0).flatten()
        self._frames = []
        return audio


def get_stt(cfg: dict) -> STT:
    return STT(model_size=cfg.get("stt_model", "base"))
