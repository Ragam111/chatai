"""sessions.py — session token แบบ signed (stateless) + ความปลอดภัย

หลักคิด: ไม่เก็บ session ฝั่ง server (stateless) — ออก token ที่ *เซ็นด้วย HMAC* ด้วย
secret ที่รู้แค่ server. client ถือ token ไว้ใน cookie; server ตรวจลายเซ็นทุกครั้ง
แก้ไข payload ไม่ได้โดยไม่รู้ secret → ปลอมตัวไม่ได้. มีวันหมดอายุกัน token เก่าถูกขโมยไปใช้

secret มาจาก env (SESSION_SECRET) — ไม่ hardcode ไม่ commit. stdlib ล้วน (hmac/hashlib/base64)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional


def _b64e(raw: bytes) -> str:
    # urlsafe + ตัด padding (ใส่ cookie/URL ได้ไม่ต้อง escape)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def sign(payload: dict, secret: str, max_age: int = 7 * 24 * 3600) -> str:
    """ออก token: base64(payload+exp) . base64(hmac) — ปลอมไม่ได้ถ้าไม่รู้ secret"""
    if not secret:
        raise ValueError("SESSION_SECRET ว่าง — ตั้ง env ก่อน (ห้ามใช้ค่าว่างเซ็น)")
    body = dict(payload)
    body["exp"] = int(time.time()) + int(max_age)
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    part = _b64e(raw)
    mac = hmac.new(secret.encode("utf-8"), part.encode("ascii"), hashlib.sha256).digest()
    return f"{part}.{_b64e(mac)}"


def verify(token: str, secret: str) -> Optional[dict]:
    """ตรวจลายเซ็น + วันหมดอายุ. ผ่าน → payload (ไม่รวม exp); ไม่ผ่าน → None (ไม่ raise)"""
    if not token or not secret or "." not in token:
        return None
    part, sig = token.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), part.encode("ascii"), hashlib.sha256).digest()
    try:
        given = _b64d(sig)
    except (ValueError, TypeError):
        return None
    # compare_digest กัน timing attack
    if not hmac.compare_digest(expected, given):
        return None
    try:
        body = json.loads(_b64d(part))
    except (ValueError, TypeError):
        return None
    if not isinstance(body, dict) or "exp" not in body:
        return None
    if int(time.time()) >= int(body["exp"]):
        return None  # หมดอายุ
    body.pop("exp", None)
    return body
