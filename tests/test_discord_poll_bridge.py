"""test_discord_poll_bridge.py — ตรรกะของบอท REST polling (ไม่เรียก Discord จริง)"""

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bots import discord_poll_bridge as pb  # noqa: E402

BOT = "999"


class MentionTest(unittest.TestCase):
    def test_extracts_prompt_after_mention(self):
        self.assertEqual(pb.extract_prompt("<@999> สวัสดี", BOT), "สวัสดี")
        self.assertEqual(pb.extract_prompt("hey <@!999> help", BOT), "hey  help")

    def test_no_mention_is_ignored(self):
        self.assertIsNone(pb.extract_prompt("สวัสดีทุกคน", BOT))
        self.assertIsNone(pb.extract_prompt("<@123> hi", BOT))


class HandleTest(unittest.TestCase):
    def test_human_mention_handled(self):
        msg = {"author": {"id": "1", "username": "a"}, "content": "<@999> 2+2"}
        self.assertEqual(pb.should_handle(msg, BOT), "2+2")

    def test_bot_authors_ignored(self):
        self.assertIsNone(pb.should_handle({"author": {"id": "5", "bot": True}, "content": "<@999> x"}, BOT))
        self.assertIsNone(pb.should_handle({"author": {"id": BOT}, "content": "<@999> x"}, BOT))

    def test_mention_only_is_ignored(self):
        self.assertIsNone(pb.should_handle({"author": {"id": "1"}, "content": "<@999>"}, BOT))


class PayloadTest(unittest.TestCase):
    def test_disables_all_pings(self):
        p = pb.reply_payload("@everyone hi", "42")
        self.assertEqual(p["allowed_mentions"], {"parse": []})
        self.assertEqual(p["message_reference"]["message_id"], "42")

    def test_no_reference_for_followup(self):
        self.assertNotIn("message_reference", pb.reply_payload("x", None))

    def test_orders_oldest_first(self):
        msgs = [{"id": "30"}, {"id": "10"}, {"id": "20"}]
        self.assertEqual([m["id"] for m in pb.newest_first_to_oldest(msgs)], ["10", "20", "30"])


class RateLimitTest(unittest.TestCase):
    def test_retries_after_429(self):
        calls, waits = [], []

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(req, timeout):
            calls.append(req.full_url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(req.full_url, 429, "rl", {}, io.BytesIO(b'{"retry_after": 0.5}'))
            return Resp(json.dumps({"ok": True}).encode())

        api = pb.DiscordREST("t", opener=opener, sleep=waits.append)
        self.assertEqual(api.call("GET", "/x"), {"ok": True})
        self.assertEqual(waits, [0.5])
        self.assertEqual(len(calls), 2)

    def test_sends_bot_auth_header(self):
        seen = {}

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(req, timeout):
            seen["auth"] = req.get_header("Authorization")
            return Resp(b"")

        pb.DiscordREST("abc", opener=opener).call("GET", "/x")
        self.assertEqual(seen["auth"], "Bot abc")


if __name__ == "__main__":
    unittest.main()
