import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { cleanTerm, GermanTerm } from "../gender";

// Paul-Noble-style hands-free drill. Two modes:
//  • Words — hear the English, pause to recall, hear the slow German; loops your deck.
//  • Sentences — a progressive course: each word taught as a building block first, then
//    assembled into sentences that start trivial and grow more complex.
//
// Robustness notes: the drill is a sequence of blocking /api/speak calls. To make Pause and
// mode-switching instant (never hanging on an in-flight utterance), each speak uses an
// AbortController, and every load is tagged with a token so a slow course fetch can't apply
// to a mode the user has since switched away from.
const SLOW_RATE = 130; // wpm for the German answer (clear and slow)

type Kind = "word" | "block" | "sentence";
type Item = { english: string; german: string; kind: Kind };
type Mode = "words" | "sentences";

export default function Listen({
  topic,
  topicName,
}: {
  topic: string | null;
  topicName: string | null;
}) {
  const [mode, setMode] = useState<Mode>("words");
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [idx, setIdx] = useState(0);
  const [running, setRunning] = useState(false);
  const [phase, setPhase] = useState<"en" | "gap" | "de" | null>(null);
  const [loop, setLoop] = useState(true);
  const [gap, setGap] = useState(3);
  const [showText, setShowText] = useState(true);

  // Refs mirror state so the async loop reads fresh values without stale closures.
  const itemsRef = useRef<Item[]>([]);
  const idxRef = useRef(0);
  const runningRef = useRef(false);
  const runIdRef = useRef(0);
  const loadIdRef = useRef(0);
  const loopRef = useRef(true);
  const gapRef = useRef(3);
  const cancelSleep = useRef<(() => void) | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => { loopRef.current = loop; }, [loop]);
  useEffect(() => { gapRef.current = gap; }, [gap]);

  function setIndex(i: number) {
    idxRef.current = i;
    setIdx(i);
  }

  function stop() {
    runningRef.current = false;
    setRunning(false);
    setPhase(null);
    if (cancelSleep.current) cancelSleep.current();
    abortRef.current?.abort();           // cancel any in-flight utterance on the client
    api.stopSpeaking().catch(() => {});  // and cut the audio on the sidecar
  }

  function load(refresh = false) {
    stop();
    const myLoad = ++loadIdRef.current;
    setIndex(0);
    itemsRef.current = [];
    setItems([]);
    setError(null);
    const fresh = () => loadIdRef.current === myLoad;

    if (mode === "words") {
      api
        .listVocab(topic)
        .then((v) => {
          if (!fresh()) return;
          const list: Item[] = v.cards.map((c) => ({
            english: c.english,
            german: cleanTerm(c.german),
            kind: "word",
          }));
          itemsRef.current = list;
          setItems(list);
        })
        .catch((e) => fresh() && setError(String(e)));
    } else {
      setLoading(true);
      api
        .getCourse(topic, topicName, refresh)
        .then((c) => {
          if (!fresh()) return;
          const list: Item[] = c.steps.map((s) => ({
            english: s.en,
            german: cleanTerm(s.de),
            kind: s.type,
          }));
          itemsRef.current = list;
          setItems(list);
        })
        .catch((e) => fresh() && setError(String(e)))
        .finally(() => fresh() && setLoading(false));
    }
  }

  useEffect(() => {
    load();
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topic, mode]);

  function sleep(seconds: number) {
    return new Promise<void>((resolve) => {
      const id = setTimeout(() => {
        cancelSleep.current = null;
        resolve();
      }, seconds * 1000);
      cancelSleep.current = () => {
        clearTimeout(id);
        cancelSleep.current = null;
        resolve();
      };
    });
  }

  async function say(text: string, lang: "en" | "de", rate?: number) {
    if (!runningRef.current) return;
    try {
      await api.speak(text, rate, lang, abortRef.current?.signal);
    } catch {
      /* aborted (pause/switch) or a one-off error — the loop's alive() check handles it */
    }
  }

  async function runLoop(myId: number) {
    const alive = () => runningRef.current && runIdRef.current === myId;
    while (alive() && idxRef.current < itemsRef.current.length) {
      const it = itemsRef.current[idxRef.current];
      const isBlock = it.kind === "block";

      setPhase("en");
      await say(it.english, "en");
      if (!alive()) break;

      setPhase("gap");
      await sleep(isBlock ? 1.5 : gapRef.current); // blocks need less thinking time
      if (!alive()) break;

      setPhase("de");
      await say(it.german, "de", SLOW_RATE);
      if (!alive()) break;
      if (!isBlock) {
        await sleep(0.5);
        if (!alive()) break;
        await say(it.german, "de", SLOW_RATE); // a second, reinforcing pass
        if (!alive()) break;
      }

      let next = idxRef.current + 1;
      if (next >= itemsRef.current.length) {
        if (!loopRef.current) break;
        next = 0;
      }
      setIndex(next);
      await sleep(0.6);
    }
    if (runIdRef.current === myId) {
      runningRef.current = false;
      setRunning(false);
      setPhase(null);
    }
  }

  function start() {
    if (runningRef.current || itemsRef.current.length === 0) return;
    abortRef.current = new AbortController();
    const myId = ++runIdRef.current;
    runningRef.current = true;
    setRunning(true);
    runLoop(myId);
  }

  function restart() {
    stop();
    setIndex(0);
  }

  function switchMode(m: Mode) {
    if (m === mode || loading) return; // ignore while a course is being generated
    stop();
    setMode(m);
  }

  const modeTabs = (
    <div className="mode-tabs">
      <button
        className={mode === "words" ? "active" : ""}
        disabled={loading}
        onClick={() => switchMode("words")}
      >
        Words
      </button>
      <button
        className={mode === "sentences" ? "active" : ""}
        disabled={loading}
        onClick={() => switchMode("sentences")}
      >
        Sentences
      </button>
    </div>
  );

  const header = (
    <header className="chat-header">
      Listen {topicName && <span className="muted">· {topicName}</span>}
      {items.length > 0 && <span className="muted"> · {idx + 1} / {items.length}</span>}
    </header>
  );

  if (error)
    return (
      <div className="view-main">
        {header}
        <div className="panel-body">
          {modeTabs}
          <div className="banner error">{error}</div>
        </div>
      </div>
    );

  if (loading)
    return (
      <div className="view-main">
        {header}
        <div className="panel-body">
          {modeTabs}
          <div className="placeholder">
            Building your progressive sentence course… (one-time, then cached)
          </div>
        </div>
      </div>
    );

  if (items.length === 0)
    return (
      <div className="view-main">
        {header}
        <div className="panel-body">
          {modeTabs}
          <div className="placeholder">
            {mode === "words"
              ? `No words to drill ${topicName ? `in “${topicName}”` : "yet"} — take a lesson first.`
              : "No sentences yet."}
          </div>
        </div>
      </div>
    );

  const cur = items[idx];
  const revealGerman = showText || phase === "de";

  return (
    <div className="view-main">
      {header}
      <div className="panel-body center">
        <div className="listen-card">
          {modeTabs}

          {cur.kind !== "word" && (
            <div className={"kind-badge " + cur.kind}>
              {cur.kind === "block" ? "🧩 building block" : "📝 sentence"}
            </div>
          )}

          <div className={"listen-phase " + (phase ?? "")}>
            {phase === "en" && (cur.kind === "block" ? "🗣️ This word in German…" : "🗣️ Say it in German…")}
            {phase === "gap" && "… your turn …"}
            {phase === "de" && "✅ Answer"}
            {!phase && (running ? "…" : "Press Start and listen along")}
          </div>

          <p className="listen-en">{cur.english}</p>
          <p className="listen-de">
            {revealGerman ? <GermanTerm text={cur.german} tintWhole /> : <span className="muted">···</span>}
            <button
              className="icon-btn"
              title="Hear the German"
              onClick={() => api.speak(cur.german, SLOW_RATE, "de")}
            >
              🔊
            </button>
          </p>

          <div className="listen-controls">
            {running ? (
              <button className="primary big" onClick={stop}>⏸ Pause</button>
            ) : (
              <button className="primary big" onClick={start}>▶ Start</button>
            )}
            <button className="ghost-btn" onClick={restart} title="Back to the first item">
              ⟲ Restart
            </button>
            {mode === "sentences" && (
              <button
                className="ghost-btn"
                onClick={() => load(true)}
                title="Generate a fresh course (uses one API call)"
              >
                ↻ New course
              </button>
            )}
          </div>

          <div className="listen-options">
            <label>
              <input type="checkbox" checked={loop} onChange={(e) => setLoop(e.target.checked)} />
              Loop
            </label>
            <label>
              <input
                type="checkbox"
                checked={showText}
                onChange={(e) => setShowText(e.target.checked)}
              />
              Show German text
            </label>
            <label className="gap-slider">
              Pause: {gap}s
              <input
                type="range"
                min={1}
                max={6}
                step={1}
                value={gap}
                onChange={(e) => setGap(Number(e.target.value))}
              />
            </label>
          </div>
          <p className="muted small listen-hint">
            {mode === "sentences"
              ? "Each new word is taught on its own first, then built into sentences that start simple and get harder. Say the German in the pause, then check yourself."
              : "Hear the English, say the German out loud in the pause, then check against the slow answer. Keep it looping — repetition is the point."}
          </p>
        </div>
      </div>
    </div>
  );
}
