"""
Resync AI Backend — Weakness Routes
Dedicated APIRouter for all /weakness endpoints.

Endpoints:
    POST /weakness/{session_id}/unsolved  — log a new unsolved question
    GET  /weakness/{session_id}           — list all weakness items for a session
    POST /weakness/{session_id}/resolve   — update the status of a weakness item
"""

import logging
from fastapi import APIRouter, HTTPException

from app.models import (
    AddUnsolvedRequest,
    ResolveWeaknessRequest,
    WeaknessItem,
    WeaknessListResponse,
)
from app.services.memory import (
    get_session,
    add_unsolved_question,
    get_unsolved_questions,
    resolve_unsolved_question,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/weakness", tags=["Weakness"])

# Valid status values — mirrors WeaknessStatus in memory.py
_VALID_STATUSES = {"unsolved", "reviewed", "resolved"}


# ─── Endpoints ────────────────────────────────────────────────

@router.post("/{session_id}/unsolved", response_model=WeaknessItem, status_code=201)
def add_weakness(session_id: str, data: AddUnsolvedRequest):
    """
    POST /weakness/{session_id}/unsolved

    Log a new unsolved question or weak concept for the session.
    Returns the created item with its generated ID, timestamps, and
    initial status of 'unsolved'.
    """
    if get_session(session_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found. Call POST /recommend first.",
        )

    item = add_unsolved_question(
        session_id,
        {
            "question": data.question,
            "notes": data.notes,
            "tags": data.tags,
        },
    )

    if item is None:
        raise HTTPException(status_code=500, detail="Failed to store weakness item.")

    logger.info(f"Session {session_id}: weakness item created id={item['id']}")
    return WeaknessItem(**item)


@router.get("/{session_id}", response_model=WeaknessListResponse)
def list_weaknesses(session_id: str, status: str | None = None):
    """
    GET /weakness/{session_id}?status=<filter>

    Retrieve all weakness/unsolved-question items for the session.
    Optionally filter by status: 'unsolved', 'reviewed', or 'resolved'.
    Response includes per-status counts and the (optionally filtered) item list.
    """
    if get_session(session_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found. Call POST /recommend first.",
        )

    if status and status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{status}'. Must be one of: {sorted(_VALID_STATUSES)}",
        )

    all_items = get_unsolved_questions(session_id)

    # Aggregate counts across all items regardless of filter
    counts = {"unsolved": 0, "reviewed": 0, "resolved": 0}
    for it in all_items:
        s = it.get("status", "unsolved")
        if s in counts:
            counts[s] += 1

    # Apply optional status filter
    filtered = [it for it in all_items if it.get("status") == status] if status else all_items

    return WeaknessListResponse(
        session_id=session_id,
        total=len(all_items),
        unsolved=counts["unsolved"],
        reviewed=counts["reviewed"],
        resolved=counts["resolved"],
        items=[WeaknessItem(**it) for it in filtered],
    )


@router.post("/{session_id}/resolve", response_model=WeaknessItem)
def resolve_weakness(session_id: str, data: ResolveWeaknessRequest):
    """
    POST /weakness/{session_id}/resolve

    Update the status of an existing weakness item.
    Body must include 'question_id' and optionally 'status'
    ('unsolved', 'reviewed', or 'resolved'; defaults to 'resolved').
    """
    if get_session(session_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found. Call POST /recommend first.",
        )

    if data.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{data.status}'. Must be one of: {sorted(_VALID_STATUSES)}",
        )

    updated = resolve_unsolved_question(session_id, data.question_id, data.status)  # type: ignore[arg-type]

    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"Weakness item '{data.question_id}' not found in session '{session_id}'.",
        )

    logger.info(f"Session {session_id}: weakness {data.question_id} → '{data.status}'")
    return WeaknessItem(**updated)
