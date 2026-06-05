import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, Mode, Msg, Vocab } from "../api";
import { GermanTerm } from "../gender";

// The lesson/chat experience. Topic selection is owned by App (the global top bar);
// this view just renders the chat for whatever topic is selected, or the create form.
export default function Lessons({
  slug,
  creating,
  onCreated,
}: {
  slug: string | null;
  creating: boolean;
  onCreated: (slug: string) => void;
}) {
  const [name, setName] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [newInput, setNewInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [vocab, setVocab] = useState<Vocab[]>([]);
  const loadedSlug = useRef<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  async function openTopic(s: string) {
    setError(null);
    try {
      const t = await api.getTopic(s);
      setName(t.name);
      setMessages(t.messages);
      setPending(t.pending);
      setVocab([]);
      loadedSlug.current = s;
    } catch (e) {
      setError(String(e));
    }
  }

  // Load whenever the global selection changes (but not right after we created it,
  // which already populated the chat — see doCreate).
  useEffect(() => {
    if (creating) return;
    if (slug && slug !== loadedSlug.current) openTopic(slug);
  }, [slug, creating]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function doCreate() {
    const text = newInput.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.createTopic(text);
      setNewInput("");
      await openTopic(res.slug);
      if (res.reply) setVocab(res.reply.vocab);
      onCreated(res.slug);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function send(mode: Mode) {
    if (!slug || busy) return;
    const text = input.trim();
    if ((mode === "answer" || mode === "question") && !text) return;
    setError(null);
    if (mode !== "continue") {
      setMessages((m) => [...m, { role: "user", content: text }]);
      setInput("");
    }
    setBusy(true);
    try {
      const r = await api.sendMessage(slug, mode === "continue" ? "" : text, mode);
      setMessages((m) => [...m, { role: "assistant", content: r.shown }]);
      setPending(r.pending);
      setVocab(r.vocab);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send("answer");
    }
  }

  if (creating)
    return (
      <div className="view-main">
        <div className="create">
          <h2>What would you like to learn?</h2>
          <p className="hint">
            A short topic (“Konjunktiv II”) or paste a whole exercise — the tutor will
            name it and start teaching.
          </p>
          <textarea
            value={newInput}
            onChange={(e) => setNewInput(e.target.value)}
            placeholder="z. B. Genitiv üben — oder fügen Sie eine Übung ein…"
            rows={6}
          />
          <button className="primary" onClick={doCreate} disabled={busy || !newInput.trim()}>
            {busy ? "Starting…" : "Start lesson"}
          </button>
          {error && <div className="banner error">{error}</div>}
        </div>
      </div>
    );

  if (!slug)
    return (
      <div className="view-main">
        <div className="placeholder">
          Pick a topic in the top bar, or ＋ New topic to start a lesson.
        </div>
      </div>
    );

  return (
    <div className="view-main">
      <header className="chat-header">{name}</header>
      <div className="messages">
        {messages.map((m, i) => (
          <div key={i} className={"msg " + m.role}>
            {m.role === "assistant" ? (
              <ReactMarkdown>{m.content}</ReactMarkdown>
            ) : (
              <div className="user-text">{m.content}</div>
            )}
          </div>
        ))}
        {busy && <div className="msg assistant thinking">Teacher is thinking…</div>}
        <div ref={endRef} />
      </div>

      {error && <div className="banner error">{error}</div>}

      <div className="composer">
        {vocab.length > 0 && (
          <div className="vocab-bar">
            <span className="vocab-bar-label">🔤 New words:</span>
            {vocab.map((v, i) => (
              <button
                key={i}
                className="vocab-chip"
                title={`Hear “${v.german}”`}
                onClick={() => api.speak(v.german)}
              >
                🔊 <GermanTerm text={v.german} tintWhole />
              </button>
            ))}
          </div>
        )}
        {pending && (
          <button className="next" onClick={() => send("continue")} disabled={busy}>
            Next exercise →
          </button>
        )}
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="Type your answer in German… (Enter to send, Shift+Enter = new line)"
          rows={2}
        />
        <div className="composer-buttons">
          <button className="primary" onClick={() => send("answer")} disabled={busy}>
            Send
          </button>
          <button onClick={() => send("question")} disabled={busy || !input.trim()}>
            ❓ Ask
          </button>
        </div>
      </div>
    </div>
  );
}
