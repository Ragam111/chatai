"""test_windows_agent.py — ตรรกะความปลอดภัยของบอท Windows (ไม่ต้องใช้หน้าจอหรือ Discord)"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bots import windows_agent as wa  # noqa: E402


class CommandTest(unittest.TestCase):
    def test_parses_command_and_arg(self):
        self.assertEqual(wa.parse_command("!open notepad"), ("open", "notepad"))
        self.assertEqual(wa.parse_command("!RUN daily report"), ("run", "daily report"))

    def test_non_command_ignored(self):
        self.assertEqual(wa.parse_command("hello"), ("", ""))
        self.assertEqual(wa.parse_command(""), ("", ""))


class OwnerGateTest(unittest.TestCase):
    def test_only_owner_passes(self):
        self.assertTrue(wa.is_owner(123, "123"))
        self.assertFalse(wa.is_owner(456, "123"))

    def test_empty_owner_denies_everyone(self):
        self.assertFalse(wa.is_owner("", ""))
        self.assertFalse(wa.is_owner(0, ""))

    def test_guild_message_is_not_dm(self):
        self.assertTrue(wa.is_dm(None))
        self.assertFalse(wa.is_dm(object()))


class AppsTest(unittest.TestCase):
    def test_parses_allowlist(self):
        self.assertEqual(wa.parse_apps("Notepad=notepad.exe; calc = calc.exe"),
                         {"notepad": "notepad.exe", "calc": "calc.exe"})

    def test_skips_malformed(self):
        self.assertEqual(wa.parse_apps("bad;=x;y="), {})


class MacroLoadTest(unittest.TestCase):
    def _write(self, d, data):
        p = os.path.join(d, "m.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return p

    def test_rejects_disallowed_steps(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, {
                "ok": {"steps": [["hotkey", "ctrl", "s"], ["sleep", 1]]},
                "bad": {"steps": [["shell", "rm -rf /"]]},
                "mixed": {"steps": [["click", 1, 2], ["powershell", "x"]]},
            })
            macros = wa.load_macros(p)
        self.assertIn("ok", macros)
        self.assertNotIn("bad", macros)
        self.assertNotIn("mixed", macros)

    def test_missing_file_is_empty(self):
        self.assertEqual(wa.load_macros("/nonexistent/x.json"), {})


class ConfirmationTest(unittest.TestCase):
    def test_token_is_single_use(self):
        pc = wa.PendingConfirmations()
        t = pc.create("send-report")
        self.assertEqual(pc.consume(t), "send-report")
        self.assertIsNone(pc.consume(t))

    def test_wrong_token_rejected(self):
        pc = wa.PendingConfirmations()
        pc.create("x")
        self.assertIsNone(pc.consume("nope"))

    def test_expires(self):
        now = [1000.0]
        pc = wa.PendingConfirmations(ttl=120, clock=lambda: now[0])
        t = pc.create("x")
        now[0] += 121
        self.assertIsNone(pc.consume(t))


if __name__ == "__main__":
    unittest.main()
