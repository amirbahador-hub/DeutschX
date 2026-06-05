import { useEffect, useState } from "react";
import { api, TopicSummary, VocabList } from "../api";
import { GenderLegend, GermanTerm } from "../gender";

// Browse the spaced-repetition deck (scoped to the selected topic, or all of it),
// and add your own words to a topic's list.
export default function Vocabulary({
  topic,
  topicName,
  topics,
  onStudy,
}: {
  topic: string | null;
  topicName: string | null;
  topics: TopicSummary[];
  onStudy: (word: string) => void;
}) {
  const [data, setData] = useState<VocabList | null>(null);
  const [error, setError] = useState<string | null>(null);

  // add-word form
  const [adding, setAdding] = useState(false);
  const [german, setGerman] = useState("");
  const [meaning, setMeaning] = useState("");
  const [target, setTarget] = useState<string>(topic ?? "");
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  function load() {
    api.listVocab(topic).then(setData).catch((e) => setError(String(e)));
  }

  useEffect(() => {
    load();
    setTarget(topic ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topic]);

  async function check() {
    const g = german.trim();
    if (!g || checking) return;
    setChecking(true);
    setNote(null);
    try {
      const r = await api.checkVocab(g, meaning.trim());
      setGerman(r.german);
      setMeaning(r.meaning);
      setNote(r.note ? `✓ ${r.note}` : "✓ Looks correct.");
    } catch (e) {
      setNote(String(e));
    } finally {
      setChecking(false);
    }
  }

  async function addWord() {
    const g = german.trim();
    if (!g || busy) return;
    setBusy(true);
    setNote(null);
    try {
      const r = await api.addVocab(g, meaning.trim(), target);
      if (r.added) {
        setNote(`Added “${g}”.`);
        setGerman("");
        setMeaning("");
        load();
      } else {
        setNote(`“${g}” is already in your deck.`);
      }
    } catch (e) {
      setNote(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <div className="banner error">{error}</div>;
  if (!data) return <div className="placeholder">Loading vocabulary…</div>;

  const { stats, cards } = data;
  return (
    <div className="view-main scroll">
      <header className="chat-header">
        Vocabulary {topicName && <span className="muted">· {topicName}</span>}
        <span className="header-legend"><GenderLegend /></span>
      </header>
      <div className="panel-body">
        <div className="stat-row">
          <div className="stat">
            <div className="stat-num">{stats.total}</div>
            <div className="stat-label">total</div>
          </div>
          <div className="stat">
            <div className="stat-num accent">{stats.due}</div>
            <div className="stat-label">due now</div>
          </div>
          <div className="stat">
            <div className="stat-num green">{stats.learned}</div>
            <div className="stat-label">learned</div>
          </div>
        </div>

        {/* add your own word */}
        {adding ? (
          <div className="add-word">
            <div className="add-word-row">
              <input
                className="add-de"
                value={german}
                autoFocus
                placeholder="German word (e.g. der Tisch)"
                onChange={(e) => setGerman(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addWord()}
              />
              <input
                className="add-en"
                value={meaning}
                placeholder="Meaning (e.g. the table)"
                onChange={(e) => setMeaning(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addWord()}
              />
            </div>
            <div className="add-word-row">
              <label className="add-target">
                Topic:
                {topic ? (
                  <span className="add-target-fixed"> {topicName}</span>
                ) : (
                  <select value={target} onChange={(e) => setTarget(e.target.value)}>
                    <option value="">(no topic)</option>
                    {topics.map((t) => (
                      <option key={t.slug} value={t.slug}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                )}
              </label>
              <button
                className="ghost-btn"
                onClick={check}
                disabled={checking || !german.trim()}
                title="Fix the article, spelling and meaning with AI"
              >
                {checking ? "Checking…" : "✓ Check with AI"}
              </button>
              <button className="primary" onClick={addWord} disabled={busy || !german.trim()}>
                {busy ? "Adding…" : "Add word"}
              </button>
              <button className="ghost-btn" onClick={() => { setAdding(false); setNote(null); }}>
                Done
              </button>
              {note && <span className="add-note">{note}</span>}
            </div>
          </div>
        ) : (
          <button className="add-word-toggle" onClick={() => setAdding(true)}>
            ＋ Add word{topicName ? ` to “${topicName}”` : ""}
          </button>
        )}

        {cards.length === 0 ? (
          <div className="empty">
            {topicName
              ? `No words in “${topicName}” yet — add some above, or take a lesson.`
              : "No words yet — add some above, or they’re captured automatically as you take lessons."}
          </div>
        ) : (
          <table className="vocab-table">
            <thead>
              <tr>
                <th></th>
                <th>German</th>
                <th>Meaning</th>
                <th>Topic</th>
                <th>Reps</th>
                <th>Next due</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {cards.map((c) => (
                <tr key={c.german} className={c.is_due ? "due" : ""}>
                  <td>
                    <button
                      className="icon-btn"
                      title={`Hear “${c.german}”`}
                      onClick={() => api.speak(c.german)}
                    >
                      🔊
                    </button>
                  </td>
                  <td className="bold"><GermanTerm text={c.german} tintWhole /></td>
                  <td>{c.english}</td>
                  <td className="muted">{c.topic}</td>
                  <td>{c.reps}</td>
                  <td className={c.is_due ? "accent" : "muted"}>
                    {c.is_due ? "due" : c.due}
                  </td>
                  <td>
                    <button
                      className="study-btn"
                      title="Study this word (parts, family, conjugation)"
                      onClick={() => onStudy(c.german)}
                    >
                      📖 study
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
