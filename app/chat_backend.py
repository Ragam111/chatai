"""chat_backend.py — เต้ารับ LLM (adapter) สำหรับ chatai: ต่อ Ollama / OpenAI-compat

ปรัชญา (เหมือน LCA model_backend): stdlib ล้วน (urllib/json), config จาก env,
degrade graceful — ไม่ได้ตั้งค่า backend → ตอบแบบ echo (ยืนยัน flow ทำงาน) ไม่ crash.

เลือก backend ด้วย env CHAT_BACKEND:
  echo      (default) — ตอบสะท้อนข้อความ (dev/ไม่มี LLM) ไม่ยิงเน็ต
  ollama    — POST {OLLAMA_URL}/api/chat (NDJSON stream, รวมเป็นข้อความเดียว)
  openai    — POST {OPENAI_BASE}/chat/completions (OpenAI-compatible)

env ที่เกี่ยว:
  CHAT_MODEL            ชื่อโมเดล (default "qwen2.5-coder:1.5b")
  OLLAMA_URL           default http://127.0.0.1:11434
  OPENAI_BASE          default https://api.openai.com/v1
  OPENAI_API_KEY       (เมื่อ backend=openai)
  CHAT_TIMEOUT         วินาที (default 120)

interface:
  reply(messages) -> str     messages = [{"role": "user"/"assistant"/"system", "content": ...}]
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_MODEL = "qwen2.5-coder:1.5b"


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _timeout() -> int:
    try:
        return int(_env("CHAT_TIMEOUT", "120") or "120")
    except ValueError:
        return 120


def _model() -> str:
    return _env("CHAT_MODEL") or DEFAULT_MODEL


def backend_name() -> str:
    return (_env("CHAT_BACKEND", "echo") or "echo").lower()


class ChatError(Exception):
    """ความผิดพลาดฝั่ง backend (ไม่เผย detail ภายใน/คีย์)"""


def _post_json(url: str, payload: dict, headers: dict, timeout: int):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    return urllib.request.urlopen(req, timeout=timeout)


def _reply_echo(messages: list) -> str:
    last = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last = (m.get("content") or "").strip()
            break
    return f"(echo) ได้รับข้อความ: {last}" if last else "(echo) ว่างเปล่า"


def _reply_ollama(messages: list) -> str:
    url = _env("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat"
    payload = {"model": _model(), "messages": messages, "stream": True}
    try:
        resp = _post_json(url, payload, {}, _timeout())
    except (urllib.error.URLError, OSError) as e:
        raise ChatError(f"ต่อ Ollama ไม่ได้ ({e.__class__.__name__})")
    out = []
    with resp:
        for line in resp:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            chunk = (obj.get("message") or {}).get("content", "")
            if chunk:
                out.append(chunk)
            if obj.get("done"):
                break
    return "".join(out).strip() or "(ไม่มีคำตอบจากโมเดล)"


def _reply_openai(messages: list) -> str:
    base = _env("OPENAI_BASE", "https://api.openai.com/v1").rstrip("/")
    key = _env("OPENAI_API_KEY")
    if not key:
        raise ChatError("ยังไม่ได้ตั้ง OPENAI_API_KEY")
    payload = {"model": _model(), "messages": messages, "stream": False}
    try:
        resp = _post_json(base + "/chat/completions", payload,
                          {"Authorization": f"Bearer {key}"}, _timeout())
    except urllib.error.HTTPError as e:
        raise ChatError(f"OpenAI-compat ตอบ http {e.code}")
    except (urllib.error.URLError, OSError) as e:
        raise ChatError(f"ต่อ backend ไม่ได้ ({e.__class__.__name__})")
    with resp:
        try:
            obj = json.loads(resp.read().decode("utf-8"))
        except ValueError:
            raise ChatError("คำตอบ backend ไม่ใช่ JSON")
    try:
        return (obj["choices"][0]["message"]["content"] or "").strip() or "(ไม่มีคำตอบ)"
    except (KeyError, IndexError, TypeError):
        raise ChatError("รูปแบบคำตอบ backend ไม่ถูกต้อง")


_BACKENDS = {"echo": _reply_echo, "ollama": _reply_ollama, "openai": _reply_openai}


def reply(messages: list) -> str:
    """รับประวัติ (list ของ {role, content}) → คืนคำตอบเป็นข้อความ. เลือก backend จาก env"""
    fn = _BACKENDS.get(backend_name(), _reply_echo)
    return fn(messages)


# ---------- streaming (ยิงคำตอบทีละ chunk) ----------
# yield ข้อความทีละชิ้น ให้ server ส่งต่อแบบ SSE → หน้าเว็บเห็นคำตอบไหลทีละคำ

def _stream_echo(messages: list):
    for ch in _reply_echo(messages):
        yield ch


def _stream_ollama(messages: list):
    url = _env("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat"
    payload = {"model": _model(), "messages": messages, "stream": True}
    try:
        resp = _post_json(url, payload, {}, _timeout())
    except (urllib.error.URLError, OSError) as e:
        raise ChatError(f"ต่อ Ollama ไม่ได้ ({e.__class__.__name__})")
    with resp:
        for line in resp:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            chunk = (obj.get("message") or {}).get("content", "")
            if chunk:
                yield chunk
            if obj.get("done"):
                break


def _stream_openai(messages: list):
    base = _env("OPENAI_BASE", "https://api.openai.com/v1").rstrip("/")
    key = _env("OPENAI_API_KEY")
    if not key:
        raise ChatError("ยังไม่ได้ตั้ง OPENAI_API_KEY")
    payload = {"model": _model(), "messages": messages, "stream": True}
    try:
        resp = _post_json(base + "/chat/completions", payload,
                          {"Authorization": f"Bearer {key}"}, _timeout())
    except urllib.error.HTTPError as e:
        raise ChatError(f"OpenAI-compat ตอบ http {e.code}")
    except (urllib.error.URLError, OSError) as e:
        raise ChatError(f"ต่อ backend ไม่ได้ ({e.__class__.__name__})")
    with resp:
        for raw in resp:
            raw = raw.strip()
            if not raw.startswith(b"data:"):
                continue
            data = raw[5:].strip()
            if data == b"[DONE]":
                break
            try:
                obj = json.loads(data)
                delta = (obj["choices"][0].get("delta") or {}).get("content", "")
            except (ValueError, KeyError, IndexError, TypeError):
                continue
            if delta:
                yield delta


_STREAMS = {"echo": _stream_echo, "ollama": _stream_ollama, "openai": _stream_openai}


def reply_stream(messages: list):
    """generator: yield คำตอบทีละ chunk (เลือก backend จาก env). ถ้าไม่ว่าง การันตีมีอย่างน้อย 1 chunk"""
    fn = _STREAMS.get(backend_name(), _stream_echo)
    yield from fn(messages)
