"""test_sessions.py — เทส signed session token (ความปลอดภัย)"""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import sessions  # noqa: E402

SECRET = "test-secret-xyz"


class SessionsTest(unittest.TestCase):
    def test_sign_verify_roundtrip(self):
        tok = sessions.sign({"id": "42", "provider": "google"}, SECRET)
        out = sessions.verify(tok, SECRET)
        self.assertEqual(out["id"], "42")
        self.assertEqual(out["provider"], "google")
        self.assertNotIn("exp", out)   # exp ถูกถอดออกหลังตรวจ

    def test_tampered_payload_rejected(self):
        tok = sessions.sign({"id": "42"}, SECRET)
        part, sig = tok.rsplit(".", 1)
        forged = part[:-2] + "XX" + "." + sig   # แก้ payload โดยไม่แก้ลายเซ็น
        self.assertIsNone(sessions.verify(forged, SECRET))

    def test_wrong_secret_rejected(self):
        tok = sessions.sign({"id": "42"}, SECRET)
        self.assertIsNone(sessions.verify(tok, "other-secret"))

    def test_expired_rejected(self):
        tok = sessions.sign({"id": "42"}, SECRET, max_age=-1)  # หมดอายุไปแล้ว
        self.assertIsNone(sessions.verify(tok, SECRET))

    def test_garbage_rejected(self):
        for bad in ("", "nodot", "a.b.c.d", "x.y"):
            self.assertIsNone(sessions.verify(bad, SECRET))

    def test_empty_secret_sign_raises(self):
        with self.assertRaises(ValueError):
            sessions.sign({"id": "1"}, "")

    def test_valid_not_expired(self):
        tok = sessions.sign({"id": "7"}, SECRET, max_age=3600)
        self.assertIsNotNone(sessions.verify(tok, SECRET))


if __name__ == "__main__":
    unittest.main()
