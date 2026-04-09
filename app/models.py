"""
Resync AI Backend — Pydantic Models
Request/Response schemas for all API endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ─── Request Models ───────────────────────────────────────────

class RecommendRequest(BaseModel):
    """Request body for POST /recommend"""
    goal: str = Field(..., min_length=3, max_length=500, description="The learning goal")
    user_id: Optional[str] = Field(None, description="Optional user/session ID for context")
    max_videos: int = Field(5, ge=1, le=10, description="Max videos to return")


class NextStepRequest(BaseModel):
    """Request body for POST /next-step"""
    user_id: str = Field(..., description="Session ID from previous /recommend call")
    completed_steps: list[str] = Field(default_factory=list, description="Steps the user has completed")


# ─── Response Models ──────────────────────────────────────────

class VideoResult(BaseModel):
    """A single recommended video"""
    title: str
    url: str
    description: str = ""
    reason: str = ""
    key_concepts: list[str] = Field(default_factory=list)
    difficulty_level: str = "beginner"  # beginner / intermediate / advanced
    channel: str = ""
    duration: str = ""


class RoadmapStep(BaseModel):
    """A single step in the learning roadmap"""
    step_number: int
    title: str
    description: str
    difficulty: str = "beginner"
    concepts: list[str] = Field(default_factory=list)
    video_urls: list[str] = Field(default_factory=list)


class RecommendResponse(BaseModel):
    """Response from POST /recommend"""
    videos: list[VideoResult] = Field(default_factory=list)
    roadmap: list[RoadmapStep] = Field(default_factory=list)
    session_id: str = ""
    goal: str = ""


class NextStepResponse(BaseModel):
    """Response from POST /next-step"""
    next_videos: list[VideoResult] = Field(default_factory=list)
    next_step: Optional[RoadmapStep] = None
    progress: str = "0%"
    remaining_steps: int = 0
