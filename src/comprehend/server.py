"""Assemble the single Starlette app (both connectors + dashboard API + SPA) and run it.

    /c/{token}/mcp      -> participant connector  (token = identity)
    /owner/{secret}/mcp -> owner connector        (secret validated in middleware)
    /api/*              -> dashboard JSON API      (signed-cookie auth)
    /admin[...]         -> built React SPA         (served if web/dist exists)

CLI:
    comprehend                 # run the server
    comprehend hash-password   # print a scrypt hash for COMPREHEND_ADMIN_PASSWORD_HASH
    comprehend gen-secret      # print a high-entropy secret (owner secret / session key)
"""

from __future__ import annotations

import contextlib
import getpass
import os
import sys

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import FileResponse, PlainTextResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .admin import build_admin_routes
from .config import Config, load_config
from .identity import IdentityMiddleware
from .owner import build_owner
from .participant import build_participant
from .security import generate_token, hash_password
from .store import Store


def build_app(store: Store, config: Config) -> Starlette:
    participant_app = build_participant(store, config).http_app()
    owner_app = build_owner(store, config).http_app()

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with participant_app.lifespan(app), owner_app.lifespan(app):
            yield
        store.close()

    routes = [
        Mount("/c/{token}", app=participant_app),
        Mount("/owner/{secret}", app=owner_app),
        Route("/health", lambda r: PlainTextResponse("ok")),
        *build_admin_routes(store, config),
        *_spa_routes(config),
    ]

    return Starlette(
        routes=routes,
        middleware=[Middleware(IdentityMiddleware, owner_secret=config.owner_secret)],
        lifespan=lifespan,
    )


def _spa_routes(config: Config) -> list:
    dist = os.environ.get("COMPREHEND_WEB_DIST", os.path.join(os.getcwd(), "web", "dist"))
    index = os.path.join(dist, "index.html")

    async def serve_index(_request) -> FileResponse | PlainTextResponse:
        if os.path.exists(index):
            return FileResponse(index)
        return PlainTextResponse(
            "Dashboard SPA not built yet. Run the Vite dev server, or `npm run build` in web/.",
            status_code=200,
        )

    routes = [
        Route("/", lambda r: RedirectResponse("/admin")),
        Route("/admin", serve_index),
        Route("/admin/{path:path}", serve_index),
    ]
    assets = os.path.join(dist, "assets")
    if os.path.isdir(assets):
        routes.append(Mount("/assets", app=StaticFiles(directory=assets)))
    return routes


def serve(config: Config | None = None) -> None:
    cfg = config or load_config()
    store = Store(cfg.db_path)
    app = build_app(store, cfg)
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "hash-password":
        pw = getpass.getpass("Admin password: ")
        if pw != getpass.getpass("Confirm: "):
            print("passwords don't match", file=sys.stderr)
            raise SystemExit(1)
        print(hash_password(pw))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "gen-secret":
        print(generate_token(32))
        return
    serve()


if __name__ == "__main__":
    main()
