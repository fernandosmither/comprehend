"""Read-only aggregation over attempts, shared by the owner connector and the dashboard API."""

from __future__ import annotations

from typing import Any

from .store import Store


def overview(store: Store) -> list[dict]:
    """One summary row per interview for the dashboard landing / `get_results()` with no slug."""
    people = {p["id"]: p for p in store.list_people()}
    rows = []
    for interview in store.list_interviews():
        rows.append(_interview_summary(store, interview, people))
    return rows


def interview_results(store: Store, interview: dict) -> dict:
    """Per-interview detail: aggregate stats + a row per participant."""
    people = {p["id"]: p for p in store.list_people()}
    attempts = store.attempts_for_interview(interview["id"])
    submitted = [a for a in attempts if a["submitted_at"]]

    by_person: dict[int, list[dict]] = {}
    for a in attempts:
        by_person.setdefault(a["person_id"], []).append(a)

    participant_rows = []
    for person_id, person_attempts in by_person.items():
        person = people.get(person_id, {"name": "(unknown)", "email": None})
        done = [a for a in person_attempts if a["submitted_at"]]
        best = max((a["score"] for a in done if a["score"] is not None), default=None)
        passed = any(a["passed"] for a in done)
        last = max(person_attempts, key=lambda a: a["started_at"])
        participant_rows.append({
            "person_id": person_id,
            "name": person["name"],
            "email": person.get("email"),
            "attempts": len(done),
            "best_score": best,
            "max_score": interview["num_questions"],
            "passed": passed,
            "last_activity": last["submitted_at"] or last["started_at"],
            "last_summary": (done[0]["summary"] if done else None),
            "last_time_spent_seconds": (done[0]["time_spent_seconds"] if done else None),
        })
    participant_rows.sort(key=lambda r: r["last_activity"], reverse=True)

    return {
        "interview": _interview_brief(interview),
        "stats": _interview_summary(store, interview, people),
        "participants": participant_rows,
    }


def person_history(store: Store, person: dict) -> dict:
    """Everything a manager would want about one person across all interviews."""
    interviews = {i["id"]: i for i in store.list_interviews()}
    attempts = store.attempts_for_person(person["id"])
    history = []
    for a in attempts:
        interview = interviews.get(a["interview_id"], {})
        history.append({
            "interview_slug": interview.get("slug"),
            "interview_title": interview.get("title"),
            "started_at": a["started_at"],
            "submitted_at": a["submitted_at"],
            "score": a["score"],
            "max_score": a["max_score"],
            "passed": a["passed"],
            "time_spent_seconds": a["time_spent_seconds"],
            "summary": a["summary"],
        })
    return {
        "person": {
            "id": person["id"],
            "name": person["name"],
            "email": person.get("email"),
            "profile_note": person.get("profile_note"),
            "active": person.get("active", True),
        },
        "history": history,
    }


# --- helpers --------------------------------------------------------------------------
def _interview_summary(store: Store, interview: dict, people: dict[int, dict]) -> dict[str, Any]:
    attempts = store.attempts_for_interview(interview["id"])
    submitted = [a for a in attempts if a["submitted_at"]]
    person_ids = {a["person_id"] for a in attempts}
    passed_people = {a["person_id"] for a in submitted if a["passed"]}
    pcts = [
        a["score"] / a["max_score"]
        for a in submitted
        if a["score"] is not None and a["max_score"]
    ]
    times = [a["time_spent_seconds"] for a in submitted if a["time_spent_seconds"] is not None]
    return {
        "slug": interview["slug"],
        "title": interview["title"],
        "status": interview["status"],
        "participants": len(person_ids),
        "attempts": len(submitted),
        "passed": len(passed_people),
        "pass_rate": (len(passed_people) / len(person_ids)) if person_ids else None,
        "avg_score_pct": (sum(pcts) / len(pcts)) if pcts else None,
        "avg_time_spent_seconds": (sum(times) // len(times)) if times else None,
    }


def _interview_brief(interview: dict) -> dict:
    return {
        "slug": interview["slug"],
        "title": interview["title"],
        "description": interview["description"],
        "status": interview["status"],
        "pass_threshold": interview["pass_threshold"],
        "num_questions": interview["num_questions"],
    }
