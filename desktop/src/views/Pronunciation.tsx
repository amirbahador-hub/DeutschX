import { useEffect, useState } from "react";
import { api, DueCard, PronResult, PronStatus } from "../api";
import { GermanTerm } from "../gender";

const REASONS: Record<string, string> = {
  disabled: "Pronunciation is turned off in Settings.",
  deps: "Speech recognition isn’t installed. Run: pip install faster-whisper sounddevice",
  no_mic: "No microphone was found.",
};

// Mic pronunciation drill: hear the word, record yourself, get AI feedback (Whisper + Claude).
export default function Pronunciation({
  topic,
  topicName,
}: {
  topic: string | null;
  topicName: string | null;
}) {
  const [status, setStatus] = useState<PronStatus | null>(null);
  const [words, setWords] = useState<DueCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [i, setI] = useState(0);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PronResult | null>(null);

  function load() {
    setI(0);
    setResult(null);
    setRecording(false);
    api.pronWords(topic).then(setWords).catch(() => {});
  }

  useEffect(() => {
    api.pronStatus().then(setStatus).catch((e) => setError(String(e)));
    load();
  }, [topic]);

  async function toggleRecord() {
    if (busy || !words[i]) return;
    setError(null);
    if (!recording) {
      try {
        await api.pronStart();
        setRecording(true);
        setResult(null);
      } catch (e) {
        setError(String(e));
      }
    } else {
      setRecording(false);
      setBusy(true);
      try {
        const r = await api.pronStop(words[i].german, words[i].english);
        setResult(r);
      } catch (e) {
        setError(String(e));
      } finally {
        setBusy(false);
      }
    }
  }

  function next() {
    setResult(null);
    setI((n) => n + 1);
  }

  if (error && !status) return <div className="banner error">{error}</div>;
  if (!status) return <div className="placeholder">Loading…</div>;

  if (!status.available)
    return (
      <div className="view-main">
        <header className="chat-header">Pronunciation</header>
        <div className="placeholder">{REASONS[status.reason] ?? "Microphone unavailable."}</div>
      </div>
    );

  if (words.length === 0)
    return (
      <div className="view-main">
        <header className="chat-header">
          Pronunciation {topicName && <span className="muted">· {topicName}</span>}
        </header>
        <div className="placeholder">
          No words to practice {topicName ? `in “${topicName}”` : "yet"} — take a lesson first.
        </div>
      </div>
    );

  const done = i >= words.length;
  return (
    <div className="view-main">
      <header className="chat-header">
        Pronunciation {topicName && <span className="muted">· {topicName}</span>}
        {!done && <span className="muted"> · {i + 1} / {words.length}</span>}
      </header>
      <div className="panel-body center">
        {done ? (
          <div className="review-summary">
            <div className="big">✓</div>
            <p className="muted">Practice complete!</p>
            <button className="primary" onClick={load}>
              Practice again
            </button>
          </div>
        ) : (
          <div className="quiz-card">
            <p className="quiz-prompt">Say this word aloud:</p>
            <p className="quiz-meaning">
              <GermanTerm text={words[i].german} tintWhole />
              <button
                className="icon-btn"
                title="Hear it"
                onClick={() => api.speak(words[i].german)}
              >
                🔊
              </button>
            </p>
            <p className="muted">{words[i].english}</p>

            <button
              className={"record-btn" + (recording ? " recording" : "")}
              onClick={toggleRecord}
              disabled={busy}
            >
              {busy ? "Transcribing…" : recording ? "⏹ Stop & check" : "🎤 Record"}
            </button>

            {error && <div className="banner error">{error}</div>}

            {result && (
              <>
                <div className={"quiz-result " + (result.correct ? "ok" : "bad")}>
                  <span className="mark">{result.correct ? "✓" : "~"}</span>
                  <span className="answer">heard: “{result.heard || "—"}”</span>
                </div>
                <p className="feedback">{result.feedback}</p>
                <button className="primary" onClick={next}>
                  {i + 1 < words.length ? "Next →" : "Finish"}
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
