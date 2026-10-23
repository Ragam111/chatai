"""test_oauth.py — เทส OAuth flow (build url, exchange, fetch user) โดย mock HTTP"""

import io
import json
import sys
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import oauth  # noqa: E402


def _fake_resp(body: str):
    m = mock.MagicMock()
    m.read.return_value = body.encode("utf-8")
    m.__enter__.return_value = m
    m.__exit__.return_value = False
    return m


class AuthorizeUrlTest(unittest.TestCase):
    def test_google_url_has_required_params(self):
        url = oauth.build_authorize_url("google", "cid", "https://x/cb", "st8")
        self.assertTrue(url.startswith("https://accounts.google.com/o/oauth2/v2/auth?"))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(q["client_id"], ["cid"])
        self.assertEqual(q["redirect_uri"], ["https://x/cb"])
        self.assertEqual(q["response_type"], ["code"])
        self.assertEqual(q["state"], ["st8"])
        self.assertIn("email", q["scope"][0])

    def test_github_url(self):
        url = oauth.build_authorize_url("github", "cid", "https://x/cb", "s")
        self.assertTrue(url.startswith("https://github.com/login/oauth/authorize?"))

    def test_unknown_provider_raises(self):
        with self.assertRaises(oauth.OAuthError):
            oauth.build_authorize_url("facebook", "cid", "https://x/cb", "s")

    def test_missing_client_id_raises(self):
        with self.assertRaises(oauth.OAuthError):
            oauth.build_authorize_url("google", "", "https://x/cb", "s")

    def test_state_is_random_and_long(self):
        a, b = oauth.new_state(), oauth.new_state()
        self.assertNotEqual(a, b)
        self.assertGreaterEqual(len(a), 32)


class ExchangeCodeTest(unittest.TestCase):
    def test_returns_access_token(self):
        body = json.dumps({"access_token": "tok123", "token_type": "bearer"})
        with mock.patch("app.oauth.urllib.request.urlopen", return_value=_fake_resp(body)):
            tok = oauth.exchange_code("github", "code", "cid", "sec", "https://x/cb")
        self.assertEqual(tok, "tok123")

    def test_missing_token_raises(self):
        body = json.dumps({"error": "bad_verification_code"})
        with mock.patch("app.oauth.urllib.request.urlopen", return_value=_fake_resp(body)):
            with self.assertRaises(oauth.OAuthError):
                oauth.exchange_code("github", "code", "cid", "sec", "https://x/cb")

    def test_network_error_raises(self):
        with mock.patch("app.oauth.urllib.request.urlopen",
                        side_effect=urllib.error.URLError("down")):
            with self.assertRaises(oauth.OAuthError):
                oauth.exchange_code("google", "code", "cid", "sec", "https://x/cb")

    def test_non_json_raises(self):
        with mock.patch("app.oauth.urllib.request.urlopen", return_value=_fake_resp("<html>")):
            with self.assertRaises(oauth.OAuthError):
                oauth.exchange_code("google", "code", "cid", "sec", "https://x/cb")


class FetchUserTest(unittest.TestCase):
    def test_google_normalized(self):
        body = json.dumps({"id": "g1", "email": "a@b.com", "name": "Alice"})
        with mock.patch("app.oauth.urllib.request.urlopen", return_value=_fake_resp(body)):
            u = oauth.fetch_user("google", "tok")
        self.assertEqual(u, {"provider": "google", "id": "g1", "email": "a@b.com", "name": "Alice"})

    def test_github_normalized_uses_login_when_no_name(self):
        body = json.dumps({"id": 777, "login": "octocat", "name": None})
        with mock.patch("app.oauth.urllib.request.urlopen", return_value=_fake_resp(body)):
            u = oauth.fetch_user("github", "tok")
        self.assertEqual(u["id"], "777")
        self.assertEqual(u["name"], "octocat")
        self.assertEqual(u["provider"], "github")

    def test_normalize_unknown_provider_empty(self):
        u = oauth.normalize_user("x", {"id": 1})
        self.assertEqual(u["id"], "")


if __name__ == "__main__":
    unittest.main()
