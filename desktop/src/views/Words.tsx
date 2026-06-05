import { useEffect, useState } from "react";
import { api, FamilyWord, WordStudy } from "../api";
import { GenderLegend, GermanTerm } from "../gender";

// Deep word study: type any German word → morphology, family, conjugation, examples.
export default function Words({ initialWord }: { initialWord: string | null }) {
  const [query, setQuery] = useState(initialWord ?? "");
  const [data, setData] = useState<WordStudy | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<Record<string, boolean>>({});

  async function run(word: string, refresh = false) {
    const w = word.trim();
    if (!w) return;
    setLoading(true);
    setError(null);
    try {
      setData(await api.lookupWord(w, refresh));
      setAdded({});
    } catch (e) {
      setError(String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  // Auto-look-up when opened from a vocab card.
  useEffect(() => {
    if (initialWord) {
      setQuery(initialWord);
      run(initialWord);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialWord]);

  async function addFamily(f: FamilyWord) {
    try {
      const r = await api.addVocab(f.word, f.meaning);
      setAdded((a) => ({ ...a, [f.word]: r.added }));
    } catch {
      /* ignore — non-critical */
    }
  }

  const c = data?.conjugation;
  const hasConj =
    c && (c.infinitive || c.present_3sg || c.praeteritum_3sg || c.perfect_3sg);

  return (
    <div className="view-main scroll">
      <header className="chat-header">
        Words <span className="header-legend"><GenderLegend /></span>
      </header>
      <div className="panel-body">
        <div className="word-search">
          <input
            value={query}
            autoFocus
            placeholder="Type a German word… (e.g. Versicherung, ankommen, freundlich)"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run(query)}
          />
          <button className="primary" onClick={() => run(query)} disabled={loading}>
            {loading ? "Looking up…" : "🔍 Look up"}
          </button>
        </div>

        {error && <div className="banner error">{error}</div>}
        {loading && !data && <div className="placeholder">Analysing…</div>}

        {data && (
          <div className="word-card">
            <div className="word-head">
              <div>
                <span className={"word-title" + (data.article ? ` g-${data.article.toLowerCase()}` : "")}>
                  {data.article && <span className="word-article">{data.article} </span>}
                  {data.word}
                </span>
                <button
                  className="icon-btn"
                  title="Hear it"
                  onClick={() => api.speak((data.article ? data.article + " " : "") + data.word)}
                >
                  🔊
                </button>
                <span className="pos-badge">{data.pos}</span>
                {data.plural && <span className="muted small"> · pl. {data.plural}</span>}
              </div>
              <button
                className="ghost-btn"
                title="Regenerate (uses one API call)"
                onClick={() => run(data.word, true)}
              >
                ↻ Refresh
              </button>
            </div>
            <p className="word-translation">{data.translation}</p>

            {/* morphology: the ver- + sicher + -ung breakdown */}
            {data.morphemes.length > 0 && (
              <section className="word-section">
                <h4>Word parts</h4>
                <div className="morpheme-row">
                  {data.morphemes.map((m, i) => (
                    <span key={i} className="morpheme" title={m.type}>
                      {m.part}
                    </span>
                  ))}
                </div>
                <ul className="morpheme-list">
                  {data.morphemes.map((m, i) => (
                    <li key={i}>
                      <span className="morpheme-part">{m.part}</span>
                      <span className="muted small"> ({m.type}) </span>— {m.meaning}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* verb conjugation */}
            {hasConj && (
              <section className="word-section">
                <h4>Conjugation</h4>
                <table className="conj-table">
                  <tbody>
                    {c!.infinitive && (
                      <tr><td>Infinitive</td><td>{c!.infinitive}</td></tr>
                    )}
                    {c!.present_3sg && (
                      <tr><td>Present (er/sie/es)</td><td>{c!.present_3sg}</td></tr>
                    )}
                    {c!.praeteritum_3sg && (
                      <tr><td>Präteritum</td><td>{c!.praeteritum_3sg}</td></tr>
                    )}
                    {c!.perfect_3sg && (
                      <tr><td>Perfekt</td><td>{c!.perfect_3sg}</td></tr>
                    )}
                    {c!.participle && (
                      <tr><td>Partizip II</td><td>{c!.participle}</td></tr>
                    )}
                  </tbody>
                </table>
              </section>
            )}

            {/* word family */}
            {data.family.length > 0 && (
              <section className="word-section">
                <h4>Word family</h4>
                <ul className="family-list">
                  {data.family.map((f, i) => (
                    <li key={i}>
                      <button
                        className="link-word"
                        title="Study this word"
                        onClick={() => run(f.word)}
                      >
                        <GermanTerm text={f.word} tintWhole />
                      </button>
                      <span className="pos-badge small">{f.pos}</span>
                      <span className="muted"> — {f.meaning}</span>
                      <button
                        className="add-btn"
                        disabled={added[f.word] !== undefined}
                        onClick={() => addFamily(f)}
                      >
                        {added[f.word] === true
                          ? "✓ added"
                          : added[f.word] === false
                          ? "already saved"
                          : "+ vocab"}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* examples */}
            {data.examples.length > 0 && (
              <section className="word-section">
                <h4>Examples</h4>
                <ul className="example-list">
                  {data.examples.map((e, i) => (
                    <li key={i}>
                      <span className="example-de">{e.de}</span>
                      <button
                        className="icon-btn"
                        title="Hear it"
                        onClick={() => api.speak(e.de)}
                      >
                        🔊
                      </button>
                      <div className="muted small">{e.translation}</div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {data.note && <p className="word-note">💡 {data.note}</p>}

            <div className="word-links">
              <a href={data.linguee_url} target="_blank" rel="noreferrer">
                Open in Linguee ↗
              </a>
              <a href={data.wiktionary_url} target="_blank" rel="noreferrer">
                Wiktionary ↗
              </a>
              <span className="muted small">
                {data.cached ? "from cache (free)" : "freshly generated"}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
