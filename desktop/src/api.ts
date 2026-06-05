// Thin client for the local DeutschX API (deutschx.api.server).
// Same API is reused by the future web & mobile frontends.
const BASE = "http://127.0.0.1:8756/api";

export interface TopicSummary {
  slug: string;
  name: string;
  status: string;
  turns: number;
  last_studied: string;
}
export interface Vocab { german: string; meaning: string }
export interface Reply { shown: string; vocab: Vocab[]; pending: boolean }
export interface Msg { role: "user" | "assistant"; content: string }
export interface TopicDetail {
  slug: string;
  name: string;
  status: string;
  pending: boolean;
  messages: Msg[];
}
export type Mode = "answer" | "question" | "continue";

export interface VocabStats { total: number; due: number; learned: number }
export interface Card {
  german: string;
  english: string;
  topic: string;
  reps: number;
  interval: number;
  due: string;
  added_at: string;
  is_due: boolean;
}
export interface VocabList { stats: VocabStats; cards: Card[] }
export interface DueCard { german: string; english: string }
export type Direction = "en2de" | "de2en";
export interface GradeResult {
  correct: boolean;
  quality: number;
  feedback: string;
  german: string;
  english: string;
  interval: number;
}
export interface Morpheme { part: string; type: string; meaning: string }
export interface FamilyWord { word: string; pos: string; meaning: string }
export interface Conjugation {
  infinitive: string;
  present_3sg: string;
  praeteritum_3sg: string;
  perfect_3sg: string;
  participle: string;
}
export interface Example { de: string; translation: string }
export interface WordStudy {
  word: string;
  pos: string;
  translation: string;
  article: string;
  plural: string;
  morphemes: Morpheme[];
  family: FamilyWord[];
  conjugation: Conjugation;
  examples: Example[];
  note: string;
  cached: boolean;
  linguee_url: string;
  wiktionary_url: string;
}

export interface CourseStep { type: "block" | "sentence"; en: string; de: string }
export interface Course { theme: string; level: string; steps: CourseStep[]; cached: boolean }

export interface PronStatus { available: boolean; reason: string }
export interface PronResult {
  correct: boolean;
  quality: number;
  feedback: string;
  heard: string;
  german: string;
}
export interface Settings {
  ui_language: string;
  native_language: string;
  level: string;
  voice: string;
  speech_rate: number;
  voice_en: string;
  tts_enabled: boolean;
  stt_enabled: boolean;
  pron_ai_feedback: boolean;
  auto_translate: boolean;
  focus_mode: boolean;
  levels: string[];
  has_api_key: boolean;
  platform: string;
}

async function unwrap<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(body.detail || r.statusText);
  }
  return r.json() as Promise<T>;
}

function send<T>(method: string, path: string, body: unknown): Promise<T> {
  return fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(unwrap<T>);
}
const post = <T>(path: string, body: unknown) => send<T>("POST", path, body);
const put = <T>(path: string, body: unknown) => send<T>("PUT", path, body);
// "?topic=slug" query suffix (empty when no topic → the global, all-topics view).
const tq = (topic?: string | null) => (topic ? `?topic=${encodeURIComponent(topic)}` : "");

export const api = {
  health: () => fetch(`${BASE}/health`).then(unwrap<{ ok: boolean; has_api_key: boolean }>),
  listTopics: () =>
    fetch(`${BASE}/topics`).then(unwrap<{ topics: TopicSummary[] }>).then((d) => d.topics),
  getTopic: (slug: string) => fetch(`${BASE}/topics/${slug}`).then(unwrap<TopicDetail>),
  createTopic: (input: string) =>
    post<{ slug: string; name: string; created: boolean; reply: Reply | null }>(
      "/topics",
      { input }
    ),
  sendMessage: (slug: string, text: string, mode: Mode) =>
    post<Reply>(`/topics/${slug}/message`, { text, mode }),

  // vocabulary & review (optionally scoped to one topic slug)
  listVocab: (topic?: string | null) =>
    fetch(`${BASE}/vocab${tq(topic)}`).then(unwrap<VocabList>),
  reviewDue: (topic?: string | null) =>
    fetch(`${BASE}/review/due${tq(topic)}`).then(unwrap<{ cards: DueCard[] }>).then((d) => d.cards),
  gradeReview: (german: string, answer: string, direction: Direction) =>
    post<GradeResult>("/review/grade", { german, answer, direction }),
  addVocab: (german: string, english: string, topic = "") =>
    post<{ added: boolean }>("/vocab/add", { german, english, topic }),
  checkVocab: (text: string, meaning = "") =>
    post<{ german: string; meaning: string; note: string }>("/vocab/check", { text, meaning }),

  // word study (morphology + family + conjugation; cached server-side)
  lookupWord: (q: string, refresh = false) =>
    fetch(`${BASE}/word?q=${encodeURIComponent(q)}${refresh ? "&refresh=true" : ""}`).then(
      unwrap<WordStudy>
    ),
  getCourse: (topic: string | null, name: string | null, refresh = false) =>
    fetch(
      `${BASE}/course?topic=${encodeURIComponent(topic ?? "")}&name=${encodeURIComponent(
        name ?? ""
      )}${refresh ? "&refresh=true" : ""}`
    ).then(unwrap<Course>),

  // pronunciation
  pronStatus: () => fetch(`${BASE}/pron/status`).then(unwrap<PronStatus>),
  pronWords: (topic?: string | null) =>
    fetch(`${BASE}/pron/words${tq(topic)}`).then(unwrap<{ words: DueCard[] }>).then((d) => d.words),
  pronStart: () => post<{ recording: boolean }>("/pron/start", {}),
  pronStop: (german: string, english: string) =>
    post<PronResult>("/pron/stop", { german, english }),

  // audio & settings
  speak: (text: string, rate?: number, lang: "de" | "en" = "de", signal?: AbortSignal) =>
    fetch(`${BASE}/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, rate: rate ?? null, lang }),
      signal,
    }).then(unwrap<{ ok: boolean; spoken: boolean }>),
  stopSpeaking: () => post<{ ok: boolean }>("/speak/stop", {}),
  setKey: (key: string) =>
    post<{ saved: boolean; valid: boolean | null }>("/key", { key }),
  getSettings: () => fetch(`${BASE}/settings`).then(unwrap<Settings>),
  updateSettings: (patch: Partial<Settings>) => put<Settings>("/settings", { patch }),
  listVoices: (lang: "de" | "en" = "de") =>
    fetch(`${BASE}/voices?lang=${lang}`).then(unwrap<{ voices: string[] }>).then((d) => d.voices),
};
