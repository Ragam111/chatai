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

## โครงสร้าง
```
server.py          HTTP server + routing + cookie/session
app/oauth.py       OAuth flow (Google/GitHub) — build url, exchange, fetch user
app/sessions.py    HMAC-signed session token
web/login.html     หน้าล็อกอิน (ปุ่ม Google/GitHub)
web/chat.html      หน้าแชต
tests/             unit tests (oauth + sessions)
```

## เทส
```bash
python -m unittest discover -s tests
```

> หมายเหตุ: `/api/chat` ตอนนี้เป็น stub (ตอบกลับยืนยัน flow) — ต่อ LLM backend จริงเป็นขั้นถัดไป.
