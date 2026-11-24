"""test_rooms.py — ชั้นห้องแชทกลุ่ม: ยืนยัน token (fail closed), ประวัติแยกห้อง, ประกอบ context"""

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import rooms  # noqa: E402

_KEYS = ("ROOMS", "ROOM_ALPHA_SECRET", "ROOM_BETA_SECRET")


class RoomAuthTest(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in _KEYS}
        os.environ["ROOMS"] = "alpha,beta"
        os.environ["ROOM_ALPHA_SECRET"] = "s3cret-alpha"
        os.environ.pop("ROOM_BETA_SECRET", None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_correct_token_accepted(self):
        self.assertTrue(rooms.verify("alpha", "s3cret-alpha"))

    def test_wrong_or_empty_token_rejected(self):
        self.assertFalse(rooms.verify("alpha", "wrong"))
        self.assertFalse(rooms.verify("alpha", ""))

    def test_unregistered_room_rejected(self):
        self.assertFalse(rooms.verify("gamma", "s3cret-alpha"))

    def test_room_without_secret_fails_closed(self):
        # beta ลงทะเบียนแต่ไม่มี secret → ปฏิเสธทุกคำขอ แม้ token ว่าง
        self.assertFalse(rooms.verify("beta", ""))
        self.assertFalse(rooms.verify("beta", "anything"))

    def test_room_id_maps_to_env_name(self):
        os.environ["ROOMS"] = "team-x"
        os.environ["ROOM_TEAM_X_SECRET"] = "k"
        try:
            self.assertTrue(rooms.verify("team-x", "k"))
        finally:
            os.environ.pop("ROOM_TEAM_X_SECRET", None)


class RoomMessageTest(unittest.TestCase):
    def test_normalize_rejects_bad_input(self):
        self.assertIsNone(rooms.normalize_inbound({}))
        self.assertIsNone(rooms.normalize_inbound({"text": "   "}))
        self.assertIsNone(rooms.normalize_inbound({"text": 123}))
        self.assertIsNone(rooms.normalize_inbound("not a dict"))

    def test_normalize_defaults_sender_and_trims(self):
        sender, text = rooms.normalize_inbound({"text": "  hi  "})
        self.assertEqual(text, "hi")
        self.assertEqual(sender, "ไม่ทราบชื่อ")

    def test_history_is_isolated_per_room(self):
        hist = rooms.RoomHistory()
        hist.append("alpha", "user", "a-only")
        self.assertEqual(hist.messages("beta"), [])
        self.assertEqual(hist.messages("alpha")[0]["content"], "a-only")

    def test_handle_message_builds_context_and_records(self):
        hist = rooms.RoomHistory()
        seen = []

        def fake_reply(messages):
            seen.append(messages)
            return "ok-" + str(len(messages))

        first = rooms.handle_message("alpha", "สมชาย", "สวัสดี", hist, fake_reply, "SYS")
        self.assertEqual(first, "ok-2")  # system + user
        second = rooms.handle_message("alpha", "สมหญิง", "ต่อ", hist, fake_reply, "SYS")
        self.assertEqual(second, "ok-4")  # system + prior user + prior assistant + new user
        self.assertEqual(seen[1][-1]["content"], "[สมหญิง] ต่อ")
        self.assertEqual(seen[0][0]["role"], "system")

    def test_history_capped(self):
        hist = rooms.RoomHistory()
        for i in range(rooms.MAX_HISTORY + 10):
            hist.append("alpha", "user", str(i))
        self.assertEqual(len(hist.messages("alpha")), rooms.MAX_HISTORY)


if __name__ == "__main__":
    unittest.main()


class EchoStripTest(unittest.TestCase):
    def test_strips_leading_sender_tag(self):
        self.assertEqual(rooms.strip_echoed_sender("[tester2] วันนี้พักผ่อน"), "วันนี้พักผ่อน")

    def test_keeps_normal_answer(self):
        self.assertEqual(rooms.strip_echoed_sender("ใช้ list[int] ได้"), "ใช้ list[int] ได้")

    def test_keeps_answer_that_is_only_a_tag(self):
        self.assertEqual(rooms.strip_echoed_sender("[x]"), "[x]")

    def test_history_stores_cleaned_answer(self):
        hist = rooms.RoomHistory()
        out = rooms.handle_message("a", "bob", "hi", hist, lambda m: "[bob] hello", "SYS")
        self.assertEqual(out, "hello")
        self.assertEqual(hist.messages("a")[-1]["content"], "hello")


class RoomHistoryPersistenceTest(unittest.TestCase):
    def test_survives_restart(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "room_history.json")
            first = rooms.RoomHistory(path)
            first.append("team-a", "user", "[สมชาย] สวัสดี")
            first.append("team-a", "assistant", "ตอบแล้ว")
            second = rooms.RoomHistory(path)  # จำลองการรีสตาร์ต
            self.assertEqual([m["content"] for m in second.messages("team-a")],
                             ["[สมชาย] สวัสดี", "ตอบแล้ว"])

    def test_corrupt_file_starts_empty(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "room_history.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{not json")
            self.assertEqual(rooms.RoomHistory(path).messages("team-a"), [])

    def test_drops_invalid_entries_on_load(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "room_history.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"team-a": [{"role": "system", "content": "x"},
                                      {"role": "user", "content": "ok"}]}, f)
            self.assertEqual(rooms.RoomHistory(path).messages("team-a"),
                             [{"role": "user", "content": "ok"}])
