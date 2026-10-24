"""history.py — เก็บประวัติแชตแยกต่อผู้ใช้ (กันข้อมูลรั่วข้ามคน)

ความปลอดภัยที่สำคัญที่สุดของไฟล์นี้: ประวัติถูก "แยกกล่อง" ด้วย user_key ที่มาจาก
session ที่ *ถูก verify ลายเซ็นแล้ว* (provider:id) — ไม่ใช่ค่าที่ client ส่งมาเอง.
ผู้ใช้ A อ่าน/เขียนได้เฉพาะกล่องของตัวเอง จะอ้าง key ของ B ไม่ได้ (server เป็นคนตั้ง key).

stdlib ล้วน (json/threading/pathlib). เก็บเป็นไฟล์ JSON เดียว (gitignored) — พอสำหรับ
สเกลเล็ก; ถ้าโตค่อยสลับเป็น sqlite ผ่าน interface เดิม. ล็อกด้วย threading.Lock กันเขียนชนกัน.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

MAX_TURNS = 100          # เก็บข้อความล่าสุดต่อผู้ใช้ (กันไฟล์บวม)
VALID_ROLES = ("user", "assistant", "system")

_lock = threading.Lock()


def user_key(user: dict) -> str:
    """สร้าง key แยกกล่องจาก session ที่ verify แล้ว — provider:id (ไม่พึ่ง input จาก client)"""
    provider = str(user.get("provider") or "").strip()
    uid = str(user.get("id") or "").strip()
    if not provider or not uid:
        raise ValueError("user ไม่มี provider/id — refuse (กัน key ปน)")
    return f"{provider}:{uid}"


class History:
    def __init__(self, path):
        self.path = Path(path)

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict):
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)   # atomic — กันไฟล์พังระหว่างเขียน

    def get(self, user: dict) -> list:
        """คืนประวัติของ *ผู้ใช้คนนี้เท่านั้น* (list ของ {role, content})"""
        key = user_key(user)
        with _lock:
            return list(self._load().get(key, []))

    def append(self, user: dict, role: str, content: str) -> list:
        """เพิ่ม 1 ข้อความลงกล่องของผู้ใช้คนนี้ — คืนประวัติล่าสุด"""
        if role not in VALID_ROLES:
            raise ValueError(f"role ไม่ถูกต้อง: {role}")
        key = user_key(user)
        entry = {"role": role, "content": str(content)}
        with _lock:
            data = self._load()
            box = data.get(key, [])
            box.append(entry)
            if len(box) > MAX_TURNS:
                box = box[-MAX_TURNS:]   # เก็บเฉพาะล่าสุด
            data[key] = box
            self._save(data)
            return list(box)

    def clear(self, user: dict):
        """ลบประวัติของผู้ใช้คนนี้ (เฉพาะกล่องตัวเอง)"""
        key = user_key(user)
        with _lock:
            data = self._load()
            if key in data:
                data.pop(key, None)
                self._save(data)
