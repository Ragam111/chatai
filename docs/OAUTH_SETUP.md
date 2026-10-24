# ลงทะเบียน OAuth app (Google / GitHub) — ทำเองทีละขั้น

> ขั้นตอนนี้ **ต้องทำด้วยบัญชีของคุณเอง** (Claude ทำแทนไม่ได้เพราะเป็นบัญชี Google/GitHub ส่วนตัว)
> ได้ `Client ID` + `Client Secret` มาแล้วเอาไปใส่ `.env` (ห้าม commit — `.env` ถูก gitignore ไว้แล้ว)

ก่อนเริ่ม ตัดสินใจก่อนว่า **BASE_URL** คืออะไร:
- ทดสอบในเครื่อง: `http://127.0.0.1:8500`
- ขึ้นจริง: `https://chat.example.com` (โดเมนของคุณ)

`redirect/callback URL` ต้อง **ตรงเป๊ะ** กับ BASE_URL เสมอ ไม่งั้น provider จะปฏิเสธ

---

## 1) Google

1. เข้า https://console.cloud.google.com/ → สร้าง/เลือก **Project** (มุมบนซ้าย)
2. เมนูซ้าย → **APIs & Services → OAuth consent screen**
   - User Type: **External** → Create
   - กรอกชื่อแอป + email แล้ว Save (ตอนทดสอบ อยู่สถานะ *Testing* ก็พอ; เพิ่มอีเมลตัวเองใน **Test users**)
3. เมนูซ้าย → **APIs & Services → Credentials**
   - **Create Credentials → OAuth client ID**
   - Application type: **Web application**
   - **Authorized redirect URIs → ADD URI** ใส่:
     ```
     <BASE_URL>/auth/google/callback
     ```
     เช่น `http://127.0.0.1:8500/auth/google/callback`
   - Create
4. ป๊อปอัปจะโชว์ **Client ID** + **Client Secret** → copy เก็บ

ใส่ใน `.env`:
```
OAUTH_GOOGLE_CLIENT_ID=<ที่ copy มา>
OAUTH_GOOGLE_CLIENT_SECRET=<ที่ copy มา>
```

---

## 2) GitHub

1. เข้า https://github.com/settings/developers → **OAuth Apps → New OAuth App**
   (หรือทำแบบองค์กร: Settings ของ org → Developer settings → OAuth Apps)
2. กรอก:
   - **Application name**: อะไรก็ได้ (เช่น `chatai`)
   - **Homepage URL**: `<BASE_URL>` เช่น `http://127.0.0.1:8500`
   - **Authorization callback URL**:
     ```
     <BASE_URL>/auth/github/callback
     ```
     เช่น `http://127.0.0.1:8500/auth/github/callback`
3. **Register application**
4. หน้า app → copy **Client ID**; กด **Generate a new client secret** → copy **ทันที** (โชว์ครั้งเดียว)

ใส่ใน `.env`:
```
OAUTH_GITHUB_CLIENT_ID=<ที่ copy มา>
OAUTH_GITHUB_CLIENT_SECRET=<ที่ copy มา>
```

---

## 3) ตั้งค่า .env ให้ครบแล้วรัน

```bash
cp .env.example .env     # ครั้งแรกเท่านั้น
# แก้ .env: ใส่ SESSION_SECRET, BASE_URL, client id/secret ทั้งสองค่าย

# สร้าง SESSION_SECRET สุ่ม:
python -c "import secrets; print(secrets.token_urlsafe(32))"

python server.py
# เปิด BASE_URL ในเบราว์เซอร์ → กดปุ่ม Google / GitHub
```

เปิด server มันจะพิมพ์บอกว่า provider ไหน "พร้อม" แล้วบ้าง — ถ้าขึ้น "ยังไม่ได้ตั้ง client id"
แปลว่า `.env` ยังไม่ครบ

---

## 4) ต่อ LLM (ถ้าต้องการให้ตอบจริง ไม่ใช่ echo)

ใน `.env`:
```
# ใช้ Ollama ในเครื่อง
CHAT_BACKEND=ollama
OLLAMA_URL=http://127.0.0.1:11434
CHAT_MODEL=qwen2.5-coder:1.5b

# หรือใช้ OpenAI-compatible endpoint
# CHAT_BACKEND=openai
# OPENAI_BASE=https://api.openai.com/v1
# OPENAI_API_KEY=sk-...
# CHAT_MODEL=gpt-4o-mini
```
ไม่ตั้ง `CHAT_BACKEND` = โหมด `echo` (สะท้อนข้อความ ไว้ทดสอบว่า login/flow ทำงาน)

---

## ปัญหาที่เจอบ่อย
- **redirect_uri_mismatch** → callback URL ที่ลงทะเบียนไม่ตรงกับ BASE_URL (ดูให้ตรงทุกตัวอักษร รวม http/https และพอร์ต)
- **ขึ้นออกนอก localhost แล้ว server ไม่ยอมรัน** → ต้องตั้ง `SESSION_SECRET` (บังคับเพื่อความปลอดภัย)
- **cookie ไม่ติดบน https** → ปกติ (Secure cookie) ต้องเข้าผ่าน https จริงตาม BASE_URL
- **GitHub secret หาย** → generate ใหม่ได้ ไม่ต้องสร้าง app ใหม่
