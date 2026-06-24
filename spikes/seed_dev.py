"""Seed the running dev server with realistic data via the real connectors.

Usage: uv run python spikes/seed_dev.py
Assumes the server is up at http://127.0.0.1:8793 with owner secret 'dev-owner-secret'.
"""

from __future__ import annotations

import asyncio

from fastmcp import Client

BASE = "http://127.0.0.1:8793"
OWNER = f"{BASE}/owner/dev-owner-secret/mcp"


async def main() -> None:
    async with Client(OWNER) as oc:
        iv = (await oc.call_tool("create_interview", {
            "title": "METR Frontier Risk Report (May 2026)",
            "description": "Deep read of METR's frontier risk report — exec summary through the control gap.",
            "material": (
                "# METR Frontier Risk Report\n\n"
                "Core claim: frontier capability growth is outpacing the maturity of our control "
                "and evaluation methods. The report frames 'frontier risk' as the gap between what "
                "models can do and what we can reliably measure, bound, and oversee.\n\n"
                "Sections: (1) capability trajectory, (2) evaluation limits, (3) loss-of-control "
                "threat models, (4) recommended mitigations and their failure modes."
            ),
            "takes": (
                "Buck's take: the executive summary undersells loss-of-control risk and overweights "
                "eval coverage. The real crux is whether oversight scales sublinearly with capability — "
                "if it does, today's mitigations are a treadmill. I want people to be able to argue "
                "BOTH why the report is right and where it's too comfortable."
            ),
            "rubric": (
                "1) States the capability-vs-control gap precisely. "
                "2) Explains why evaluation methods lag. "
                "3) Engages Buck's crux on oversight scaling. "
                "4) Can steelman the optimistic counter-view."
            ),
            "always_probe": "Make them steelman the view they disagree with before accepting their answer.",
            "pass_threshold": 7,
            "num_questions": 10,
        })).data
        slug = iv["slug"]
        await oc.call_tool("set_status", {"slug": slug, "status": "published"})

        # a second, still-draft interview to show status variety
        draft = (await oc.call_tool("create_interview", {
            "title": "Redwood: AI Control — house principles",
            "description": "Our in-house framing of AI control vs alignment for new researchers.",
            "takes": "Control first: assume the model may be scheming and design to catch/contain it anyway.",
            "rubric": "1) control vs alignment 2) red-team mindset 3) why we bet on control",
            "pass_threshold": 7, "num_questions": 8,
        })).data

        links = {}
        for name, email in [("Anna Reyes", "anna@redwood.test"),
                            ("Ben Okafor", "ben@redwood.test"),
                            ("Carla Mendes", "carla@redwood.test")]:
            res = (await oc.call_tool("add_person", {"name": name, "email": email})).data
            links[name] = res["connector_url"]

    # Anna: fails once, then passes. Ben: passes first try. Carla: still trying.
    await take(links["Anna Reyes"], slug, score=4, passed=False,
               confusions="loss-of-control threat model; conflated control with alignment",
               strengths="clear on the capability trajectory",
               development="work through the oversight-scaling crux",
               profile="Strong on definitions and trends; shaky translating them into threat models.")
    await take(links["Anna Reyes"], slug, score=9, passed=True,
               confusions="minor wobble steelmanning the optimistic view",
               strengths="now articulates the control gap and Buck's crux well",
               development="ready for adversarial red-team exercises",
               profile="Improved threat-modeling; reasons well once pushed to argue both sides.")
    await take(links["Ben Okafor"], slug, score=8, passed=True,
               confusions="slightly hand-wavy on eval limits",
               strengths="excellent on oversight-scaling argument",
               development="tighten the evaluation-methods section",
               profile="Systems thinker; strong on mechanisms, light on empirical detail.")
    await take(links["Carla Mendes"], slug, score=5, passed=False,
               confusions="why evaluation methods lag; the steelman requirement",
               strengths="engaged and asks good questions",
               development="more time on sections 2 and 4 before retrying",
               profile="Curious and engaged; still building the core vocabulary.")

    # one piece of pushback, for the Feedback page
    async with Client(links["Anna Reyes"]) as pc:
        await pc.call_tool("send_feedback", {
            "slug": slug,
            "body": ("I think the rubric is too harsh on untrusted monitoring. With paraphrasing "
                     "plus upfront honeypotting of the monitor, it's competitive with trusted "
                     "monitoring on the safety-usefulness frontier, not strictly worse — so docking "
                     "me for defending it seems wrong."),
            "context": "Control-protocols set; I was marked down for arguing untrusted monitoring is viable.",
        })

    print("seeded.")


async def take(url: str, slug: str, *, score: int, passed: bool,
               confusions: str, strengths: str, development: str, profile: str) -> None:
    async with Client(url) as pc:
        await pc.call_tool("get_interview", {"slug": slug})
        await asyncio.sleep(0.4)  # a little time-on-task so durations aren't all 0
        await pc.call_tool("submit_result", {
            "slug": slug, "score": score, "max_score": 10, "passed": passed,
            "per_question": [{"question": "control gap?", "verdict": "partial" if not passed else "correct", "note": ""}],
            "summary": {"confusions": confusions, "strengths": strengths, "development": development},
            "profile_note": profile,
        })


if __name__ == "__main__":
    asyncio.run(main())
