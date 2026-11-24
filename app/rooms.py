"""rooms.py — ชั้นเชื่อมห้องแชทกลุ่มเข้ากับ chat_backend (แพลตฟอร์มจริงเสียบทีหลังได้)

หลักการ:
  - รับข้อความเข้าผ่าน webhook: POST /api/rooms/<room_id>/webhook
    body JSON: {"sender": "...", "text": "..."} + header X-Room-Token
  - ห้องต้องลงทะเบียนด้วย env ROOMS (คั่นด้วย ,) และต้องมี secret ของตัวเอง
    ROOM_<ID>_SECRET  → ไม่มี secret = ปฏิเสธทุกคำขอ (fail closed)
  - ประวัติแยกต่อห้อง (ไม่ปนกับกล่องแชทส่วนตัวของผู้ใช้เว็บ)
  - คืนคำตอบใน response ของ webhook (ปลายทางที่รองรับ reply ใน response ใช้ได้เลย)

stdlib ล้วน เหมือน chat_backend.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import threading
from collections import deque

MAX_HISTORY = 20          # ข้อความล่าสุดต่อห้องที่เก็บเป็น context
MAX_TEXT = 4000           # จำกัดความยาวข้อความเข้า


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def configured_rooms() -> list[str]:
    raw = _env("ROOMS")
    return [r.strip() for r in raw.split(",") if r.strip()]


def room_secret(room_id: str) -> str:
    return _env("ROOM_" + room_id.upper().replace("-", "_") + "_SECRET")


def verify(room_id: str, token: str) -> bool:
    """ตรวจ token แบบ constant-time. ไม่ได้ลงทะเบียน/ไม่มี secret → False เสมอ"""
    if room_id not in configured_rooms():
        return False
    secret = room_secret(room_id)
    if not secret or not token:
        return False
    return hmac.compare_digest(secret.encode(), token.encode())


class RoomHistory:
    """ประวัติห้องแชทกลุ่ม (thread-safe) ถ้าระบุ path จะบันทึกลงไฟล์ JSON เพื่อไม่หายเมื่อรีสตาร์ต"""

    def __init__(self, path: str | None = None):
        self._lock = threading.Lock()
        self._path = path
        self._rooms: dict[str, deque] = {}
        if path:
            self._load()

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return  # ไม่มีไฟล์หรือไฟล์เสีย → เริ่มว่าง (ไม่ crash)
        if not isinstance(raw, dict):
            return
        for room_id, items in raw.items():
            if not isinstance(room_id, str) or not isinstance(items, list):
                continue
            dq = deque(maxlen=MAX_HISTORY)
            for m in items[-MAX_HISTORY:]:
                if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
                    dq.append({"role": m["role"], "content": m["content"]})
            self._rooms[room_id] = dq

    def _save(self) -> None:
        if not self._path:
            return
        data = {rid: list(dq) for rid, dq in self._rooms.items()}
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self._path)  # เขียนแบบ atomic

    def messages(self, room_id: str) -> list[dict]:
        with self._lock:
            return [dict(m) for m in self._rooms.get(room_id, deque())]

    def append(self, room_id: str, role: str, content: str) -> None:
        with self._lock:
            dq = self._rooms.setdefault(room_id, deque(maxlen=MAX_HISTORY))
            dq.append({"role": role, "content": content})
            self._save()


def normalize_inbound(body: dict) -> tuple[str, str] | None:
    """คืน (sender, text) ที่ทำความสะอาดแล้ว หรือ None ถ้าข้อความไม่ถูกต้อง"""
    if not isinstance(body, dict):
        return None
    text = body.get("text")
    if not isinstance(text, str):
        return None
    text = text.strip()[:MAX_TEXT]
    if not text:
        return None
    sender = body.get("sender")
    sender = str(sender).strip()[:100] if sender else "ไม่ทราบชื่อ"
    return sender, text


_ECHO = re.compile(r"^\s*\[[^\]\n]{1,100}\]\s*")


def strip_echoed_sender(answer: str) -> str:
    """ตัด "[ชื่อ] " ที่โมเดลทวนกลับมาจากรูปแบบข้อความในห้อง ถ้าตัดแล้วว่างให้คงเดิม"""
    cleaned = _ECHO.sub("", answer or "", count=1)
    return cleaned or (answer or "")


def handle_message(room_id: str, sender: str, text: str, hist: RoomHistory, reply_fn, system_prompt: str) -> str:
    """ประกอบ context ของห้อง → เรียก reply_fn(messages) → บันทึกประวัติ → คืนคำตอบ"""
    prior = hist.messages(room_id)
    messages = [{"role": "system", "content": system_prompt}] + prior
    messages.append({"role": "user", "content": f"[{sender}] {text}"})
    answer = strip_echoed_sender(reply_fn(messages))
    hist.append(room_id, "user", f"[{sender}] {text}")
    hist.append(room_id, "assistant", answer)
    return answer
