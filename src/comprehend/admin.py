"""Dashboard JSON API + admin auth.

Auth: POST /api/login with the admin password -> a signed session cookie. Everything under
/api except login/me requires that cookie. Same-origin in production (and via the Vite dev
proxy locally), so no CORS dance and no tokens in JS.
"""

from __future__ import annotations

from typing import Any

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .config import Config
from .results import interview_results, overview, person_history
from .security import sign_session, verify_password, verify_session
from .store import Store

COOKIE = "comprehend_session"
_INTERVIEW_FIELDS = (
    "title", "description", "material", "takes", "rubric", "always_probe",
    "conduct_instructions", "seed_questions", "pass_threshold", "num_questions",
)


def build_admin_routes(store: Store, config: Config) -> list[Route]:
    def _authed(request: Request) -> bool:
        return verify_session(config.session_key, request.cookies.get(COOKIE)) is not None

    def _require(request: Request) -> None:
        if not _authed(request):
            raise HTTPException(status_code=401, detail="not authenticated")

    def _check_password(password: str) -> bool:
        if config.admin_password_hash:
            return verify_password(password, config.admin_password_hash)
        # Dev convenience: with no hash configured, accept "dev" so the dashboard is usable.
        return config.dev_mode and password == "dev"

    async def login(request: Request) -> JSONResponse:
        body = await _json(request)
        if not _check_password(str(body.get("password", ""))):
            raise HTTPException(status_code=401, detail="bad password")
        resp = JSONResponse({"ok": True})
        resp.set_cookie(
            COOKIE, sign_session(config.session_key, "admin"),
            httponly=True, samesite="lax", secure=not config.dev_mode,
            max_age=7 * 24 * 3600, path="/",
        )
        return resp

    async def logout(request: Request) -> JSONResponse:
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    async def me(request: Request) -> JSONResponse:
        return JSONResponse({"authenticated": _authed(request)})

    async def list_interviews(request: Request) -> JSONResponse:
        _require(request)
        return JSONResponse({"interviews": overview(store)})

    async def get_interview(request: Request) -> JSONResponse:
        _require(request)
        interview = store.get_interview(request.path_params["slug"])
        if not interview:
            raise HTTPException(status_code=404, detail="not found")
        return JSONResponse(interview)

    async def create_interview(request: Request) -> JSONResponse:
        _require(request)
        body = await _json(request)
        if not body.get("title"):
            raise HTTPException(status_code=400, detail="title is required")
        interview = store.create_interview(**_pick(body, _INTERVIEW_FIELDS))
        store.log_event("admin_create", interview_id=interview["id"], meta={"slug": interview["slug"]})
        return JSONResponse(interview, status_code=201)

    async def update_interview(request: Request) -> JSONResponse:
        _require(request)
        body = await _json(request)
        interview = store.update_interview(request.path_params["slug"], **_pick(body, _INTERVIEW_FIELDS))
        if not interview:
            raise HTTPException(status_code=404, detail="not found")
        return JSONResponse(interview)

    async def set_status(request: Request) -> JSONResponse:
        _require(request)
        body = await _json(request)
        status = body.get("status")
        if status not in {"draft", "published"}:
            raise HTTPException(status_code=400, detail="status must be draft|published")
        interview = store.update_interview(request.path_params["slug"], status=status)
        if not interview:
            raise HTTPException(status_code=404, detail="not found")
        return JSONResponse(interview)

    async def results(request: Request) -> JSONResponse:
        _require(request)
        interview = store.get_interview(request.path_params["slug"])
        if not interview:
            raise HTTPException(status_code=404, detail="not found")
        return JSONResponse(interview_results(store, interview))

    async def list_people(request: Request) -> JSONResponse:
        _require(request)
        people = [
            {
                "id": p["id"], "name": p["name"], "email": p["email"],
                "active": p["active"], "profile_note": p["profile_note"],
                "connector_url": config.participant_url(p["token"]),
            }
            for p in store.list_people()
        ]
        return JSONResponse({"people": people})

    async def create_person(request: Request) -> JSONResponse:
        _require(request)
        body = await _json(request)
        if not body.get("name"):
            raise HTTPException(status_code=400, detail="name is required")
        person = store.add_person(name=body["name"], email=body.get("email"))
        store.log_event("admin_add_person", person_id=person["id"], meta={"name": person["name"]})
        return JSONResponse({
            "id": person["id"], "name": person["name"], "email": person["email"],
            "connector_url": config.participant_url(person["token"]),
        }, status_code=201)

    async def set_person_active(request: Request) -> JSONResponse:
        _require(request)
        body = await _json(request)
        store.set_person_active(int(request.path_params["pid"]), bool(body.get("active", True)))
        return JSONResponse({"ok": True})

    async def get_person(request: Request) -> JSONResponse:
        _require(request)
        pid = int(request.path_params["pid"])
        person = next((p for p in store.list_people() if p["id"] == pid), None)
        if not person:
            raise HTTPException(status_code=404, detail="not found")
        data = person_history(store, person)
        data["person"]["connector_url"] = config.participant_url(person["token"])
        return JSONResponse(data)

    return [
        Route("/api/login", login, methods=["POST"]),
        Route("/api/logout", logout, methods=["POST"]),
        Route("/api/me", me, methods=["GET"]),
        Route("/api/interviews", list_interviews, methods=["GET"]),
        Route("/api/interviews", create_interview, methods=["POST"]),
        Route("/api/interviews/{slug}", get_interview, methods=["GET"]),
        Route("/api/interviews/{slug}", update_interview, methods=["PUT"]),
        Route("/api/interviews/{slug}/status", set_status, methods=["POST"]),
        Route("/api/results/{slug}", results, methods=["GET"]),
        Route("/api/people", list_people, methods=["GET"]),
        Route("/api/people", create_person, methods=["POST"]),
        Route("/api/people/{pid}", get_person, methods=["GET"]),
        Route("/api/people/{pid}/active", set_person_active, methods=["POST"]),
    ]


async def _json(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="expected a JSON object")
    return body


def _pick(body: dict, keys: tuple[str, ...]) -> dict:
    return {k: body[k] for k in keys if k in body and body[k] is not None}
