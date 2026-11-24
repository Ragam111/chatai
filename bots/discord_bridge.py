"""discord_bridge.py — บอท Discord ที่ส่งข้อความจากช่องที่กำหนดเข้า /api/rooms/<room>/webhook ของ chatai

เป็นโปรเซสแยกจาก server หลัก (ใช้ discord.py ซึ่งไม่ใช่ stdlib) จึงไม่ถูก import จาก server.py
ตรรกะส่วนที่ทดสอบได้ (แปลงข้อความ, แบ่งข้อความยาว, สร้างคำขอ) อยู่ด้านบน ไม่ต้องมี discord.py

env:
  DISCORD_BOT_TOKEN   token ของบอท (ตั้งบนเครื่องที่รันบอท ห้ามใส่ในโค้ดหรือแชต)
  CHATAI_URL          เช่น http://127.0.0.1:8500
  DISCORD_CHANNEL_MAP ช่อง→ห้อง เช่น "123456:team-a,234567:team-b,345678:team-c"
  ROOM_<ID>_SECRET    secret ของห้องนั้น (ต้องตรงกับฝั่ง server)

รัน: pip install discord.py && python -m bots.discord_bridge
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

MAX_DISCORD_CHARS = 2000   # ขีดจำกัดข้อความของ Discord ต่อหนึ่งข้อความ


def parse_channel_map(raw: str) -> dict[str, str]:
    """'123:room-a,456:room-b' → {'123': 'room-a', '456': 'room-b'} (ข้ามรายการที่ผิดรูปแบบ)"""
    out: dict[str, str] = {}
    for pair in (raw or "").split(","):
        if ":" not in pair:
            continue
        ch, room = (p.strip() for p in pair.split(":", 1))
        if ch and room:
            out[ch] = room
    return out


def split_for_discord(text: str, limit: int = MAX_DISCORD_CHARS) -> list[str]:
    """แบ่งข้อความยาวให้แต่ละส่วนไม่เกิน limit ตัดตามบรรทัดถ้าทำได้"""
    text = text or ""
    parts: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text or not parts:
        parts.append(text)
    return parts


def build_forward_request(base_url: str, room_id: str, secret: str, sender: str, text: str) -> urllib.request.Request:
    """สร้างคำขอ POST ไปยัง webhook ของห้อง (ยังไม่ยิง)"""
    url = base_url.rstrip("/") + f"/api/rooms/{room_id}/webhook"
    body = json.dumps({"sender": sender, "text": text}, ensure_ascii=False).encode("utf-8")
    return urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Room-Token": secret},
    )


def forward(base_url: str, room_id: str, secret: str, sender: str, text: str, timeout: int = 130) -> str:
    """ส่งข้อความไปยัง chatai แล้วคืนคำตอบของ Agent (หรือข้อความแจ้งข้อผิดพลาดที่ปลอดภัย)"""
    req = build_forward_request(base_url, room_id, secret, sender, text)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return str(data.get("reply") or "(ไม่มีคำตอบ)")
    except urllib.error.HTTPError as e:
        return f"(ระบบตอบกลับไม่สำเร็จ: http {e.code})"
    except (urllib.error.URLError, OSError, ValueError):
        return "(ระบบตอบกลับไม่สำเร็จ: ต่อ chatai ไม่ได้)"


def main() -> None:  # pragma: no cover - ต้องมี discord.py และ token จริง
    import asyncio

    import discord  # type: ignore

    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    base = os.environ.get("CHATAI_URL", "http://127.0.0.1:8500").strip()
    channel_map = parse_channel_map(os.environ.get("DISCORD_CHANNEL_MAP", ""))
    if not token:
        raise SystemExit("ต้องตั้ง DISCORD_BOT_TOKEN")
    if not channel_map:
        raise SystemExit("ต้องตั้ง DISCORD_CHANNEL_MAP")

    intents = discord.Intents.default()
    intents.message_content = True  # ต้องเปิด Message Content Intent ในหน้า Developer Portal
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"บอทออนไลน์แล้ว: {client.user} | ช่องที่ดูแล: {len(channel_map)}")

    @client.event
    async def on_message(message):
        if message.author.bot:          # ไม่ตอบข้อความของบอทด้วยกัน กันวนลูป
            return
        room = channel_map.get(str(message.channel.id))
        if not room or not message.content.strip():
            return
        secret = os.environ.get("ROOM_" + room.upper().replace("-", "_") + "_SECRET", "")
        if not secret:
            return
        reply = await asyncio.to_thread(
            forward, base, room, secret, message.author.display_name, message.content)
        for part in split_for_discord(reply):
            await message.channel.send(part)

    client.run(token)


if __name__ == "__main__":  # pragma: no cover
    main()
