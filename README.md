# chatai

เว็บแชตที่ล็อกอินด้วย **Google / GitHub** (OAuth 2.0) พร้อมระบบความปลอดภัย — Python stdlib ล้วน ไม่มี dependency นอก, ความลับมาจาก env ไม่ commit.

## ความปลอดภัยที่มีให้
- **OAuth 2.0 Authorization Code** — secret แลก token ฝั่ง server เท่านั้น ไม่โผล่หน้าเว็บ
- **CSRF protection** — `state` สุ่มต่อครั้ง เก็บฝั่ง server ใช้ได้ครั้งเดียว มีหมดอายุ
- **Session แบบ HMAC-signed** (stateless) — ปลอม payload ไม่ได้ถ้าไม่รู้ `SESSION_SECRET`, มีวันหมดอายุ
- **Cookie ปลอดภัย** — `HttpOnly`, `SameSite=Lax`, `Secure` อัตโนมัติเมื่อเป็น https
- **Security headers** — `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`
- **บังคับตั้ง `SESSION_SECRET`** เมื่อเปิดออกนอก localhost (ไม่งั้นปฏิเสธรัน)

## เริ่มใช้งาน
```bash
cp .env.example .env     # แล้วเติมค่าจริง (ดูด้านล่าง)
python server.py
# เปิด http://127.0.0.1:8500
```

## ตั้งค่า OAuth (ต้องลงทะเบียน app เองก่อน)
| provider | ลงทะเบียนที่ | redirect/callback URL |
|---|---|---|
| Google | https://console.cloud.google.com/apis/credentials | `<BASE_URL>/auth/google/callback` |
| GitHub | https://github.com/settings/developers | `<BASE_URL>/auth/github/callback` |

เอา Client ID / Secret ที่ได้ไปใส่ใน `.env` (อย่า commit).

## แชต + LLM
`/api/chat` ต่อ LLM จริงผ่าน adapter (เลือกด้วย env `CHAT_BACKEND`):

| CHAT_BACKEND | ต่อกับ | env เพิ่ม |
|---|---|---|
| `echo` (default) | สะท้อนข้อความ (dev/ไม่มี LLM) | — |
| `ollama` | `{OLLAMA_URL}/api/chat` | `OLLAMA_URL`, `CHAT_MODEL` |
| `openai` | `{OPENAI_BASE}/chat/completions` (OpenAI-compatible) | `OPENAI_API_KEY`, `OPENAI_BASE`, `CHAT_MODEL` |

**ประวัติแชต** เก็บ **แยกต่อผู้ใช้** — key = `provider:id` จาก session ที่ verify แล้ว
(ไม่ใช่ค่าจาก client) → ผู้ใช้อ่าน/ลบได้เฉพาะกล่องของตัวเอง **ไม่รั่วข้ามคน**.
ไฟล์ `chat_history.json` ถูก gitignore (ไม่ commit ข้อมูลผู้ใช้).

- `GET  /api/history`      ประวัติของผู้ใช้คนนี้
- `POST /api/chat`         ส่งข้อความ → ตอบทีเดียว (JSON)
- `POST /api/chat/stream`  ส่งข้อความ → ตอบไหลทีละ chunk (SSE) หน้าเว็บใช้อันนี้
- `POST /api/chat/clear`   ล้างประวัติของตัวเอง

## โครงสร้าง
```
server.py            HTTP server + routing + cookie/session + chat/history endpoints
app/oauth.py         OAuth flow (Google/GitHub) — build url, exchange, fetch user
app/sessions.py      HMAC-signed session token
app/chat_backend.py  adapter ต่อ LLM (echo/ollama/openai) — stdlib ล้วน
app/history.py       ประวัติแชตแยกต่อผู้ใช้ (กันรั่วข้ามคน)
web/login.html       หน้าล็อกอิน (ปุ่ม Google/GitHub)
web/chat.html        หน้าแชต (โหลดประวัติ + ปุ่มล้าง)
tests/               unit + integration tests
```

## เทส
```bash
python -m unittest discover -s tests
# 38 tests: oauth + sessions + chat_backend + history (isolation) + chat flow
```
