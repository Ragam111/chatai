"""test_chat_backend.py — เต้ารับ LLM: echo (default) + เลือก backend จาก env + กันคีย์รั่ว"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import chat_backend  # noqa: E402


class ChatBackendTest(unittest.TestCase):
    def setUp(self):
        # ล้าง env ที่เกี่ยวเพื่อให้เทสเสถียร
        for k in ("CHAT_BACKEND", "OPENAI_API_KEY", "CHAT_MODEL"):
            os.environ.pop(k, None)

    def test_default_is_echo(self):
        self.assertEqual(chat_backend.backend_name(), "echo")

    def test_echo_reflects_last_user_message(self):
        out = chat_backend.reply([{"role": "user", "content": "ทดสอบ"}])
        self.assertIn("ทดสอบ", out)

    def test_echo_empty(self):
        out = chat_backend.reply([{"role": "system", "content": "x"}])
        self.assertIn("ว่าง", out)

    def test_unknown_backend_falls_back_to_echo(self):
        os.environ["CHAT_BACKEND"] = "ไม่มีจริง"
        out = chat_backend.reply([{"role": "user", "content": "hi"}])
        self.assertIn("hi", out)

    def test_openai_without_key_raises_cleanly(self):
        os.environ["CHAT_BACKEND"] = "openai"
        with self.assertRaises(chat_backend.ChatError) as ctx:
            chat_backend.reply([{"role": "user", "content": "hi"}])
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))

    def test_model_default(self):
        self.assertEqual(chat_backend._model(), chat_backend.DEFAULT_MODEL)
        os.environ["CHAT_MODEL"] = "llama3.2"
        self.assertEqual(chat_backend._model(), "llama3.2")


if __name__ == "__main__":
    unittest.main()
