# รันบอท Discord ของ chatai

บอทเป็นโปรเซสแยกที่รับข้อความจากช่องใน Discord แล้วส่งต่อไปที่ `/api/rooms/<room>/webhook` ของ chatai และส่งคำตอบกลับช่องเดิม

## 1. ตั้งค่าใน Discord Developer Portal
1. เปิด https://discord.com/developers/applications → New Application
2. แท็บ **Bot** → Reset Token แล้วคัดลอก token (เก็บเป็นความลับ)
3. แท็บ **Bot** → Privileged Gateway Intents → เปิด **Message Content Intent**
4. แท็บ **OAuth2 → URL Generator**: scope `bot` และสิทธิ์ View Channels, Send Messages, Read Message History → เปิดลิงก์ที่ได้เพื่อเชิญบอทเข้าเซิร์ฟเวอร์

## 2. หา ID ของห้อง
ใน Discord: User Settings → Advanced → เปิด **Developer Mode** แล้วคลิกขวาที่แต่ละห้อง เลือก **Copy Channel ID**

## 3. ตั้งค่าฝั่ง chatai
ตั้ง env บนเครื่องที่รัน server (ห้ามใส่ในโค้ดหรือรีโพ):
```bash
export ROOMS=room-1,room-2,room-3
export ROOM_ROOM_1_SECRET=<สุ่มยาว ๆ>
export ROOM_ROOM_2_SECRET=<สุ่มยาว ๆ>
export ROOM_ROOM_3_SECRET=<สุ่มยาว ๆ>
export ROOM_HISTORY_FILE=/var/lib/chatai/room_history.json   # ไม่บังคับ: ให้ประวัติไม่หายเมื่อรีสตาร์ต
export CHAT_BACKEND=ollama        # หรือ openai (ต้องตั้ง OPENAI_API_KEY ด้วย)
python3 server.py
```
สร้าง secret ได้ด้วย `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`

## 4. ตั้งค่าฝั่งบอท
ติดตั้งไลบรารีหนึ่งครั้ง แล้วตั้ง env:
```bash
pip install discord.py
export DISCORD_BOT_TOKEN=<token จากขั้นที่ 1>
export CHATAI_URL=http://127.0.0.1:8500
export DISCORD_CHANNEL_MAP="<channel_id_1>:room-1,<channel_id_2>:room-2,<channel_id_3>:room-3"
export ROOM_ROOM_1_SECRET=<secret เดียวกับฝั่ง server>   # ต้องตั้งให้ครบทุกห้องที่อยู่ใน map
python3 -m bots.discord_bridge
```
เมื่อขึ้นว่า `บอทออนไลน์แล้ว` ให้พิมพ์ข้อความในห้องที่ตั้งไว้ บอทจะตอบกลับ

## 5. รันถาวรบนเซิร์ฟเวอร์ (systemd)
ดูไฟล์ `deploy/chatai.service` และ `deploy/discord-bot.service` แก้ path และ user ให้ตรงกับเครื่อง แล้วเก็บ env ไว้ในไฟล์ที่มีสิทธิ์จำกัด เช่น `/etc/chatai/env` (chmod 600) เพราะมี token และ secret

## ข้อควรรู้
- ข้อความจากบอทตัวอื่นจะถูกข้าม ไม่ตอบตัวเอง
- ห้องที่ไม่อยู่ใน `DISCORD_CHANNEL_MAP` จะถูกเพิกเฉย
- ประวัติห้องเก็บไว้สูงสุด 20 ข้อความต่อห้อง
- ถ้าไม่ตั้ง `ROOM_HISTORY_FILE` ประวัติจะหายเมื่อรีสตาร์ต
