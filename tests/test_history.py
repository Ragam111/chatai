"""test_history.py — เน้นความปลอดภัย: ประวัติต้องแยกต่อผู้ใช้ ไม่รั่วข้ามคน"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import history  # noqa: E402

USER_A = {"provider": "google", "id": "aaa", "name": "A"}
USER_B = {"provider": "github", "id": "bbb", "name": "B"}


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.hist = history.History(Path(self._tmp.name) / "h.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_user_key_from_verified_fields(self):
        self.assertEqual(history.user_key(USER_A), "google:aaa")

    def test_user_key_refuses_missing(self):
        with self.assertRaises(ValueError):
            history.user_key({"provider": "google"})

    def test_append_and_get_own(self):
        self.hist.append(USER_A, "user", "สวัสดี")
        self.hist.append(USER_A, "assistant", "ครับ")
        got = self.hist.get(USER_A)
        self.assertEqual([m["content"] for m in got], ["สวัสดี", "ครับ"])

    def test_isolation_no_cross_leak(self):
        # แก่นความปลอดภัย: A เขียน แล้ว B ต้องไม่เห็นของ A
        self.hist.append(USER_A, "user", "ความลับของ A")
        self.assertEqual(self.hist.get(USER_B), [])
        self.hist.append(USER_B, "user", "ของ B")
        self.assertEqual([m["content"] for m in self.hist.get(USER_A)], ["ความลับของ A"])
        self.assertEqual([m["content"] for m in self.hist.get(USER_B)], ["ของ B"])

    def test_clear_only_own_box(self):
        self.hist.append(USER_A, "user", "A")
        self.hist.append(USER_B, "user", "B")
        self.hist.clear(USER_A)
        self.assertEqual(self.hist.get(USER_A), [])
        self.assertEqual(len(self.hist.get(USER_B)), 1)   # ของ B ไม่โดนลบ

    def test_invalid_role_rejected(self):
        with self.assertRaises(ValueError):
            self.hist.append(USER_A, "root", "x")

    def test_trim_to_max_turns(self):
        for i in range(history.MAX_TURNS + 10):
            self.hist.append(USER_A, "user", str(i))
        box = self.hist.get(USER_A)
        self.assertEqual(len(box), history.MAX_TURNS)
        self.assertEqual(box[-1]["content"], str(history.MAX_TURNS + 9))   # เก็บล่าสุด


if __name__ == "__main__":
    unittest.main()
