"""
Resync AI Backend — Roadmap Routes
Dedicated APIRouter for all /roadmap endpoints.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.services.roadmap import generate_roadmap
from app.services.memory import (
    get_session,
    set_roadmap,
    mark_steps_completed,
    get_progress,
)
from app.models import RoadmapStep, RoadmapProgressResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roadmap", tags=["Roadmap"])


# ─── Request / Response Helpers ───────────────────────────────

class CompleteStepsRequest(BaseModel):
    """Request body for marking steps as completed."""
    completed_steps: list[str] = Field(..., description="List of step titles to mark complete")


class RoadmapStepWithStatus(RoadmapStep):
    """RoadmapStep extended with live completion status."""
    status: str = Field("not_started", description="not_started | in_progress | completed")


class RoadmapDetailResponse(BaseModel):
    """Full roadmap with per-step completion status and summary progress."""
    session_id: str
    goal: str
    steps: list[RoadmapStepWithStatus]
    progress: RoadmapProgressResponse


class RegenerateRequest(BaseModel):
    """Request body to regenerate a roadmap for an existing session."""
    session_id: str = Field(..., description="Session ID from /recommend")
    goal: Optional[str] = Field(None, description="Override the session goal (optional)")


# ─── Endpoints ────────────────────────────────────────────────

@router.get("/{session_id}", response_model=RoadmapDetailResponse)
def get_roadmap(session_id: str):
    """
    GET /roadmap/{session_id}

    Retrieve the full roadmap for a session, with live completion status per step.
    """
    session = get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found. Call POST /recommend first.",
        )

    roadmap = session.get("roadmap", [])
    completed_set = set(session.get("completed_steps", []))
    progress_data = get_progress(session_id)

    steps_with_status: list[RoadmapStepWithStatus] = []
    for raw in roadmap:
        title = raw.get("title", "")
        status = "completed" if title in completed_set else "not_started"
        steps_with_status.append(
            RoadmapStepWithStatus(
                step_number=raw.get("step_number", 0),
                title=title,
                description=raw.get("description", ""),
                difficulty=raw.get("difficulty", "beginner"),
                estimated_time=raw.get("estimated_time", ""),
                concepts=raw.get("concepts", []),
                video_urls=raw.get("video_urls", []),
                resources=raw.get("resources", []),
                prerequisites=raw.get("prerequisites", []),
                status=status,
            )
        )

    return RoadmapDetailResponse(
        session_id=session_id,
        goal=session.get("goal", ""),
        steps=steps_with_status,
        progress=RoadmapProgressResponse(
            progress=progress_data["progress"],
            completed=progress_data["completed"],
            total=progress_data["total"],
            remaining=progress_data["remaining"],
            completed_steps=list(session.get("completed_steps", [])),
        ),
    )


@router.post("/{session_id}/complete", response_model=RoadmapProgressResponse)
def complete_steps(session_id: str, data: CompleteStepsRequest):
    """
    POST /roadmap/{session_id}/complete

    Mark one or more roadmap steps as completed and return updated progress.
    """
    session = get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found.",
        )

    roadmap_titles = {s.get("title", "") for s in session.get("roadmap", [])}
    invalid = [t for t in data.completed_steps if t not in roadmap_titles]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown step titles: {invalid}. Valid titles: {sorted(roadmap_titles)}",
        )

    mark_steps_completed(session_id, data.completed_steps)
    progress_data = get_progress(session_id)
    updated_session = get_session(session_id)

    logger.info(f"Session {session_id}: marked {data.completed_steps} as completed")

    return RoadmapProgressResponse(
        progress=progress_data["progress"],
        completed=progress_data["completed"],
        total=progress_data["total"],
        remaining=progress_data["remaining"],
        completed_steps=list(updated_session.get("completed_steps", [])),
    )


@router.get("/{session_id}/progress", response_model=RoadmapProgressResponse)
def get_roadmap_progress(session_id: str):
    """
    GET /roadmap/{session_id}/progress

    Get a summary of the user's progress through their roadmap.
    """
    session = get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found.",
        )

    progress_data = get_progress(session_id)

    return RoadmapProgressResponse(
        progress=progress_data["progress"],
        completed=progress_data["completed"],
        total=progress_data["total"],
        remaining=progress_data["remaining"],
        completed_steps=list(session.get("completed_steps", [])),
    )


@router.post("/regenerate", response_model=RoadmapDetailResponse)
def regenerate_roadmap(data: RegenerateRequest):
    """
    POST /roadmap/regenerate

    Re-generate the roadmap for an existing session (e.g. if user changes their goal
    or wants a fresh plan). Previously recommended videos are reused as context.
    """
    session = get_session(data.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{data.session_id}' not found. Call POST /recommend first.",
        )

    goal = data.goal or session.get("goal", "")
    if not goal:
        raise HTTPException(status_code=400, detail="Goal is required.")

    existing_videos = session.get("recommended_videos", [])
    new_roadmap = generate_roadmap(goal, existing_videos)
    set_roadmap(data.session_id, new_roadmap)

    # Reset completed steps on regeneration
    session["completed_steps"] = []
    progress_data = get_progress(data.session_id)

    steps_with_status = [
        RoadmapStepWithStatus(
            step_number=s.get("step_number", 0),
            title=s.get("title", ""),
            description=s.get("description", ""),
            difficulty=s.get("difficulty", "beginner"),
            estimated_time=s.get("estimated_time", ""),
            concepts=s.get("concepts", []),
            video_urls=s.get("video_urls", []),
            resources=s.get("resources", []),
            prerequisites=s.get("prerequisites", []),
            status="not_started",
        )
        for s in new_roadmap
    ]

    logger.info(f"Regenerated roadmap for session {data.session_id} — goal: '{goal}'")

    return RoadmapDetailResponse(
        session_id=data.session_id,
        goal=goal,
        steps=steps_with_status,
        progress=RoadmapProgressResponse(
            progress=progress_data["progress"],
            completed=progress_data["completed"],
            total=progress_data["total"],
            remaining=progress_data["remaining"],
            completed_steps=[],
        ),
    )
