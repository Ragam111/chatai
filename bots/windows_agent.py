"""windows_agent.py — บอท Discord ที่รันบน Windows ของเจ้าของ เพื่อสั่งงานบนเครื่อง

หลักความปลอดภัย:
  - รับคำสั่งเฉพาะ DM จาก OWNER_DISCORD_ID เท่านั้น (ห้องกลุ่มถูกเพิกเฉยทั้งหมด)
  - เปิดได้เฉพาะแอปใน APPS ที่กำหนดไว้ ไม่มีการรันคำสั่งเชลล์ตามใจ
  - มาโคร (macro) รันได้เฉพาะที่อยู่ในไฟล์ MACROS_FILE และมีขั้นตอนประเภท hotkey/type/click/sleep เท่านั้น
  - มาโครที่ risky=true ต้องยืนยันด้วย !confirm <token> ภายใน 120 วินาที

คำสั่ง:
  !apps                 ดูรายการแอปที่เปิดได้
  !open <ชื่อแอป>        เปิดแอป
  !macros               ดูรายการมาโคร
  !run <ชื่อมาโคร>       รันมาโคร (risky จะขอยืนยันก่อน)
  !confirm <token>      ยืนยันมาโครที่ risky
  !help                 ดูคำสั่ง

env:
  DISCORD_BOT_TOKEN  token ของบอท (ตั้งบนเครื่อง Windows เท่านั้น)
  OWNER_DISCORD_ID   ID ของ Discord ของคุณ
  APPS               "notepad=C:\\Windows\\notepad.exe;calc=calc.exe"
  MACROS_FILE        path ของไฟล์ JSON มาโคร (ไม่บังคับ)

รัน (บน Windows):  pip install discord.py pyautogui  แล้ว  python -m bots.windows_agent
ส่วนคลิก/พิมพ์จริงใช้ pyautogui จึงทดสอบได้เฉพาะบนเครื่องที่มีหน้าจอ
"""

from __future__ import annotations

import json
import os
import secrets
import time

CONFIRM_TTL = 120
ALLOWED_STEPS = {"hotkey", "type", "click", "sleep"}


def parse_command(text: str) -> tuple[str, str]:
    """'!open notepad' → ('open', 'notepad'). ข้อความที่ไม่ใช่คำสั่งคืน ('', '')"""
    text = (text or "").strip()
    if not text.startswith("!"):
        return "", ""
    head, _, arg = text[1:].partition(" ")
    return head.lower(), arg.strip()


def is_owner(author_id: int | str, owner_id: str) -> bool:
    return bool(owner_id) and str(author_id) == str(owner_id)


def is_dm(guild) -> bool:
    return guild is None  # ข้อความส่วนตัวไม่มี guild


def parse_apps(raw: str) -> dict[str, str]:
    """'notepad=C:\\x.exe;calc=calc.exe' → {'notepad': 'C:\\x.exe', 'calc': 'calc.exe'}"""
    out: dict[str, str] = {}
    for pair in (raw or "").split(";"):
        if "=" not in pair:
            continue
        name, path = (p.strip() for p in pair.split("=", 1))
        if name and path:
            out[name.lower()] = path
    return out


def load_macros(path: str) -> dict[str, dict]:
    """อ่านมาโครจาก JSON และตัดมาโครที่มีขั้นตอนไม่อนุญาตทิ้ง"""
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    macros: dict[str, dict] = {}
    for name, spec in (raw or {}).items():
        if not isinstance(spec, dict) or not isinstance(spec.get("steps"), list):
            continue
        steps = spec["steps"]
        if all(isinstance(s, list) and s and s[0] in ALLOWED_STEPS for s in steps):
            macros[str(name).lower()] = {"risky": bool(spec.get("risky")), "steps": steps}
    return macros


class PendingConfirmations:
    """เก็บคำขอที่รอยืนยัน มีหมดอายุ ใช้ได้ครั้งเดียว"""

    def __init__(self, ttl: int = CONFIRM_TTL, clock=time.time):
        self._ttl = ttl
        self._clock = clock
        self._items: dict[str, tuple[str, float]] = {}

    def create(self, macro_name: str) -> str:
        self._purge()
        token = secrets.token_hex(3)
        self._items[token] = (macro_name, self._clock() + self._ttl)
        return token

    def consume(self, token: str) -> str | None:
        self._purge()
        item = self._items.pop(token, None)
        return item[0] if item else None

    def _purge(self) -> None:
        now = self._clock()
        self._items = {t: v for t, v in self._items.items() if v[1] > now}


def run_steps(steps: list) -> None:  # pragma: no cover - ต้องมีหน้าจอ
    import time as _t

    import pyautogui  # type: ignore

    for s in steps:
        kind = s[0]
        if kind == "hotkey":
            pyautogui.hotkey(*[str(k) for k in s[1:]])
        elif kind == "type":
            pyautogui.write(str(s[1]), interval=0.02)
        elif kind == "click":
            pyautogui.click(int(s[1]), int(s[2]))
        elif kind == "sleep":
            _t.sleep(min(float(s[1]), 30))


def open_app(target: str) -> None:  # pragma: no cover - ต้องเป็น Windows
    os.startfile(target)  # type: ignore[attr-defined]


def main() -> None:  # pragma: no cover - ต้องมี discord.py และ token จริง
    import discord  # type: ignore

    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    owner = os.environ.get("OWNER_DISCORD_ID", "").strip()
    apps = parse_apps(os.environ.get("APPS", ""))
    macros = load_macros(os.environ.get("MACROS_FILE", ""))
    if not token or not owner:
        raise SystemExit("ต้องตั้ง DISCORD_BOT_TOKEN และ OWNER_DISCORD_ID")

    pending = PendingConfirmations()
    intents = discord.Intents.default()
    intents.message_content = True
    intents.dm_messages = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_message(message):
        if message.author.bot or not is_dm(message.guild):
            return
        if not is_owner(message.author.id, owner):
            return  # ไม่ตอบคนอื่น
        cmd, arg = parse_command(message.content)
        if not cmd:
            return

        async def say(text):
            await message.channel.send(text)

        if cmd == "help":
            await say("!apps !open <แอป> !macros !run <มาโคร> !confirm <token>")
        elif cmd == "apps":
            await say("แอปที่เปิดได้: " + (", ".join(sorted(apps)) or "(ยังไม่ได้ตั้งค่า)"))
        elif cmd == "macros":
            await say("มาโคร: " + (", ".join(sorted(macros)) or "(ยังไม่ได้ตั้งค่า)"))
        elif cmd == "open":
            if arg.lower() not in apps:
                return await say("ไม่รู้จักแอปนี้ ดูรายการด้วย !apps")
            open_app(apps[arg.lower()])
            await say(f"เปิด {arg} แล้ว")
        elif cmd == "run":
            m = macros.get(arg.lower())
            if not m:
                return await say("ไม่รู้จักมาโครนี้ ดูรายการด้วย !macros")
            if m["risky"]:
                token_ = pending.create(arg.lower())
                return await say(f"มาโคร {arg} เป็นงานที่มีผลกระทบ ยืนยันด้วย: !confirm {token_} (หมดอายุใน 2 นาที)")
            run_steps(m["steps"])
            await say(f"รัน {arg} เสร็จแล้ว")
        elif cmd == "confirm":
            name = pending.consume(arg)
            if not name:
                return await say("token ไม่ถูกต้องหรือหมดอายุแล้ว")
            run_steps(macros[name]["steps"])
            await say(f"ยืนยันแล้ว รัน {name} เสร็จแล้ว")

    client.run(token)


if __name__ == "__main__":  # pragma: no cover
    main()
