"""test_chat_flow.py — integration: ล็อกอิน (cookie เซ็น) → แชต → ประวัติคงอยู่ + แยกผู้ใช้

สตาร์ท server จริงบนพอร์ตสุ่ม, backend=echo (ไม่ต้องมี LLM), history ลงไฟล์ชั่วคราว.
"""

import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["SESSION_SECRET"] = "test-secret-xyz"
os.environ["HOST"] = "127.0.0.1"
os.environ["CHAT_BACKEND"] = "echo"

import server  # noqa: E402
from app import history, sessions  # noqa: E402


def _cookie_for(user):
    token = sessions.sign(user, os.environ["SESSION_SECRET"])
    return f"{server.COOKIE_NAME}={token}"


class ChatFlowTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        hist = history.History(Path(self._tmp.name) / "h.json")
        cfg = server.Config()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(cfg, hist))
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self._tmp.cleanup()

    def _req(self, method, path, cookie=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        if cookie:
            headers["Cookie"] = cookie
        data = None
        if body is not None:
            data = json.dumps(body)
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
        r = conn.getresponse()
        raw = r.read()
        conn.close()
        return r.status, json.loads(raw) if raw else {}

    def test_chat_requires_login(self):
        st, _ = self._req("POST", "/api/chat", body={"message": "hi"})
        self.assertEqual(st, 401)

    def test_chat_and_history_roundtrip(self):
        c = _cookie_for({"provider": "google", "id": "u1", "name": "หนึ่ง"})
        st, data = self._req("POST", "/api/chat", cookie=c, body={"message": "สวัสดี"})
        self.assertEqual(st, 200)
        self.assertIn("สวัสดี", data["reply"])          # echo backend
        # ประวัติต้องมี user+assistant
        st, data = self._req("GET", "/api/history", cookie=c)
        self.assertEqual(st, 200)
        roles = [m["role"] for m in data["messages"]]
        self.assertEqual(roles, ["user", "assistant"])

    def test_history_isolated_between_users(self):
        c1 = _cookie_for({"provider": "google", "id": "u1"})
        c2 = _cookie_for({"provider": "github", "id": "u2"})
        self._req("POST", "/api/chat", cookie=c1, body={"message": "ของ u1"})
        # u2 ต้องไม่เห็นประวัติของ u1
        st, data = self._req("GET", "/api/history", cookie=c2)
        self.assertEqual(st, 200)
        self.assertEqual(data["messages"], [])

    def test_clear_only_affects_self(self):
        c1 = _cookie_for({"provider": "google", "id": "u1"})
        c2 = _cookie_for({"provider": "github", "id": "u2"})
        self._req("POST", "/api/chat", cookie=c1, body={"message": "a"})
        self._req("POST", "/api/chat", cookie=c2, body={"message": "b"})
        self._req("POST", "/api/chat/clear", cookie=c1)
        st, d1 = self._req("GET", "/api/history", cookie=c1)
        st, d2 = self._req("GET", "/api/history", cookie=c2)
        self.assertEqual(d1["messages"], [])
        self.assertEqual(len(d2["messages"]), 2)         # ของ u2 ยังอยู่

    def test_empty_message_rejected(self):
        c = _cookie_for({"provider": "google", "id": "u1"})
        st, _ = self._req("POST", "/api/chat", cookie=c, body={"message": "   "})
        self.assertEqual(st, 400)

    def test_forged_cookie_rejected(self):
        bad = f"{server.COOKIE_NAME}=not.a.valid.token"
        st, _ = self._req("GET", "/api/history", cookie=bad)
        self.assertEqual(st, 401)

    def _raw(self, method, path, cookie=None, body=None):
        """เหมือน _req แต่คืน (status, content-type, body-string ดิบ) — ใช้กับ SSE"""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        if cookie:
            headers["Cookie"] = cookie
        data = None
        if body is not None:
            data = json.dumps(body)
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
        r = conn.getresponse()
        raw = r.read().decode("utf-8")
        ctype = r.getheader("Content-Type")
        conn.close()
        return r.status, ctype, raw

    def test_stream_requires_login(self):
        st, _, _ = self._raw("POST", "/api/chat/stream", body={"message": "hi"})
        self.assertEqual(st, 401)

    def test_stream_emits_sse_and_saves_history(self):
        c = _cookie_for({"provider": "google", "id": "s1", "name": "สตรีม"})
        st, ctype, body = self._raw("POST", "/api/chat/stream", cookie=c, body={"message": "ทดสอบสตรีม"})
        self.assertEqual(st, 200)
        self.assertIn("text/event-stream", ctype)
        # รวม delta ทุก event = คำตอบเต็ม (echo สะท้อนข้อความ) + ปิดด้วย done
        deltas = []
        for block in body.split("\n\n"):
            block = block.strip()
            if block.startswith("data:"):
                evt = json.loads(block[5:].strip())
                if "delta" in evt:
                    deltas.append(evt["delta"])
        self.assertIn("ทดสอบสตรีม", "".join(deltas))
        self.assertIn('"done": true', body)
        # history บันทึก user+assistant (เหมือน non-stream)
        st, data = self._req("GET", "/api/history", cookie=c)
        self.assertEqual([m["role"] for m in data["messages"]], ["user", "assistant"])

    def test_stream_isolated_between_users(self):
        c1 = _cookie_for({"provider": "google", "id": "s1"})
        c2 = _cookie_for({"provider": "github", "id": "s2"})
        self._raw("POST", "/api/chat/stream", cookie=c1, body={"message": "ของ s1"})
        st, data = self._req("GET", "/api/history", cookie=c2)
        self.assertEqual(data["messages"], [])   # s2 ไม่เห็นของ s1


if __name__ == "__main__":
    unittest.main()
