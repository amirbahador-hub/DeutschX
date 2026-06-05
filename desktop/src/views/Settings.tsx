import { useEffect, useState } from "react";
import { api, Settings as SettingsT } from "../api";

// Edit the same config the CLI uses (data/config.json) — shared across frontends.
export default function Settings() {
  const [cfg, setCfg] = useState<SettingsT | null>(null);
  const [voices, setVoices] = useState<string[]>([]);
  const [voicesEn, setVoicesEn] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [keyNote, setKeyNote] = useState<string | null>(null);
  const [keyBusy, setKeyBusy] = useState(false);

  async function saveKey() {
    const k = apiKey.trim();
    if (!k || keyBusy) return;
    setKeyBusy(true);
    setKeyNote(null);
    try {
      const r = await api.setKey(k);
      if (r.valid === false) {
        setKeyNote("That key didn’t work — check it’s copied in full.");
      } else {
        setApiKey("");
        setKeyNote("Saved ✓");
        const s = await api.getSettings();
        setCfg(s);
      }
    } catch (e) {
      setKeyNote(String(e));
    } finally {
      setKeyBusy(false);
    }
  }

  useEffect(() => {
    api.getSettings().then(setCfg).catch((e) => setError(String(e)));
    api.listVoices("de").then(setVoices).catch(() => {});
    api.listVoices("en").then(setVoicesEn).catch(() => {});
  }, []);

  function set<K extends keyof SettingsT>(key: K, value: SettingsT[K]) {
    setCfg((c) => (c ? { ...c, [key]: value } : c));
    setSaved(false);
  }

  async function save() {
    if (!cfg || busy) return;
    setBusy(true);
    setError(null);
    try {
      const { levels, ...patch } = cfg;
      void levels;
      const updated = await api.updateSettings(patch);
      setCfg(updated);
      setSaved(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (error && !cfg) return <div className="banner error">{error}</div>;
  if (!cfg) return <div className="placeholder">Loading settings…</div>;

  return (
    <div className="view-main scroll">
      <header className="chat-header">Settings</header>
      <div className="panel-body settings">
        <label className="field">
          <span>Anthropic API key {cfg.has_api_key ? "— set ✓" : "— not set"}</span>
          <div className="key-row">
            <input
              type="password"
              value={apiKey}
              placeholder={cfg.has_api_key ? "•••••••••  (enter a new key to replace)" : "sk-ant-…"}
              onChange={(e) => setApiKey(e.target.value)}
            />
            <button className="primary" onClick={saveKey} disabled={keyBusy || !apiKey.trim()}>
              {keyBusy ? "Checking…" : "Save key"}
            </button>
          </div>
          {keyNote && <span className="saved-note">{keyNote}</span>}
        </label>

        <label className="field">
          <span>Interface language</span>
          <select value={cfg.ui_language} onChange={(e) => set("ui_language", e.target.value)}>
            <option value="en">English</option>
            <option value="de">Deutsch</option>
          </select>
        </label>

        <label className="field">
          <span>Native language</span>
          <input
            value={cfg.native_language}
            onChange={(e) => set("native_language", e.target.value)}
          />
        </label>

        <label className="field">
          <span>German level</span>
          <select value={cfg.level} onChange={(e) => set("level", e.target.value)}>
            {cfg.levels.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>German voice</span>
          <select value={cfg.voice} onChange={(e) => set("voice", e.target.value)}>
            {voices.length === 0 && <option value={cfg.voice}>{cfg.voice}</option>}
            {voices.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>English voice (Listen prompts)</span>
          <select value={cfg.voice_en} onChange={(e) => set("voice_en", e.target.value)}>
            {voicesEn.length === 0 && <option value={cfg.voice_en}>{cfg.voice_en}</option>}
            {voicesEn.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Speech rate (wpm)</span>
          <input
            type="number"
            min={80}
            max={300}
            value={cfg.speech_rate}
            onChange={(e) => set("speech_rate", Number(e.target.value))}
          />
        </label>

        <label className="field checkbox">
          <input
            type="checkbox"
            checked={cfg.tts_enabled}
            onChange={(e) => set("tts_enabled", e.target.checked)}
          />
          <span>Speak new words aloud (text-to-speech)</span>
        </label>

        <label className="field checkbox">
          <input
            type="checkbox"
            checked={cfg.stt_enabled}
            onChange={(e) => set("stt_enabled", e.target.checked)}
          />
          <span>Enable microphone pronunciation practice</span>
        </label>

        <label className="field checkbox">
          <input
            type="checkbox"
            checked={cfg.pron_ai_feedback}
            onChange={(e) => set("pron_ai_feedback", e.target.checked)}
          />
          <span>
            Detailed AI pronunciation tips (uses API credits — off = free local grading)
          </span>
        </label>

        <label className="field checkbox">
          <input
            type="checkbox"
            checked={cfg.auto_translate}
            onChange={(e) => set("auto_translate", e.target.checked)}
          />
          <span>Auto-translate replies into my native language</span>
        </label>

        <label className="field checkbox">
          <input
            type="checkbox"
            checked={cfg.focus_mode}
            onChange={(e) => set("focus_mode", e.target.checked)}
          />
          <span>Focus mode (CLI: clear screen each step)</span>
        </label>

        {error && <div className="banner error">{error}</div>}
        <div className="settings-actions">
          <button className="primary" onClick={save} disabled={busy}>
            {busy ? "Saving…" : "Save settings"}
          </button>
          {saved && <span className="saved-note">Saved ✓</span>}
        </div>
      </div>
    </div>
  );
}
