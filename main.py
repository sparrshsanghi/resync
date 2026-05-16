"""
Resync AI Backend — Main Application
FastAPI entry point that wires together all services.
"""

import json
import re
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    GROQ_API_KEY,
    PRIMARY_MODEL,
    FALLBACK_MODEL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    LLM_TIMEOUT,
    ALLOWED_ORIGINS,
    MAX_VIDEOS_TO_RETURN,
    NUM_SEARCH_QUERIES,
)
from app.models import RecommendRequest, RecommendResponse, NextStepRequest, NextStepResponse
from app.services.embeddings import rank_videos
from app.services.youtube import search_and_extract
from app.services.roadmap import generate_roadmap
from app.services.memory import (
    create_session,
    get_session,
    add_recommended_videos,
    set_roadmap,
    mark_steps_completed,
    get_previously_recommended_urls,
    get_progress,
)
from app.routes.roadmap import router as roadmap_router

# ─── Logging ──────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s │ %(name)s │ %(levelname)s │ %(message)s")
logger = logging.getLogger("resync")

# ─── App ──────────────────────────────────────────────────────
app = FastAPI(
    title="Resync AI",
    description="Agentic learning assistant — YouTube discovery + LLM roadmaps",
    version="1.0.0",
)

# ─── CORS ─────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────
app.include_router(roadmap_router)


# ─── Groq Helper ─────────────────────────────────────────────
def _call_groq(prompt: str) -> str | None:
    """Call Groq LLM with automatic fallback to smaller model."""
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set — skipping LLM call")
        return None

    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)

    for model_name in [PRIMARY_MODEL, FALLBACK_MODEL]:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                timeout=LLM_TIMEOUT,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Groq model {model_name} failed: {e}")
            continue

    return None


def _parse_json(raw: str | None) -> dict | None:
    """Best-effort extraction of JSON from LLM output."""
    if not raw:
        return None
    try:
        cleaned = re.sub(r"```json|```", "", raw).strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM output as JSON")
        return None


# ─── Core Logic ───────────────────────────────────────────────
def _generate_search_queries(goal: str) -> list[str]:
    """Use LLM to generate diverse YouTube search queries for the goal."""
    prompt = f"""Generate {NUM_SEARCH_QUERIES} diverse YouTube search queries for someone learning:
"{goal}"

Return ONLY valid JSON:
{{"queries": ["query1", "query2", "query3"]}}"""

    parsed = _parse_json(_call_groq(prompt))
    if parsed and "queries" in parsed:
        return parsed["queries"][:NUM_SEARCH_QUERIES]

    # Fallback: use the goal directly
    return [goal, f"{goal} tutorial", f"{goal} explained"]


# _generate_roadmap has been moved to app/services/roadmap.py — use generate_roadmap() directly.


# ─── API Routes ───────────────────────────────────────────────

@app.post("/recommend", response_model=RecommendResponse)
def recommend_api(data: RecommendRequest):
    """Main recommendation endpoint — search, rank, and generate roadmap."""
    goal = data.goal
    logger.info(f"Recommendation request: '{goal}'")

    # 1. Create / resume session
    session_id = create_session(goal, data.user_id)
    prev_urls = get_previously_recommended_urls(session_id)

    # 2. Generate search queries via LLM
    queries = _generate_search_queries(goal)
    logger.info(f"Search queries: {queries}")

    # 3. Search YouTube + extract transcripts
    raw_videos = search_and_extract(queries)

    # 4. Filter out previously recommended videos
    fresh_videos = [v for v in raw_videos if v.get("url") not in prev_urls]
    if not fresh_videos:
        fresh_videos = raw_videos  # fallback to all if everything was recommended before

    # 5. Rank by semantic similarity
    top_n = data.max_videos or MAX_VIDEOS_TO_RETURN
    ranked = rank_videos(goal, fresh_videos, top_n=top_n)

    # 6. Generate roadmap
    roadmap = generate_roadmap(goal, ranked)

    # 7. Store in session
    add_recommended_videos(session_id, ranked)
    set_roadmap(session_id, roadmap)

    # 8. Build response
    video_results = []
    for v in ranked:
        video_results.append({
            "title": v.get("title", ""),
            "url": v.get("url", ""),
            "description": v.get("description", ""),
            "reason": f"Relevance score: {v.get('relevance_score', 0):.2f}",
            "key_concepts": [],
            "difficulty_level": "beginner",
            "channel": v.get("channel", ""),
            "duration": v.get("duration", ""),
        })

    return RecommendResponse(
        videos=video_results,
        roadmap=roadmap,
        session_id=session_id,
        goal=goal,
    )


@app.post("/next-step", response_model=NextStepResponse)
def next_step_api(data: NextStepRequest):
    """Get the next step in the learning roadmap after completing steps."""
    session = get_session(data.user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found. Call /recommend first.")

    # Mark completed steps
    if data.completed_steps:
        mark_steps_completed(data.user_id, data.completed_steps)

    # Get progress
    progress = get_progress(data.user_id)

    # Find next uncompleted step
    roadmap = session.get("roadmap", [])
    completed = set(session.get("completed_steps", []))
    next_step = None
    for step in roadmap:
        title = step.get("title", "")
        if title not in completed:
            next_step = step
            break

    return NextStepResponse(
        next_videos=[],
        next_step=next_step,
        progress=progress["progress"],
        remaining_steps=progress["remaining"],
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def home():
    return {"message": "Resync AI running "}
