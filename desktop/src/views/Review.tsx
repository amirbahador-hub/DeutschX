import { useEffect, useState } from "react";
import { api, DueCard, GradeResult } from "../api";
import { GermanTerm } from "../gender";

// Spaced-repetition quiz: shown a meaning, type the German; Claude grades + reschedules.
export default function Review({
  topic,
  topicName,
}: {
  topic: string | null;
  topicName: string | null;
}) {
  const [cards, setCards] = useState<DueCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [i, setI] = useState(0);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<GradeResult | null>(null);
  const [reviewed, setReviewed] = useState(0);
  const [correct, setCorrect] = useState(0);

  function load() {
    setCards(null);
    setI(0);
    setAnswer("");
    setResult(null);
    setReviewed(0);
    setCorrect(0);
    api.reviewDue(topic).then(setCards).catch((e) => setError(String(e)));
  }

  useEffect(load, [topic]);

  async function submit() {
    if (!cards || busy || !answer.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.gradeReview(cards[i].german, answer, "en2de");
      setResult(r);
      setReviewed((n) => n + 1);
      if (r.correct) setCorrect((n) => n + 1);
      if (r.correct) api.speak(r.german);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function next() {
    setResult(null);
    setAnswer("");
    setI((n) => n + 1);
  }

  if (error) return <div className="banner error">{error}</div>;
  if (!cards) return <div className="placeholder">Loading review…</div>;
  if (cards.length === 0)
    return (
      <div className="view-main">
        <header className="chat-header">
          Review {topicName && <span className="muted">· {topicName}</span>}
        </header>
        <div className="placeholder">
          🎉 Nothing due {topicName ? `in “${topicName}”` : "right now"} — come back later!
        </div>
      </div>
    );

  const done = i >= cards.length;
  return (
    <div className="view-main">
      <header className="chat-header">
        Review {topicName && <span className="muted">· {topicName}</span>}
        {!done && <span className="muted"> · {i + 1} / {cards.length}</span>}
      </header>
      <div className="panel-body center">
        {done ? (
          <div className="review-summary">
            <div className="big">{correct} / {reviewed}</div>
            <p className="muted">correct this session</p>
            <button className="primary" onClick={load}>
              Review again
            </button>
          </div>
        ) : (
          <div className="quiz-card">
            <p className="quiz-prompt">What is the German for…</p>
            <p className="quiz-meaning">{cards[i].english}</p>

            {result ? (
              <>
                <div className={"quiz-result " + (result.correct ? "ok" : "bad")}>
                  <span className="mark">{result.correct ? "✓" : "✗"}</span>
                  <span className="answer">
                    <GermanTerm text={result.german} tintWhole />
                    <button
                      className="icon-btn"
                      title="Hear it"
                      onClick={() => api.speak(result.german)}
                    >
                      🔊
                    </button>
                  </span>
                </div>
                <p className="feedback">{result.feedback}</p>
                <p className="muted small">Next review in {result.interval} day(s)</p>
                <button className="primary" onClick={next}>
                  {i + 1 < cards.length ? "Next →" : "Finish"}
                </button>
              </>
            ) : (
              <>
                <input
                  className="quiz-input"
                  value={answer}
                  autoFocus
                  onChange={(e) => setAnswer(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && submit()}
                  placeholder="Type the German word (with article)…"
                />
                <button
                  className="primary"
                  onClick={submit}
                  disabled={busy || !answer.trim()}
                >
                  {busy ? "Grading…" : "Check"}
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
