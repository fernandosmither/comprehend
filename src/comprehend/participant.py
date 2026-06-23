"""Participant connector: the per-person endpoint a participant's own Claude talks to.

Identity is the path token (see identity.py). Tools are deliberately thin: serve the
interview package, record the structured result, and log timing/events. The interview
itself is conducted and graded inside the participant's Claude.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from .config import Config
from .identity import get_participant_token
from .instructions import DEFAULT_CONDUCT_INSTRUCTIONS, PARTICIPANT_SERVER_INSTRUCTIONS
from .store import Store


def build_participant(store: Store, config: Config) -> FastMCP:
    mcp = FastMCP(
        name="comprehend",
        instructions=PARTICIPANT_SERVER_INSTRUCTIONS,
        website_url=config.base_url if not config.dev_mode else None,
    )

    def _require_person() -> dict:
        token = get_participant_token()
        if not token:
            raise ToolError("No participant link detected. This connector needs a /c/<token>/mcp URL.")
        person = store.get_person_by_token(token)
        if not person:
            raise ToolError("This interview link isn't recognized. Ask whoever invited you for a fresh link.")
        if not person["active"]:
            raise ToolError("This interview link has been deactivated. Ask the owner for a new one.")
        return person

    @mcp.tool
    def list_interviews() -> list[dict]:
        """List the interviews available to you and whether you've already passed each."""
        person = _require_person()
        store.log_event("list", person_id=person["id"])
        out = []
        for i in store.list_interviews(status="published"):
            out.append({
                "slug": i["slug"],
                "title": i["title"],
                "description": i["description"],
                "num_questions": i["num_questions"],
                "pass_threshold": i["pass_threshold"],
                "already_passed": store.has_passed(person["id"], i["id"]),
            })
        return out

    @mcp.tool
    def get_interview(
        slug: Annotated[str, Field(description="The interview slug from list_interviews")],
    ) -> dict:
        """Pull the full interview package and start a (timed) attempt.

        Read all of it yourself before interviewing. The returned `adaptive_context` is brief
        memory of how this person did before — use it to steer toward their weak spots and to
        avoid re-asking, verbatim, anything they previously memorized.
        """
        person = _require_person()
        interview = store.get_interview(slug)
        if not interview or interview["status"] != "published":
            raise ToolError(f"No published interview named {slug!r}. Try list_interviews.")

        attempt = store.start_attempt(person["id"], interview["id"])
        store.log_event("get", person_id=person["id"], interview_id=interview["id"],
                        meta={"attempt_id": attempt["id"]})

        return {
            "slug": interview["slug"],
            "title": interview["title"],
            "description": interview["description"],
            "material": interview["material"],
            "takes": interview["takes"],
            "rubric": interview["rubric"],
            "always_probe": interview["always_probe"],
            "pass_threshold": interview["pass_threshold"],
            "num_questions": interview["num_questions"],
            "seed_questions": interview["seed_questions"],
            "conduct_instructions": _resolve_conduct(interview),
            "adaptive_context": _adaptive_context(store, person, interview),
            "attempt_id": attempt["id"],
        }

    @mcp.tool
    def submit_result(
        slug: Annotated[str, Field(description="The interview slug")],
        score: Annotated[float, Field(description="Overall quality on a 0-10 scale (mean of your per-question totals)")],
        max_score: Annotated[float, Field(description="The quality-scale maximum -- always 10")],
        passed: Annotated[bool, Field(description="True if score >= pass_threshold")],
        per_question: Annotated[
            list[dict] | None,
            Field(description="List of {topic, total (0-10), note}; include sub-answer scores if useful"),
        ] = None,
        summary: Annotated[
            dict | None,
            Field(description="{confusions, strengths, development} for the manager"),
        ] = None,
        profile_note: Annotated[
            str | None,
            Field(description="ONE updated sentence on this person's overall strengths/weaknesses"),
        ] = None,
    ) -> dict:
        """Record the finished interview. Grade honestly; they can retake until they pass."""
        person = _require_person()
        interview = store.get_interview(slug)
        if not interview:
            raise ToolError(f"No interview named {slug!r}.")

        attempt = (
            store.open_attempt(person["id"], interview["id"])
            or store.start_attempt(person["id"], interview["id"])
        )
        saved = store.submit_attempt(
            attempt["id"],
            score=float(score),
            max_score=float(max_score),
            passed=bool(passed),
            per_question=per_question,
            summary=summary,
        )
        if profile_note:
            store.update_profile_note(person["id"], profile_note.strip())
        store.log_event("submit", person_id=person["id"], interview_id=interview["id"],
                        meta={"attempt_id": attempt["id"], "score": score, "passed": passed})

        return {
            "ok": True,
            "passed": saved["passed"],
            "score": saved["score"],
            "max_score": saved["max_score"],
            "time_spent_seconds": saved["time_spent_seconds"],
            "message": (
                "Recorded — nice work, you passed." if saved["passed"]
                else "Recorded. You didn't pass yet — keep working through it and retake when ready."
            ),
        }

    return mcp


def _resolve_conduct(interview: dict) -> str:
    custom = (interview.get("conduct_instructions") or "").strip()
    if custom:
        return custom
    return DEFAULT_CONDUCT_INSTRUCTIONS.format(
        num_questions=interview["num_questions"],
        pass_threshold=interview["pass_threshold"],
    )


def _adaptive_context(store: Store, person: dict, interview: dict) -> dict[str, Any]:
    """Lean memory: a few prior-attempt one-liners + the rolling profile note. Kept small
    on purpose — Claude.ai's own memory carries the rest, and we don't want to bloat context."""
    prior = []
    for a in store.recent_attempts(person["id"], interview["id"], limit=3):
        date = (a["submitted_at"] or "")[:10]
        verdict = "PASS" if a["passed"] else "fail"
        note = ""
        if isinstance(a["summary"], dict):
            note = (a["summary"].get("confusions") or a["summary"].get("development") or "")
            if isinstance(note, list):
                note = "; ".join(str(x) for x in note)
            note = str(note)[:160]
        prior.append(
            f"{date}: {a['score']}/{a['max_score']} {verdict}" + (f" — {note}" if note else "")
        )
    return {
        "already_passed": store.has_passed(person["id"], interview["id"]),
        "prior_attempts": prior,
        "profile_note": person.get("profile_note"),
    }
