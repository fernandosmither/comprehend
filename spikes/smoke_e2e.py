"""End-to-end smoke test of the whole backend against a live uvicorn process.

Owner connector: create + publish an interview, add a person (get their link).
Participant connector (via that link): list, get (starts timed attempt), submit a fail,
re-get (adaptive context shows the prior attempt + profile note), submit a pass.
Owner + admin API: confirm results/telemetry landed.

Run: uv run python spikes/smoke_e2e.py  ->  prints "E2E PASSED" and exits 0.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading

import httpx
import uvicorn
from fastmcp import Client

from comprehend.config import Config
from comprehend.server import build_app
from comprehend.store import Store

PORT = 8796
OWNER_SECRET = "test-owner-secret-1234"


class _Server(uvicorn.Server):
    def install_signal_handlers(self) -> None:
        pass


async def drive(base: str) -> None:
    owner_url = f"{base}/owner/{OWNER_SECRET}/mcp"

    # --- owner: author + publish + add a person -------------------------------------
    async with Client(owner_url) as oc:
        otools = {t.name for t in await oc.list_tools()}
        assert {"create_interview", "set_status", "add_person", "get_results"} <= otools, otools

        created = (await oc.call_tool("create_interview", {
            "title": "METR Frontier Risk Report",
            "description": "Deep read of METR's May 2026 frontier risk report.",
            "material": "## The report\nKey claim: capabilities are outpacing controls...",
            "takes": "Buck's take: the executive summary undersells loss-of-control risk.",
            "rubric": "1) threat model 2) why controls lag 3) Buck's crux on oversight",
            "always_probe": "Can they steelman the opposing view?",
            "pass_threshold": 7,
            "num_questions": 10,
        })).data
        slug = created["slug"]
        print("created:", slug)

        await oc.call_tool("set_status", {"slug": slug, "status": "published"})

        added = (await oc.call_tool("add_person", {"name": "Anna", "email": "anna@example.com"})).data
        connector_url = added["connector_url"]
        print("anna link:", connector_url)
        assert connector_url.startswith(base + "/c/")

    # --- participant: the whole loop -------------------------------------------------
    async with Client(connector_url) as pc:
        ptools = {t.name for t in await pc.list_tools()}
        assert {"list_interviews", "get_interview", "submit_result"} <= ptools, ptools

        listing = (await pc.call_tool("list_interviews", {})).data
        assert any(i["slug"] == slug for i in listing), listing
        assert listing[0]["already_passed"] is False

        pkg = (await pc.call_tool("get_interview", {"slug": slug})).data
        assert pkg["title"].startswith("METR")
        assert "Buck's take" in pkg["takes"]
        assert pkg["adaptive_context"]["prior_attempts"] == []
        assert "Socratic" in pkg["conduct_instructions"] or "interview" in pkg["conduct_instructions"]

        # fail first
        r1 = (await pc.call_tool("submit_result", {
            "slug": slug, "score": 4, "max_score": 10, "passed": False,
            "per_question": [{"question": "threat model?", "verdict": "partial", "note": "vague"}],
            "summary": {"confusions": "loss-of-control threat model", "strengths": "definitions",
                        "development": "work through the control-vs-capability gap"},
            "profile_note": "Strong on definitions, shaky on threat models.",
        })).data
        assert r1["passed"] is False
        print("fail recorded, time_spent:", r1["time_spent_seconds"])

        # re-get: adaptive context should now carry the prior attempt + profile note
        pkg2 = (await pc.call_tool("get_interview", {"slug": slug})).data
        ac = pkg2["adaptive_context"]
        assert ac["prior_attempts"], ac
        assert ac["profile_note"] == "Strong on definitions, shaky on threat models.", ac
        assert ac["already_passed"] is False
        print("adaptive prior:", ac["prior_attempts"])

        # pass on retry
        r2 = (await pc.call_tool("submit_result", {
            "slug": slug, "score": 9, "max_score": 10, "passed": True,
            "summary": {"confusions": "none major", "strengths": "threat model now solid",
                        "development": "ready for harder material"},
            "profile_note": "Improved threat-modeling; strong conceptual grasp.",
        })).data
        assert r2["passed"] is True

        # participant pushes back hard and asks to forward it (never changes the grade)
        fb = (await pc.call_tool("send_feedback", {
            "slug": slug,
            "body": "The rubric treats untrusted monitoring as strictly worse, but with paraphrasing it's competitive.",
            "context": "Q on control protocols; I was marked down for defending untrusted monitoring.",
        })).data
        assert fb["ok"] is True and "does not change your grade" in fb["message"], fb
        print("feedback sent")

        listing2 = (await pc.call_tool("list_interviews", {})).data
        assert any(i["slug"] == slug and i["already_passed"] for i in listing2), listing2

    # --- owner: results reflect the two attempts ------------------------------------
    async with Client(owner_url) as oc:
        res = (await oc.call_tool("get_results", {"slug": slug})).data
        stats = res["stats"]
        assert stats["participants"] == 1
        assert stats["attempts"] == 2
        assert stats["passed"] == 1
        assert res["participants"][0]["name"] == "Anna"
        print("owner results stats:", stats)

        # feedback: read via owner, mark reviewed
        fbres = (await oc.call_tool("get_feedback", {})).data
        assert fbres["unreviewed"] == 1 and len(fbres["feedback"]) == 1, fbres
        item = fbres["feedback"][0]
        assert item["person_name"] == "Anna" and item["interview_slug"] == slug, item
        fid = item["id"]
        mk = (await oc.call_tool("mark_feedback_reviewed", {"feedback_id": fid})).data
        assert mk["unreviewed"] == 0, mk
        assert (await oc.call_tool("get_feedback", {})).data["feedback"] == []
        reviewed_items = (await oc.call_tool("get_feedback", {"include_reviewed": True})).data["feedback"]
        assert len(reviewed_items) == 1 and reviewed_items[0]["reviewed"] is True
        print("owner feedback ok; fid:", fid)

    # --- owner secret gating: wrong secret -> 403 -----------------------------------
    async with httpx.AsyncClient() as h:
        bad = await h.post(f"{base}/owner/WRONG/mcp", json={})
        assert bad.status_code == 403, bad.status_code

    # --- admin API: login + read --------------------------------------------------
    async with httpx.AsyncClient(base_url=base) as h:
        assert (await h.get("/api/interviews")).status_code == 401  # gated
        login = await h.post("/api/login", json={"password": "dev"})
        assert login.status_code == 200, login.text
        cookie = login.cookies.get("comprehend_session")
        assert cookie
        h.cookies.set("comprehend_session", cookie)

        ints = (await h.get("/api/interviews")).json()["interviews"]
        assert any(i["slug"] == slug for i in ints), ints
        people = (await h.get("/api/people")).json()["people"]
        assert people and people[0]["name"] == "Anna"
        assert people[0]["connector_url"].startswith(base + "/c/")
        results = (await h.get(f"/api/results/{slug}")).json()
        assert results["stats"]["attempts"] == 2
        hist = (await h.get(f"/api/people/{people[0]['id']}")).json()
        assert len(hist["history"]) == 2
        print("admin API ok; person history len:", len(hist["history"]))

        # feedback API: it's reviewed now (owner marked it); flip it back and forth
        assert (await h.get("/api/feedback/count")).json()["unreviewed"] == 0
        fb_list = (await h.get("/api/feedback")).json()["feedback"]
        assert len(fb_list) == 1 and fb_list[0]["reviewed"] is True, fb_list
        await h.post(f"/api/feedback/{fid}/reviewed", json={"reviewed": False})
        assert (await h.get("/api/feedback/count")).json()["unreviewed"] == 1
        unrev = (await h.get("/api/feedback?reviewed=false")).json()["feedback"]
        assert len(unrev) == 1 and unrev[0]["id"] == fid, unrev
        print("admin feedback API ok")

    print("E2E PASSED")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        config = Config(
            host="127.0.0.1", port=PORT, base_url=f"http://127.0.0.1:{PORT}",
            db_path=os.path.join(tmp, "test.db"), owner_secret=OWNER_SECRET,
            admin_password_hash=None, session_key="test-session-key", dev_mode=True,
        )
        store = Store(config.db_path)
        app = build_app(store, config)
        server = _Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        async def runner() -> int:
            for _ in range(100):
                if server.started:
                    break
                await asyncio.sleep(0.05)
            else:
                print("server did not start")
                return 1
            try:
                await drive(f"http://127.0.0.1:{PORT}")
                return 0
            finally:
                server.should_exit = True

        rc = asyncio.run(runner())
        thread.join(timeout=5)
        return rc


if __name__ == "__main__":
    raise SystemExit(main())
