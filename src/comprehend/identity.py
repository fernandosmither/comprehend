"""Per-request identity recovered from the connector URL path.

ASGI middleware parses the raw path *before* Starlette routing and stashes the
participant token / owner secret in contextvars that the connector tools read. This is
the architecture validated by spikes/spike_path_token.py.

The middleware also rejects owner requests whose secret doesn't match, so a wrong
`/owner/<secret>/mcp` never reaches the owner tools. Participant tokens are NOT rejected
here: unknown tokens fall through so the tools can return a friendly "bad link" message.
"""

from __future__ import annotations

import hmac
import re
from contextvars import ContextVar

from starlette.types import ASGIApp, Receive, Scope, Send

current_token: ContextVar[str | None] = ContextVar("current_token", default=None)
current_owner_secret: ContextVar[str | None] = ContextVar("current_owner_secret", default=None)

_PARTICIPANT_RE = re.compile(r"^/c/([^/]+)/mcp(?:/.*)?$")
_OWNER_RE = re.compile(r"^/owner/([^/]+)/mcp(?:/.*)?$")


def get_participant_token() -> str | None:
    return current_token.get()


def get_owner_secret() -> str | None:
    return current_owner_secret.get()


class IdentityMiddleware:
    def __init__(self, app: ASGIApp, owner_secret: str) -> None:
        self.app = app
        self.owner_secret = owner_secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        reset_tok = reset_sec = None

        if m := _PARTICIPANT_RE.match(path):
            reset_tok = current_token.set(m.group(1))
        elif m := _OWNER_RE.match(path):
            secret = m.group(1)
            if not hmac.compare_digest(secret, self.owner_secret):
                await _forbidden(send)
                return
            reset_sec = current_owner_secret.set(secret)

        try:
            await self.app(scope, receive, send)
        finally:
            if reset_tok is not None:
                current_token.reset(reset_tok)
            if reset_sec is not None:
                current_owner_secret.reset(reset_sec)


async def _forbidden(send: Send) -> None:
    await send({
        "type": "http.response.start",
        "status": 403,
        "headers": [(b"content-type", b"text/plain")],
    })
    await send({"type": "http.response.body", "body": b"forbidden"})
