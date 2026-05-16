"""
Resync AI Backend — Session Memory
In-memory user session store for context-aware recommendations.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, Literal

logger = logging.getLogger(__name__)

# ─── In-Memory Store ──────────────────────────────────────────
_sessions: dict[str, dict] = {}


def create_session(goal: str, user_id: Optional[str] = None) -> str:
    """Create a new user session or update existing one."""
    session_id = user_id or str(uuid.uuid4())

    if session_id in _sessions:
        # Update existing session
        session = _sessions[session_id]
        session["goal"] = goal
        session["interaction_count"] += 1
        session["updated_at"] = datetime.now().isoformat()
        logger.info(f"Updated session {session_id} (interaction #{session['interaction_count']})")
    else:
        # Create new session
        _sessions[session_id] = {
            "session_id": session_id,
            "goal": goal,
            "recommended_videos": [],
            "recommended_video_urls": set(),
            "roadmap": [],
            "completed_steps": [],
            "unsolved_questions": [],
            "interaction_count": 1,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        logger.info(f"Created new session {session_id}")

    return session_id


def get_session(session_id: str) -> Optional[dict]:
    """Retrieve a session by ID."""
    return _sessions.get(session_id)


def add_recommended_videos(session_id: str, videos: list[dict]):
    """Track videos that have been recommended to avoid repetition."""
    session = _sessions.get(session_id)
    if session is None:
        return

    for v in videos:
        url = v.get("url", "")
        if url:
            session["recommended_video_urls"].add(url)
            session["recommended_videos"].append({
                "title": v.get("title", ""),
                "url": url,
                "recommended_at": datetime.now().isoformat(),
            })


def set_roadmap(session_id: str, roadmap: list[dict]):
    """Store the generated roadmap."""
    session = _sessions.get(session_id)
    if session is None:
        return
    session["roadmap"] = roadmap
    session["updated_at"] = datetime.now().isoformat()


def mark_steps_completed(session_id: str, step_titles: list[str]):
    """Mark roadmap steps as completed."""
    session = _sessions.get(session_id)
    if session is None:
        return

    for title in step_titles:
        if title not in session["completed_steps"]:
            session["completed_steps"].append(title)

    session["updated_at"] = datetime.now().isoformat()
    logger.info(f"Session {session_id}: {len(session['completed_steps'])} steps completed")


def get_previously_recommended_urls(session_id: str) -> set:
    """Get URLs of previously recommended videos."""
    session = _sessions.get(session_id)
    if session is None:
        return set()
    return session.get("recommended_video_urls", set())


def get_progress(session_id: str) -> dict:
    """Calculate user progress through the roadmap."""
    session = _sessions.get(session_id)
    if session is None:
        return {"progress": "0%", "completed": 0, "total": 0, "remaining": 0}

    total = len(session.get("roadmap", []))
    completed = len(session.get("completed_steps", []))
    remaining = max(0, total - completed)
    pct = f"{int((completed / total) * 100)}%" if total > 0 else "0%"

    return {
        "progress": pct,
        "completed": completed,
        "total": total,
        "remaining": remaining,
    }


# ─── Weakness / Unsolved Question Helpers ─────────────────────

WeaknessStatus = Literal["unsolved", "reviewed", "resolved"]


def add_unsolved_question(session_id: str, question_data: dict) -> Optional[dict]:
    """
    Add a weakness / unsolved-question item to the session.

    Expected keys in question_data:
        question (str)  — required
        notes    (str)  — optional, default ""
        tags     (list) — optional, default []

    Returns the stored item (with auto-generated id, status, attempted_at),
    or None if the session does not exist.
    """
    session = _sessions.get(session_id)
    if session is None:
        return None

    item: dict = {
        "id": str(uuid.uuid4()),
        "question": question_data.get("question", ""),
        "notes": question_data.get("notes", ""),
        "weakness_tags": question_data.get("tags", []),
        "attempted_at": datetime.now().isoformat(),
        "status": "unsolved",
    }

    session.setdefault("unsolved_questions", []).append(item)
    session["updated_at"] = datetime.now().isoformat()
    logger.info(f"Session {session_id}: added unsolved question id={item['id']}")
    return item


def get_unsolved_questions(session_id: str) -> list[dict]:
    """Return all weakness/unsolved-question items for a session."""
    session = _sessions.get(session_id)
    if session is None:
        return []
    return session.get("unsolved_questions", [])


def resolve_unsolved_question(
    session_id: str,
    question_id: str,
    new_status: WeaknessStatus = "resolved",
) -> Optional[dict]:
    """
    Update the status of a weakness item.

    new_status must be one of: 'unsolved', 'reviewed', 'resolved'

    Returns the updated item, or None if the session/item is not found.
    """
    session = _sessions.get(session_id)
    if session is None:
        return None

    for item in session.get("unsolved_questions", []):
        if item["id"] == question_id:
            item["status"] = new_status
            session["updated_at"] = datetime.now().isoformat()
            logger.info(
                f"Session {session_id}: question {question_id} → status='{new_status}'"
            )
            return item

    return None
