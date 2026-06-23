"""Spike: prove the per-person path-token connector architecture works end to end.

Validates the riskiest assumptions in the plan before we build the real thing:

1. Two FastMCP streamable-HTTP servers can be mounted in ONE Starlette app under
   path-parameter routes: /c/{token}/mcp (participant) and /owner/{secret}/mcp (owner).
2. The per-request token can be recovered inside a tool (via a contextvar set by ASGI
   middleware that parses the raw path) so every call attributes to the right person.
3. Both FastMCP lifespans (session managers) can be combined under the parent app.
4. A real MCP client (fastmcp.Client) can connect through the path-token URL and call tools.

Run:  uv run python spikes/spike_path_token.py
Pass condition: prints "SPIKE PASSED" and exits 0.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import threading
from contextvars import ContextVar

import uvicorn
from fastmcp import Client, FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Mount
from starlette.types import ASGIApp, Receive, Scope, Send

PORT = 8795

# --- identity carried per-request via contextvars -------------------------------------
current_token: ContextVar[str | None] = ContextVar("current_token", default=None)
current_owner_secret: ContextVar[str | None] = ContextVar("current_owner_secret", default=None)

_PARTICIPANT_RE = re.compile(r"^/c/([^/]+)/mcp(?:/.*)?$")
_OWNER_RE = re.compile(r"^/owner/([^/]+)/mcp(?:/.*)?$")


class IdentityMiddleware:
    """Parse the raw ASGI path and stash the path token in a contextvar.

    Runs before Starlette routing, so it reads scope['path'] directly rather than
    relying on resolved path_params (which aren't populated yet at middleware time).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            tok = reset_tok = None
            sec = reset_sec = None
            if m := _PARTICIPANT_RE.match(path):
                reset_tok = current_token.set(m.group(1))
            if m := _OWNER_RE.match(path):
                reset_sec = current_owner_secret.set(m.group(1))
            try:
                await self.app(scope, receive, send)
            finally:
                if reset_tok is not None:
                    current_token.reset(reset_tok)
                if reset_sec is not None:
                    current_owner_secret.reset(reset_sec)
            return
        await self.app(scope, receive, send)


# --- the two MCP servers --------------------------------------------------------------
participant = FastMCP(name="comprehend-participant")
owner = FastMCP(name="comprehend-owner")


@participant.tool
def whoami() -> str:
    """Return the participant token the server resolved for this call."""
    return f"participant token={current_token.get()!r}"


@owner.tool
def owner_whoami() -> str:
    """Return the owner secret the server resolved for this call."""
    return f"owner secret={current_owner_secret.get()!r}"


def build_app() -> Starlette:
    participant_app = participant.http_app()  # serves /mcp
    owner_app = owner.http_app()  # serves /mcp

    @contextlib.asynccontextmanager
    async def combined_lifespan(app: Starlette):
        # Enter both FastMCP session-manager lifespans.
        async with participant_app.lifespan(app), owner_app.lifespan(app):
            yield

    return Starlette(
        routes=[
            Mount("/c/{token}", app=participant_app),
            Mount("/owner/{secret}", app=owner_app),
        ],
        middleware=[Middleware(IdentityMiddleware)],
        lifespan=combined_lifespan,
    )


# --- run uvicorn in a background thread, drive it with a real MCP client ---------------
class _Server(uvicorn.Server):
    def install_signal_handlers(self) -> None:  # don't grab signals off the main thread
        pass


async def drive() -> None:
    base = f"http://127.0.0.1:{PORT}"

    async with Client(f"{base}/c/alice-token-AAA/mcp") as c:
        tools = [t.name for t in await c.list_tools()]
        res = await c.call_tool("whoami", {})
        alice = res.data
    print("participant tools:", tools)
    print("participant whoami ->", alice)

    async with Client(f"{base}/c/bob-token-BBB/mcp") as c:
        res = await c.call_tool("whoami", {})
        bob = res.data
    print("participant whoami (bob) ->", bob)

    async with Client(f"{base}/owner/owner-secret-XYZ/mcp") as c:
        otools = [t.name for t in await c.list_tools()]
        res = await c.call_tool("owner_whoami", {})
        own = res.data
    print("owner tools:", otools)
    print("owner whoami ->", own)

    assert "alice-token-AAA" in alice, alice
    assert "bob-token-BBB" in bob, bob
    assert "owner-secret-XYZ" in own, own
    assert "whoami" in tools and "owner_whoami" in otools
    print("SPIKE PASSED")


def main() -> int:
    config = uvicorn.Config(build_app(), host="127.0.0.1", port=PORT, log_level="warning")
    server = _Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    async def runner() -> int:
        # wait for startup
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)
        else:
            print("server did not start")
            return 1
        try:
            await drive()
            return 0
        finally:
            server.should_exit = True

    rc = asyncio.run(runner())
    thread.join(timeout=5)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
