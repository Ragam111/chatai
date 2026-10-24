"""oauth.py — เข้าสู่ระบบด้วย Google / GitHub (OAuth 2.0 Authorization Code)

flow (มาตรฐาน ปลอดภัย):
  1. ผู้ใช้กดปุ่ม → server สร้าง state (สุ่ม) เก็บไว้ → redirect ไปหน้า login ของ provider
  2. provider เด้งกลับมาที่ callback พร้อม code + state
  3. server ตรวจ state (กัน CSRF) → เอา code แลก access_token (ฝั่ง server, secret ไม่โผล่หน้าเว็บ)
  4. เอา token ไปถามข้อมูลผู้ใช้ (id/email/name)

client_id/secret มาจาก env — ไม่ hardcode ไม่ commit. stdlib ล้วน (urllib/json/secrets)
"""

from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

# config ของแต่ละ provider — endpoint มาตรฐานที่เอกสารทางการระบุ
PROVIDERS = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scope": "openid email profile",
    },
    "github": {
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "userinfo": "https://api.github.com/user",
        "scope": "read:user user:email",
    },
}


class OAuthError(Exception):
    """OAuth ล้มเหลว (provider ไม่รู้จัก / แลก token ไม่ได้ / response พัง)"""


def is_supported(provider: str) -> bool:
    return provider in PROVIDERS


def new_state() -> str:
    """state สุ่ม 32 bytes (กัน CSRF) — ต้องเก็บฝั่ง server แล้วตรวจตอน callback"""
    return secrets.token_urlsafe(32)


def build_authorize_url(provider: str, client_id: str, redirect_uri: str, state: str) -> str:
    """สร้าง URL ส่งผู้ใช้ไปหน้า login ของ provider"""
    if not is_supported(provider):
        raise OAuthError(f"ไม่รองรับ provider: {provider!r}")
    if not client_id:
        raise OAuthError(f"ยังไม่ได้ตั้ง client_id ของ {provider} (ตั้ง env ก่อน)")
    cfg = PROVIDERS[provider]
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    if provider == "google":
        params["access_type"] = "online"
        params["prompt"] = "select_account"
    return cfg["authorize"] + "?" + urllib.parse.urlencode(params)


def exchange_code(provider: str, code: str, client_id: str, client_secret: str,
                  redirect_uri: str, timeout: float = 15.0) -> str:
    """เอา code แลก access_token (POST ฝั่ง server — secret ไม่หลุดไปหน้าเว็บ)"""
    if not is_supported(provider):
        raise OAuthError(f"ไม่รองรับ provider: {provider!r}")
    cfg = PROVIDERS[provider]
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    req = urllib.request.Request(cfg["token"], data=data,
                                 headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        raise OAuthError(f"แลก token กับ {provider} ไม่ได้: {e}") from e
    try:
        tok = json.loads(raw)
    except ValueError as e:
        raise OAuthError(f"token response จาก {provider} ไม่ใช่ JSON") from e
    access = tok.get("access_token")
    if not access:
        # provider มักส่ง error มาเป็น field
        raise OAuthError(f"ไม่มี access_token จาก {provider}: {tok.get('error', 'unknown')}")
    return access


def fetch_user(provider: str, access_token: str, timeout: float = 15.0) -> dict:
    """เอา access_token ไปถามข้อมูลผู้ใช้ — คืน {provider, id, email, name} (normalize ให้เหมือนกัน)"""
    if not is_supported(provider):
        raise OAuthError(f"ไม่รองรับ provider: {provider!r}")
    cfg = PROVIDERS[provider]
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json",
               "User-Agent": "chatai-oauth"}
    req = urllib.request.Request(cfg["userinfo"], headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        raise OAuthError(f"ดึงข้อมูลผู้ใช้จาก {provider} ไม่ได้: {e}") from e
    try:
        u = json.loads(raw)
    except ValueError as e:
        raise OAuthError(f"userinfo จาก {provider} ไม่ใช่ JSON") from e
    return normalize_user(provider, u)


def normalize_user(provider: str, u: dict) -> dict:
    """แปลงรูปข้อมูลผู้ใช้ของแต่ละ provider ให้เป็นทรงเดียวกัน"""
    if provider == "google":
        uid = u.get("id") or u.get("sub")
        return {"provider": "google", "id": str(uid) if uid else "",
                "email": u.get("email", ""), "name": u.get("name", "")}
    if provider == "github":
        uid = u.get("id")
        return {"provider": "github", "id": str(uid) if uid is not None else "",
                "email": u.get("email") or "",
                "name": u.get("name") or u.get("login", "")}
    return {"provider": provider, "id": "", "email": "", "name": ""}
