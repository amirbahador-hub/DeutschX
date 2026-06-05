import { useEffect, useState } from "react";
import { api, TopicSummary } from "./api";
import Lessons from "./views/Lessons";
import Vocabulary from "./views/Vocabulary";
import Review from "./views/Review";
import Pronunciation from "./views/Pronunciation";
import Listen from "./views/Listen";
import Words from "./views/Words";
import Settings from "./views/Settings";
import Onboarding from "./views/Onboarding";
import "./App.css";

type View = "lessons" | "vocab" | "review" | "pron" | "listen" | "words" | "settings";

const NAV: { id: View; icon: string; label: string }[] = [
  { id: "lessons", icon: "💬", label: "Lessons" },
  { id: "vocab", icon: "🔤", label: "Vocabulary" },
  { id: "review", icon: "🔁", label: "Review" },
  { id: "pron", icon: "🎤", label: "Speak" },
  { id: "listen", icon: "🎧", label: "Listen" },
  { id: "words", icon: "📖", label: "Words" },
  { id: "settings", icon: "⚙️", label: "Settings" },
];

export default function App() {
  const [view, setView] = useState<View>("lessons");
  const [hasKey, setHasKey] = useState<boolean | null>(null);
  const [apiDown, setApiDown] = useState(false);
  const [topics, setTopics] = useState<TopicSummary[]>([]);
  // The single, global topic selection that every section is scoped to.
  // null = "All topics" (the deck-wide view).
  const [slug, setSlug] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [due, setDue] = useState(0);
  // A word sent to the Words view when "study" is clicked from a vocab card.
  const [studyWord, setStudyWord] = useState<string | null>(null);

  function studyWordFromVocab(word: string) {
    setStudyWord(word);
    setView("words");
  }

  async function refreshTopics() {
    try {
      setTopics(await api.listTopics());
    } catch {
      /* ignore transient errors; the boot poll / banner handle server state */
    }
  }

  function checkHealth() {
    api
      .health()
      .then((h) => setHasKey(h.has_api_key))
      .catch(() => setApiDown(true));
  }

  // Wait for the bundled engine to come up (it takes ~1–2s to boot on first launch).
  async function waitForServer() {
    for (let i = 0; i < 40; i++) {
      try {
        const h = await api.health();
        setApiDown(false);
        setHasKey(h.has_api_key);
        refreshTopics();
        return;
      } catch {
        await new Promise((r) => setTimeout(r, 500));
      }
    }
    setApiDown(true);
  }

  useEffect(() => {
    waitForServer();
  }, []);

  // Keep the Review badge in sync with the current topic scope.
  useEffect(() => {
    api
      .listVocab(slug)
      .then((v) => setDue(v.stats.due))
      .catch(() => {});
  }, [view, slug]);

  const topicName = topics.find((t) => t.slug === slug)?.name ?? null;
  const scopeKey = slug ?? "all";

  // Still booting the engine: show a splash instead of a scary "server down" flash.
  if (!apiDown && hasKey === null) {
    return (
      <div className="splash">
        <img className="splash-logo" src="/deutschx.png" alt="DeutschX" />
        <div className="splash-name">DeutschX</div>
        <div className="splash-sub">Starting up…</div>
      </div>
    );
  }

  // First-run / no-key: block the app behind a setup screen (unless the server is down).
  if (!apiDown && hasKey === false) {
    return (
      <Onboarding
        onDone={() => {
          setHasKey(true);
          checkHealth();
        }}
      />
    );
  }

  return (
    <div className="app">
      <nav className="nav-rail">
        <div className="nav-brand"><img src="/deutschx.png" alt="DeutschX" /></div>
        {NAV.map((n) => (
          <button
            key={n.id}
            className={"nav-item" + (view === n.id ? " active" : "")}
            onClick={() => setView(n.id)}
            title={n.label}
          >
            <span className="nav-icon">{n.icon}</span>
            <span className="nav-label">{n.label}</span>
            {n.id === "review" && due > 0 && <span className="nav-due">{due}</span>}
          </button>
        ))}
      </nav>

      <div className="content">
        {view !== "settings" && (
          <div className="topbar">
            <span className="topbar-label">Topic</span>
            <select
              className="topic-select"
              value={slug ?? ""}
              onChange={(e) => {
                setSlug(e.target.value || null);
                setCreating(false);
              }}
            >
              <option value="">All topics</option>
              {topics.map((t) => (
                <option key={t.slug} value={t.slug}>
                  {t.name}
                  {t.status === "learned" ? " ✓" : ""}
                </option>
              ))}
            </select>
            <button
              className="topbar-new"
              onClick={() => {
                setView("lessons");
                setCreating(true);
              }}
            >
              ＋ New topic
            </button>
            {view !== "lessons" && (
              <span className="topbar-scope">
                {topicName ? `Scoped to “${topicName}”` : "All topics"}
              </span>
            )}
          </div>
        )}

        {apiDown && (
          <div className="banner error">
            Can’t reach the DeutschX server. Start it with{" "}
            <code>python -m deutschx.api</code> and reopen.
          </div>
        )}
        {hasKey === false && (
          <div className="banner warn">
            No ANTHROPIC_API_KEY — add it to your <code>.env</code> so the tutor can reply.
          </div>
        )}

        {view === "lessons" && (
          <Lessons
            slug={slug}
            creating={creating}
            onCreated={(s) => {
              setCreating(false);
              setSlug(s);
              refreshTopics();
            }}
          />
        )}
        {view === "vocab" && (
          <Vocabulary
            key={scopeKey}
            topic={slug}
            topicName={topicName}
            topics={topics}
            onStudy={studyWordFromVocab}
          />
        )}
        {view === "review" && (
          <Review key={scopeKey} topic={slug} topicName={topicName} />
        )}
        {view === "pron" && (
          <Pronunciation key={scopeKey} topic={slug} topicName={topicName} />
        )}
        {view === "listen" && (
          <Listen key={scopeKey} topic={slug} topicName={topicName} />
        )}
        {view === "words" && <Words initialWord={studyWord} />}
        {view === "settings" && <Settings />}
      </div>
    </div>
  );
}
