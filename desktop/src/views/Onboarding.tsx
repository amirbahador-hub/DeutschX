import { useEffect, useState } from "react";
import { api } from "../api";

// First-run setup: paste an Anthropic API key, pick your native language + level.
// Everything stays on this machine — the key is saved locally, never uploaded.
export default function Onboarding({ onDone }: { onDone: () => void }) {
  const [key, setKey] = useState("");
  const [native, setNative] = useState("English");
  const [level, setLevel] = useState("A2-B1");
  const [levels, setLevels] = useState<string[]>(["A1", "A2", "A2-B1", "B1", "B1-B2", "B2", "C1"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then((s) => {
      setLevels(s.levels);
      setNative(s.native_language || "English");
      setLevel(s.level || "A2-B1");
    }).catch(() => {});
  }, []);

  async function start() {
    const k = key.trim();
    if (!k || busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.setKey(k);
      if (r.valid === false) {
        setError("That key didn’t work — double-check you copied the whole key.");
        setBusy(false);
        return;
      }
      await api.updateSettings({ native_language: native.trim() || "English", level });
      onDone();
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  }

  return (
    <div className="onboard">
      <div className="onboard-card">
        <img className="onboard-logo" src="/deutschx.png" alt="DeutschX" />
        <h1>Welcome to DeutschX</h1>
        <p className="onboard-sub">
          Your personal AI German tutor. Everything stays on your computer — your lessons and
          this key are saved locally and never uploaded.
        </p>

        <label className="onboard-field">
          <span>Anthropic API key</span>
          <input
            type="password"
            value={key}
            autoFocus
            placeholder="sk-ant-…"
            onChange={(e) => setKey(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && start()}
          />
          <a className="onboard-link" href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">
            Get a key from console.anthropic.com ↗
          </a>
        </label>

        <div className="onboard-row">
          <label className="onboard-field">
            <span>Your native language</span>
            <input
              value={native}
              placeholder="English"
              onChange={(e) => setNative(e.target.value)}
            />
          </label>
          <label className="onboard-field">
            <span>Your German level</span>
            <select value={level} onChange={(e) => setLevel(e.target.value)}>
              {levels.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </label>
        </div>

        {error && <div className="banner error">{error}</div>}

        <button className="onboard-start" onClick={start} disabled={busy || !key.trim()}>
          {busy ? "Checking…" : "Get started"}
        </button>
        <p className="onboard-foot">
          Usage is billed to your own Anthropic account. DeutschX has no servers — it talks to
          Anthropic directly from your machine.
        </p>
      </div>
    </div>
  );
}
