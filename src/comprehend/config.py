"""Configuration loaded from the environment.

The whole app (both connectors + the dashboard API + the SPA) runs as one Starlette
process behind Caddy. Access control is by URL secret, not MCP-level auth:

* participant connector: a per-person token in the path (`/c/{token}/mcp`) IS the identity.
* owner connector: a single high-entropy secret in the path (`/owner/{secret}/mcp`).
* dashboard: an admin password -> signed session cookie.

No Anthropic API key lives here: all grading/teaching happens in the participant's Claude.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

DEV_OWNER_SECRET = "dev-owner-secret"
DEV_SESSION_KEY = "dev-insecure-session-key-change-me"


@dataclass(frozen=True)
class Config:
    host: str = "127.0.0.1"
    port: int = 8793
    base_url: str = "http://127.0.0.1:8793"
    db_path: str = "comprehend.db"
    owner_secret: str = DEV_OWNER_SECRET
    admin_password_hash: str | None = None
    session_key: str = DEV_SESSION_KEY
    dev_mode: bool = True

    @property
    def owner_connector_url(self) -> str:
        return f"{self.base_url}/owner/{self.owner_secret}/mcp"

    def participant_url(self, token: str) -> str:
        return f"{self.base_url}/c/{token}/mcp"

    @property
    def admin_url(self) -> str:
        return f"{self.base_url}/admin"


def load_config() -> Config:
    host = os.environ.get("COMPREHEND_HOST", "127.0.0.1")
    port = int(os.environ.get("COMPREHEND_PORT", "8793"))
    base_url = os.environ.get("COMPREHEND_BASE_URL", f"http://{host}:{port}").rstrip("/")
    dev_mode = os.environ.get("COMPREHEND_DEV", "1") == "1"

    owner_secret = os.environ.get("COMPREHEND_OWNER_SECRET")
    if not owner_secret:
        if not dev_mode:
            raise RuntimeError("COMPREHEND_OWNER_SECRET must be set in production")
        owner_secret = DEV_OWNER_SECRET

    session_key = os.environ.get("COMPREHEND_SESSION_KEY")
    if not session_key:
        if not dev_mode:
            raise RuntimeError("COMPREHEND_SESSION_KEY must be set in production")
        session_key = DEV_SESSION_KEY

    return Config(
        host=host,
        port=port,
        base_url=base_url,
        db_path=os.environ.get("COMPREHEND_DB_PATH", "comprehend.db"),
        owner_secret=owner_secret,
        admin_password_hash=os.environ.get("COMPREHEND_ADMIN_PASSWORD_HASH"),
        session_key=session_key,
        dev_mode=dev_mode,
    )


@lru_cache
def get_config() -> Config:
    """Process-wide config singleton."""
    return load_config()
