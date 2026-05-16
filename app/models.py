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
    difficulty: str = "beginner"  # beginner / intermediate / advanced
    estimated_time: str = ""     # e.g. "2-3 hours"
    concepts: list[str] = Field(default_factory=list)
    video_urls: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)       # docs, articles, exercises
    prerequisites: list[str] = Field(default_factory=list)   # titles of required prior steps


class RoadmapProgressResponse(BaseModel):
    """Detailed progress summary for a session's roadmap"""
    progress: str = "0%"             # human-readable, e.g. "60%"
    completed: int = 0
    total: int = 0
    remaining: int = 0
    completed_steps: list[str] = Field(default_factory=list)


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
