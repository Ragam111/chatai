# Data Storage — chatai

## ไฟล์เก็บข้อมูล

| ไฟล์ | อยู่ที่ | gitignored | หน้าที่ |
|------|---------|------------|---------|
| `chat_history.json` | root/ | ✅ | ประวัติแชตทุก user |

---

## chat_history.json — schema

```json
{
  "<provider>:<user_id>": [
    {"role": "user",      "content": "ข้อความ"},
    {"role": "assistant", "content": "คำตอบ"}
  ]
}
```

**key:** `provider:id` สร้างจาก session ที่ verify แล้ว (server กำหนด — client เปลี่ยนไม่ได้)

**role ที่ valid:** `user` | `assistant` | `system`

**จำกัด:** max 100 ข้อความล่าสุดต่อ user (ป้องกันไฟล์บวม)

---

## Session (stateless — ไม่มี DB)

เก็บใน **signed cookie** เท่านั้น — format:
```
base64(payload+exp) . base64(HMAC-SHA256)
```

**payload:** `{provider, id, email, name, exp}`

ไม่มีตาราง session ฝั่ง server

---

## OAuth state (in-memory — ไม่มี DB)

```python
pending_states: dict[str, float]  # {state_token: expire_time}
```
อยู่ใน RAM, หายเมื่อ restart, TTL 10 นาที

---

## สรุปสั้นๆ

```
app ทั้งหมดใช้ไฟล์ 1 ไฟล์ (chat_history.json) + cookie
ไม่มี DB ไม่มี migration ไม่มี ORM
โตเกิน → เปลี่ยนเป็น SQLite ผ่าน interface เดิม (History class)
```
