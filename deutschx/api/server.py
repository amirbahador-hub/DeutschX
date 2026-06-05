"""FastAPI app exposing the DeutschX core over HTTP.

Runs locally (the desktop app spawns it as a sidecar). REST today; the structure
leaves room for a WebSocket streaming endpoint later. Every route delegates to
deutschx.service, so the API holds no lesson logic of its own.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .. import config, service

config.ensure_api_key()  # export the saved key so the Anthropic SDK can read it

app = FastAPI(title="DeutschX API", version="0.1.0")

# The desktop app and the Vite dev server load the UI from localhost origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:1420", "tauri://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- request bodies ----------------------------------------------------------
class NewTopic(BaseModel):
    input: str


class Message(BaseModel):
    text: str = ""
    mode: str = "answer"  # answer | question | continue


class GradeBody(BaseModel):
    german: str
    answer: str
    direction: str = "en2de"  # en2de | de2en


class PronStop(BaseModel):
    german: str
    english: str = ""


class SpeakBody(BaseModel):
    text: str
    rate: int | None = None
    lang: str = "de"  # de | en


class SettingsPatch(BaseModel):
    patch: dict


class ApiKeyBody(BaseModel):
    key: str


class AddVocab(BaseModel):
    german: str
    english: str
    topic: str = ""


class CheckVocab(BaseModel):
    text: str
    meaning: str = ""


# --- routes ------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "has_api_key": bool(config.api_key())}


@app.get("/api/topics")
def list_topics() -> dict:
    return {"topics": service.list_topics()}


@app.post("/api/topics")
def create_topic(body: NewTopic) -> dict:
    if not body.input.strip():
        raise HTTPException(400, "input is empty")
    try:
        return service.create_topic(body.input)
    except Exception as exc:
        raise HTTPException(502, f"tutor error: {exc}") from exc


@app.get("/api/topics/{slug}")
def get_topic(slug: str) -> dict:
    topic = service.get_topic(slug)
    if topic is None:
        raise HTTPException(404, "topic not found")
    return topic


@app.post("/api/topics/{slug}/message")
def post_message(slug: str, body: Message) -> dict:
    try:
        return service.post_message(slug, body.text, body.mode)
    except KeyError:
        raise HTTPException(404, "topic not found")
    except Exception as exc:
        raise HTTPException(502, f"tutor error: {exc}") from exc


# --- vocabulary & review -----------------------------------------------------
@app.get("/api/vocab")
def vocab(topic: str | None = None) -> dict:
    return service.list_vocab(topic)


@app.get("/api/review/due")
def review_due(topic: str | None = None) -> dict:
    return service.review_due(topic)


@app.post("/api/review/grade")
def review_grade(body: GradeBody) -> dict:
    try:
        return service.review_grade(body.german, body.answer, body.direction)
    except KeyError:
        raise HTTPException(404, "card not found")
    except Exception as exc:
        raise HTTPException(502, f"grader error: {exc}") from exc


@app.post("/api/vocab/add")
def add_vocab(body: AddVocab) -> dict:
    if not body.german.strip():
        raise HTTPException(400, "german is empty")
    return service.add_vocab(body.german, body.english, body.topic)


@app.post("/api/vocab/check")
def check_vocab(body: CheckVocab) -> dict:
    if not body.text.strip():
        raise HTTPException(400, "text is empty")
    try:
        return service.check_vocab(body.text, body.meaning)
    except Exception as exc:
        raise HTTPException(502, f"check error: {exc}") from exc


# --- word study --------------------------------------------------------------
@app.get("/api/word")
def word_lookup(q: str, refresh: bool = False) -> dict:
    if not q.strip():
        raise HTTPException(400, "query is empty")
    try:
        return service.word_lookup(q, refresh)
    except Exception as exc:
        raise HTTPException(502, f"lookup error: {exc}") from exc


@app.get("/api/course")
def course(topic: str = "", name: str = "", refresh: bool = False) -> dict:
    try:
        return service.course(topic or None, name or None, refresh)
    except Exception as exc:
        raise HTTPException(502, f"course error: {exc}") from exc


# --- pronunciation -----------------------------------------------------------
@app.get("/api/pron/status")
def pron_status() -> dict:
    return service.pron_status()


@app.get("/api/pron/words")
def pron_words(topic: str | None = None) -> dict:
    return service.pron_words(topic)


@app.post("/api/pron/start")
def pron_start() -> dict:
    try:
        return service.pron_start()
    except Exception as exc:
        raise HTTPException(503, f"mic unavailable: {exc}") from exc


@app.post("/api/pron/stop")
def pron_stop(body: PronStop) -> dict:
    try:
        return service.pron_stop(body.german, body.english)
    except Exception as exc:
        raise HTTPException(502, f"transcription error: {exc}") from exc


# --- audio & settings --------------------------------------------------------
@app.post("/api/speak")
def speak(body: SpeakBody) -> dict:
    try:
        return service.speak(body.text, body.rate, body.lang)
    except Exception as exc:
        raise HTTPException(502, f"tts error: {exc}") from exc


@app.post("/api/speak/stop")
def speak_stop() -> dict:
    return service.stop_speaking()


@app.post("/api/key")
def set_key(body: ApiKeyBody) -> dict:
    return service.set_api_key(body.key)


@app.get("/api/settings")
def get_settings() -> dict:
    return service.get_settings()


@app.put("/api/settings")
def update_settings(body: SettingsPatch) -> dict:
    return service.update_settings(body.patch)


@app.get("/api/voices")
def voices(lang: str = "de") -> dict:
    return service.list_voices(lang)
