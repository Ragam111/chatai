"""server.py — chatai: เว็บแชตที่ล็อกอินด้วย Google / GitHub (OAuth) พร้อมระบบความปลอดภัย

ปรัชญา (เหมือน LCA): stdlib ล้วน, ความลับมาจาก env ไม่ commit, ปลอดภัยเป็นค่าเริ่มต้น.

ตัวแปร environment:
  SESSION_SECRET               ลายเซ็น session (บังคับเมื่อเปิดออกนอก localhost)
  BASE_URL                     เช่น https://chat.example.com (ใช้ประกอบ redirect_uri)
  OAUTH_GOOGLE_CLIENT_ID/SECRET
  OAUTH_GITHUB_CLIENT_ID/SECRET
  HOST (default 127.0.0.1), PORT (default 8500)

รัน: python server.py
"""

from __future__ import annotations

import http.cookies
import os
import secrets
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import oauth, sessions  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent / "web"
COOKIE_NAME = "chatai_session"
STATE_TTL = 600  # วินาที — state (CSRF) ใช้ได้ 10 นาที


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


class Config:
    def __init__(self):
        self.host = _env("HOST", "127.0.0.1")
        self.port = int(_env("PORT", "8500") or "8500")
        self.base_url = _env("BASE_URL", f"http://{self.host}:{self.port}").rstrip("/")
        self.secret = _env("SESSION_SECRET")
        self.clients = {
            "google": (_env("OAUTH_GOOGLE_CLIENT_ID"), _env("OAUTH_GOOGLE_CLIENT_SECRET")),
            "github": (_env("OAUTH_GITHUB_CLIENT_ID"), _env("OAUTH_GITHUB_CLIENT_SECRET")),
        }
        self._is_local = self.host in ("127.0.0.1", "localhost", "::1")
        # โหมด local ไม่ตั้ง secret ก็ได้ (dev) — gen ชั่วคราวในหน่วยความจำ
        if not self.secret:
            if not self._is_local:
                raise SystemExit("[ปฏิเสธ] เปิดออกนอก localhost ต้องตั้ง SESSION_SECRET (ความปลอดภัย)")
            self.secret = secrets.token_urlsafe(32)
            print("[dev] ไม่ได้ตั้ง SESSION_SECRET — gen ชั่วคราว (session หายเมื่อ restart)")

    @property
    def secure_cookie(self) -> bool:
        return self.base_url.startswith("https://")

    def redirect_uri(self, provider: str) -> str:
        return f"{self.base_url}/auth/{provider}/callback"


def make_handler(cfg: Config):
    # เก็บ state (CSRF) ที่ยังไม่ถูกใช้ — in-memory, ใช้ครั้งเดียว, มีหมดอายุ
    pending_states: dict[str, float] = {}

    def _prune_states():
        now = time.time()
        for s, exp in list(pending_states.items()):
            if exp < now:
                pending_states.pop(s, None)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            print(f"[chatai] {self.address_string()} - {fmt % args}")

        # ---------- helpers ----------
        def _send(self, status, body: bytes, ctype="text/html; charset=utf-8", extra=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            # security headers พื้นฐาน
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            for k, v in (extra or []):
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _redirect(self, location, extra=None):
            self._send(302, b"", extra=[("Location", location)] + (extra or []))

        def _serve_file(self, name, status=200):
            path = WEB_DIR / name
            try:
                self._send(status, path.read_bytes())
            except OSError:
                self._send(404, b"not found", ctype="text/plain; charset=utf-8")

        def _current_user(self):
            cookie = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
            morsel = cookie.get(COOKIE_NAME)
            if not morsel:
                return None
            return sessions.verify(morsel.value, cfg.secret)

        def _set_session_cookie(self, payload: dict):
            token = sessions.sign(payload, cfg.secret)
            c = http.cookies.SimpleCookie()
            c[COOKIE_NAME] = token
            m = c[COOKIE_NAME]
            m["path"] = "/"
            m["httponly"] = True
            m["samesite"] = "Lax"
            m["max-age"] = 7 * 24 * 3600
            if cfg.secure_cookie:
                m["secure"] = True
            return ("Set-Cookie", m.OutputString())

        def _clear_cookie(self):
            c = http.cookies.SimpleCookie()
            c[COOKIE_NAME] = ""
            m = c[COOKIE_NAME]
            m["path"] = "/"
            m["max-age"] = 0
            return ("Set-Cookie", m.OutputString())

        # ---------- routing ----------
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            if path == "/":
                return self._serve_file("chat.html") if self._current_user() else self._redirect("/login")
            if path == "/login":
                return self._serve_file("login.html")
            if path == "/logout":
                return self._redirect("/login", extra=[self._clear_cookie()])
            if path == "/api/me":
                user = self._current_user()
                if not user:
                    return self._json(401, {"error": "ยังไม่ได้ล็อกอิน"})
                return self._json(200, {"user": user})
            if path.startswith("/auth/"):
                return self._handle_auth(path, parsed)
            return self._send(404, b"not found", ctype="text/plain; charset=utf-8")

        def _json(self, status, obj):
            import json
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       ctype="application/json; charset=utf-8")

        def _handle_auth(self, path, parsed):
            parts = path.strip("/").split("/")   # ["auth", provider] หรือ ["auth", provider, "callback"]
            if len(parts) < 2 or not oauth.is_supported(parts[1]):
                return self._send(404, b"unknown provider", ctype="text/plain; charset=utf-8")
            provider = parts[1]
            client_id, client_secret = cfg.clients[provider]

            # เริ่ม flow: /auth/<provider>
            if len(parts) == 2:
                if not client_id:
                    return self._json(503, {"error": f"ยังไม่ได้ตั้งค่า {provider} (ต้องมี Client ID/Secret ใน env)"})
                _prune_states()
                state = oauth.new_state()
                pending_states[state] = time.time() + STATE_TTL
                url = oauth.build_authorize_url(provider, client_id, cfg.redirect_uri(provider), state)
                return self._redirect(url)

            # callback: /auth/<provider>/callback
            if len(parts) == 3 and parts[2] == "callback":
                qs = urllib.parse.parse_qs(parsed.query)
                state = (qs.get("state") or [""])[0]
                code = (qs.get("code") or [""])[0]
                # ตรวจ state (CSRF) — ต้องมีและใช้ครั้งเดียว
                _prune_states()
                if not state or pending_states.pop(state, None) is None:
                    return self._json(400, {"error": "state ไม่ถูกต้อง/หมดอายุ (กัน CSRF)"})
                if not code:
                    return self._json(400, {"error": "ไม่มี code จาก provider"})
                try:
                    access = oauth.exchange_code(provider, code, client_id, client_secret,
                                                 cfg.redirect_uri(provider))
                    user = oauth.fetch_user(provider, access)
                except oauth.OAuthError as e:
                    return self._json(502, {"error": str(e)})
                if not user.get("id"):
                    return self._json(502, {"error": "ข้อมูลผู้ใช้ไม่ครบจาก provider"})
                payload = {"provider": user["provider"], "id": user["id"],
                           "email": user["email"], "name": user["name"]}
                return self._redirect("/", extra=[self._set_session_cookie(payload)])
            return self._send(404, b"not found", ctype="text/plain; charset=utf-8")

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/chat":
                user = self._current_user()
                if not user:
                    return self._json(401, {"error": "ยังไม่ได้ล็อกอิน"})
                length = int(self.headers.get("Content-Length", 0))
                import json
                try:
                    data = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                except ValueError:
                    return self._json(400, {"error": "body ไม่ใช่ JSON"})
                msg = (data.get("message") or "").strip()
                if not msg:
                    return self._json(400, {"error": "ต้องมี message"})
                # stub: ยังไม่ต่อ LLM จริง — ตอบกลับเพื่อยืนยันว่า auth+flow ทำงาน
                reply = f"[chatai] สวัสดี {user.get('name') or user.get('email')} — ได้รับข้อความ: {msg}"
                return self._json(200, {"reply": reply})
            return self._send(404, b"not found", ctype="text/plain; charset=utf-8")

    return Handler


def main():
    cfg = Config()
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), make_handler(cfg))
    print(f"=== chatai === {cfg.base_url}")
    for p, (cid, _) in cfg.clients.items():
        print(f"  {p}: {'พร้อม' if cid else 'ยังไม่ได้ตั้ง client id'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nปิด server")
        httpd.shutdown()


if __name__ == "__main__":
    main()
