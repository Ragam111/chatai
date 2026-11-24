"""test_discord_bridge.py — ตรรกะของบอท Discord ที่ไม่ต้องใช้ discord.py หรือ token จริง"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bots import discord_bridge as db  # noqa: E402


class ChannelMapTest(unittest.TestCase):
    def test_parses_valid_pairs(self):
        self.assertEqual(db.parse_channel_map("1:a, 2:b"), {"1": "a", "2": "b"})

    def test_skips_malformed(self):
        self.assertEqual(db.parse_channel_map("bad,3:,:x,4:c"), {"4": "c"})

    def test_empty(self):
        self.assertEqual(db.parse_channel_map(""), {})


class SplitTest(unittest.TestCase):
    def test_short_text_unchanged(self):
        self.assertEqual(db.split_for_discord("hi"), ["hi"])

    def test_long_text_split_under_limit(self):
        text = ("ก" * 1500) + "\n" + ("ข" * 1500)
        parts = db.split_for_discord(text)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= db.MAX_DISCORD_CHARS for p in parts))
        self.assertEqual("".join(parts).replace("\n", ""), text.replace("\n", ""))

    def test_empty_gives_one_part(self):
        self.assertEqual(db.split_for_discord(""), [""])


class ForwardRequestTest(unittest.TestCase):
    def test_builds_post_with_token_and_body(self):
        req = db.build_forward_request("http://h:8500/", "team-a", "sec", "สมชาย", "สวัสดี")
        self.assertEqual(req.full_url, "http://h:8500/api/rooms/team-a/webhook")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("X-room-token"), "sec")
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body, {"sender": "สมชาย", "text": "สวัสดี"})


if __name__ == "__main__":
    unittest.main()
