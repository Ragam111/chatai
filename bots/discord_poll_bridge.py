"""discord_poll_bridge.py — บอท Discord แบบ REST polling (ไม่ใช้ WebSocket gateway)

ใช้เมื่อรันในที่ที่ส่ง token ได้เฉพาะผ่าน HTTP header (เช่น proxy ที่ฉีด credential ให้)
หรือไม่อยากลง discord.py. ทำงาน:
  1. ทุก ๆ POLL_SECONDS อ่านข้อความใหม่ของแต่ละช่องใน DISCORD_CHANNEL_MAP
  2. ตอบเฉพาะข้อความที่ @mention บอท และไม่ใช่ข้อความของบอทด้วยกัน
  3. ส่งต่อไป /api/rooms/<room>/webhook ของ chatai แล้วตอบกลับเป็น reply ในช่องเดิม
  4. ปิดการ ping ทุกชนิดในคำตอบ (allowed_mentions) กันโมเดลพิมพ์ @everyone

ไม่ตอบข้อความเก่าที่มีอยู่ก่อนบอทเริ่ม (เริ่มนับจากข้อความล่าสุดตอนเปิด)

env:
  DISCORD_BOT_TOKEN   token ของบอท (ถ้า proxy ฉีดให้ ใส่ค่าอะไรก็ได้ เช่น proxy-injected)
  CHATAI_URL          เช่น http://127.0.0.1:8500
  DISCORD_CHANNEL_MAP "channel_id:room,channel_id:room"
  ROOM_<ID>_SECRET    secret ของแต่ละห้อง (ตรงกับฝั่ง server)
  STATUS_CHANNEL_ID   (ไม่บังคับ) ช่องที่โพสต์ข้อความแจ้งว่าบอทออนไลน์ครั้งเดียวตอนเริ่ม
  POLL_SECONDS        ค่าเริ่มต้น 3

รัน: python -m bots.discord_poll_bridge
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from bots.discord_bridge import forward, parse_channel_map, split_for_discord

API = "https://discord.com/api/v10"
USER_AGENT = "DiscordBot (https://github.com/Ragam111/chatai, 1.0)"


def extract_prompt(content: str, bot_id: str) -> str | None:
    """คืนข้อความหลังตัด mention ของบอทออก หรือ None ถ้าไม่ได้ mention บอท"""
    pattern = re.compile(rf"<@!?{re.escape(bot_id)}>")
    if not pattern.search(content or ""):
        return None
    return pattern.sub("", content).strip()


def should_handle(msg: dict, bot_id: str) -> str | None:
    """ตัดสินว่าจะตอบข้อความนี้ไหม คืน prompt หรือ None"""
    author = msg.get("author") or {}
    if author.get("bot") or author.get("id") == bot_id:
        return None
    prompt = extract_prompt(msg.get("content", ""), bot_id)
    return prompt or None


def reply_payload(text: str, reply_to: str | None) -> dict:
    payload = {"content": text, "allowed_mentions": {"parse": []}}
    if reply_to:
        payload["message_reference"] = {"message_id": reply_to, "fail_if_not_exists": False}
    return payload


def newest_first_to_oldest(messages: list) -> list:
    return sorted(messages, key=lambda m: int(m["id"]))


class DiscordREST:
    def __init__(self, token: str, opener=urllib.request.urlopen, sleep=time.sleep):
        self._headers = {"Authorization": f"Bot {token}", "User-Agent": USER_AGENT,
                         "Content-Type": "application/json"}
        self._open = opener
        self._sleep = sleep

    def call(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        for _ in range(3):
            req = urllib.request.Request(API + path, data=data, method=method, headers=self._headers)
            try:
                with self._open(req, timeout=20) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                if e.code == 429:  # rate limit: รอตามที่ Discord บอกแล้วลองใหม่
                    try:
                        wait = float(json.loads(e.read() or b"{}").get("retry_after", 1))
                    except ValueError:
                        wait = 1.0
                    self._sleep(min(wait, 30))
                    continue
                raise
        raise RuntimeError("rate limited too many times")


def run() -> None:  # pragma: no cover - เรียก Discord จริง
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    base = os.environ.get("CHATAI_URL", "http://127.0.0.1:8500").strip()
    channel_map = parse_channel_map(os.environ.get("DISCORD_CHANNEL_MAP", ""))
    poll = float(os.environ.get("POLL_SECONDS", "3") or 3)
    if not token or not channel_map:
        raise SystemExit("ต้องตั้ง DISCORD_BOT_TOKEN และ DISCORD_CHANNEL_MAP")

    api = DiscordREST(token)
    me = api.call("GET", "/users/@me")
    bot_id = me["id"]
    last: dict[str, str] = {}
    for ch in channel_map:
        recent = api.call("GET", f"/channels/{ch}/messages?limit=1") or []
        last[ch] = recent[0]["id"] if recent else "0"
    print(f"บอทออนไลน์: {me.get('username')} | ช่องที่ดูแล {len(channel_map)} ช่อง", flush=True)

    status = os.environ.get("STATUS_CHANNEL_ID", "").strip()
    if status:
        api.call("POST", f"/channels/{status}/messages",
                 reply_payload("🟢 บอทออนไลน์แล้ว — @mention บอทในห้องที่เปิดไว้เพื่อถามได้เลย", None))

    while True:
        for ch, room in channel_map.items():
            try:
                q = f"?after={last[ch]}&limit=50" if last[ch] != "0" else "?limit=50"
                msgs = newest_first_to_oldest(api.call("GET", f"/channels/{ch}/messages{q}") or [])
            except (urllib.error.URLError, OSError, RuntimeError) as e:
                print(f"[{room}] อ่านข้อความไม่ได้: {e.__class__.__name__}", flush=True)
                continue
            for m in msgs:
                last[ch] = m["id"]
                prompt = should_handle(m, bot_id)
                if not prompt:
                    continue
                secret = os.environ.get("ROOM_" + room.upper().replace("-", "_") + "_SECRET", "")
                sender = (m.get("member") or {}).get("nick") or m["author"].get("global_name") or m["author"]["username"]
                answer = forward(base, room, secret, sender, prompt)
                for i, part in enumerate(split_for_discord(answer)):
                    api.call("POST", f"/channels/{ch}/messages",
                             reply_payload(part, m["id"] if i == 0 else None))
                print(f"[{room}] ตอบ {sender} แล้ว", flush=True)
        time.sleep(poll)


if __name__ == "__main__":  # pragma: no cover
    run()
