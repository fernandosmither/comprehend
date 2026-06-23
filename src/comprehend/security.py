"""Security primitives, all stdlib (no extra dependencies -> small supply-chain surface).

- per-person / owner tokens: ``secrets.token_urlsafe``
- admin password: ``hashlib.scrypt`` (salted, constant-time verify)
- session cookie: HMAC-SHA256 signed, with an expiry
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

# scrypt work factors (RFC 7914-ish defaults; fine for a login that's hit rarely).
_SCRYPT = dict(n=2**14, r=8, p=1, maxmem=0, dklen=32)


def generate_token(nbytes: int = 24) -> str:
    """High-entropy URL-safe token used for per-person connector links."""
    return secrets.token_urlsafe(nbytes)


# --- admin password -------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, b_salt, b_hash = stored.split("$", 2)
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=_unb64(b_salt), **_SCRYPT)
        return hmac.compare_digest(dk, _unb64(b_hash))
    except Exception:  # noqa: BLE001 - malformed hash -> deny
        return False


# --- signed session cookie ------------------------------------------------------------
def sign_session(key: str, sub: str, ttl_seconds: int = 7 * 24 * 3600) -> str:
    payload = {"sub": sub, "exp": int(time.time()) + ttl_seconds}
    raw = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return f"{raw}.{_sig(key, raw)}"


def verify_session(key: str, token: str | None) -> str | None:
    if not token:
        return None
    try:
        raw, sig = token.split(".", 1)
        if not hmac.compare_digest(sig, _sig(key, raw)):
            return None
        payload = json.loads(_unb64(raw))
        if int(payload["exp"]) < int(time.time()):
            return None
        return payload.get("sub")
    except Exception:  # noqa: BLE001 - malformed token -> not authed
        return None


# --- helpers --------------------------------------------------------------------------
def _sig(key: str, raw: str) -> str:
    return _b64(hmac.new(key.encode(), raw.encode(), hashlib.sha256).digest())


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
