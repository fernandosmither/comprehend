"""Owner connector: the author's own Claude uses this to create/manage interviews and people.

The secret in the path is validated by IdentityMiddleware (wrong secret -> 403 before we get
here), so any tool that runs is authorized. The heavy lifting — researching material, drafting
takes, grading — happens in the owner's / participants' Claude, never here.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from .config import Config
from .instructions import OWNER_SERVER_INSTRUCTIONS
from .results import interview_results, overview
from .store import Store

_VALID_STATUS = {"draft", "published"}


def build_owner(store: Store, config: Config) -> FastMCP:
    mcp = FastMCP(name="comprehend-owner", instructions=OWNER_SERVER_INSTRUCTIONS)

    @mcp.tool
    def list_interviews() -> list[dict]:
        """List every interview (draft and published) with quick stats."""
        return overview(store)

    @mcp.tool
    def get_interview(
        slug: Annotated[str, Field(description="The interview slug")],
    ) -> dict:
        """Fetch one interview's full content for review or editing."""
        interview = store.get_interview(slug)
        if not interview:
            raise ToolError(f"No interview named {slug!r}.")
        return interview

    @mcp.tool
    def create_interview(
        title: Annotated[str, Field(description="Interview title")],
        material: Annotated[str, Field(description="The source material (markdown)")] = "",
        takes: Annotated[str, Field(description="The owner's opinionated takes and cruxes")] = "",
        rubric: Annotated[str, Field(description="The key understanding points to grade against")] = "",
        always_probe: Annotated[str, Field(description="Things every participant should always be probed on")] = "",
        description: Annotated[str, Field(description="One-line blurb shown in the participant's list")] = "",
        conduct_instructions: Annotated[
            str | None, Field(description="Override the default interview conduct guide (optional)")
        ] = None,
        seed_questions: Annotated[
            list[str] | None, Field(description="Optional starter questions (Claude still varies them)")
        ] = None,
        pass_threshold: Annotated[int, Field(description="Points needed to pass")] = 7,
        num_questions: Annotated[int, Field(description="Target number of questions")] = 10,
    ) -> dict:
        """Create a new interview as a draft. Publish it with set_status when ready.

        Before calling this you should have researched the material and asked the owner about
        their takes/cruxes and what to always probe (see this connector's instructions).
        """
        interview = store.create_interview(
            title=title, material=material, takes=takes, rubric=rubric,
            always_probe=always_probe, description=description,
            conduct_instructions=conduct_instructions, seed_questions=seed_questions,
            pass_threshold=pass_threshold, num_questions=num_questions, status="draft",
        )
        store.log_event("owner_create", interview_id=interview["id"], meta={"slug": interview["slug"]})
        return {
            "slug": interview["slug"],
            "status": interview["status"],
            "message": f"Created draft '{interview['title']}'. Publish with set_status('{interview['slug']}', 'published').",
            "dashboard_url": config.admin_url,
        }

    @mcp.tool
    def update_interview(
        slug: Annotated[str, Field(description="The interview slug")],
        title: Annotated[str | None, Field(description="New title")] = None,
        material: Annotated[str | None, Field(description="New material")] = None,
        takes: Annotated[str | None, Field(description="New takes")] = None,
        rubric: Annotated[str | None, Field(description="New rubric")] = None,
        always_probe: Annotated[str | None, Field(description="New always-probe notes")] = None,
        description: Annotated[str | None, Field(description="New blurb")] = None,
        conduct_instructions: Annotated[str | None, Field(description="New conduct override")] = None,
        seed_questions: Annotated[list[str] | None, Field(description="New seed questions")] = None,
        pass_threshold: Annotated[int | None, Field(description="New pass threshold")] = None,
        num_questions: Annotated[int | None, Field(description="New question count")] = None,
    ) -> dict:
        """Edit an existing interview's fields. Only provided fields change."""
        fields = {
            "title": title, "material": material, "takes": takes, "rubric": rubric,
            "always_probe": always_probe, "description": description,
            "conduct_instructions": conduct_instructions, "pass_threshold": pass_threshold,
            "num_questions": num_questions,
        }
        if seed_questions is not None:
            fields["seed_questions"] = seed_questions
        interview = store.update_interview(slug, **fields)
        if not interview:
            raise ToolError(f"No interview named {slug!r}.")
        store.log_event("owner_update", interview_id=interview["id"], meta={"slug": slug})
        return {"slug": interview["slug"], "message": "Updated.", "dashboard_url": config.admin_url}

    @mcp.tool
    def set_status(
        slug: Annotated[str, Field(description="The interview slug")],
        status: Annotated[str, Field(description="'draft' or 'published'")],
    ) -> dict:
        """Publish or unpublish an interview. Only published interviews are visible to participants."""
        if status not in _VALID_STATUS:
            raise ToolError("status must be 'draft' or 'published'.")
        interview = store.update_interview(slug, status=status)
        if not interview:
            raise ToolError(f"No interview named {slug!r}.")
        store.log_event("owner_status", interview_id=interview["id"], meta={"status": status})
        return {"slug": slug, "status": status, "message": f"'{interview['title']}' is now {status}."}

    @mcp.tool
    def add_person(
        name: Annotated[str, Field(description="The participant's name")],
        email: Annotated[str | None, Field(description="Optional email")] = None,
    ) -> dict:
        """Create a participant and return their personal connector link to share with them."""
        person = store.add_person(name=name, email=email)
        store.log_event("owner_add_person", person_id=person["id"], meta={"name": name})
        return {
            "name": person["name"],
            "connector_url": config.participant_url(person["token"]),
            "message": f"Send this link to {name}; they add it as a custom connector in Claude.ai.",
        }

    @mcp.tool
    def list_people() -> list[dict]:
        """List participants with their personal connector links."""
        return [
            {
                "name": p["name"],
                "email": p["email"],
                "active": p["active"],
                "profile_note": p["profile_note"],
                "connector_url": config.participant_url(p["token"]),
            }
            for p in store.list_people()
        ]

    @mcp.tool
    def get_results(
        slug: Annotated[
            str | None, Field(description="Interview slug for detail; omit for an overview of all")
        ] = None,
    ) -> dict:
        """See how participants are doing — overall, or in detail for one interview."""
        if slug is None:
            return {"interviews": overview(store)}
        interview = store.get_interview(slug)
        if not interview:
            raise ToolError(f"No interview named {slug!r}.")
        return interview_results(store, interview)

    return mcp
