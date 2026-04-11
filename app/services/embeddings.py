"""
Resync AI Backend — Video Ranking Service
Uses Groq LLM for semantic relevance ranking of videos.

Replaces the previous sentence-transformers approach which required ~2GB RAM
to load locally — infeasible on Render's free tier (512MB).
"""

import json
import re
import logging
from app.config import GROQ_API_KEY, PRIMARY_MODEL, FALLBACK_MODEL, LLM_TIMEOUT

logger = logging.getLogger(__name__)


def _call_groq_ranking(prompt: str) -> str | None:
    """Call Groq LLM for ranking. Separate from main._call_groq to avoid circular imports."""
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set — skipping LLM ranking")
        return None

    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)

    for model_name in [PRIMARY_MODEL, FALLBACK_MODEL]:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # low temperature for consistent ranking
                max_tokens=1024,
                timeout=LLM_TIMEOUT,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Groq ranking with {model_name} failed: {e}")
            continue

    return None


def _parse_ranking(raw: str | None) -> list[int] | None:
    """Extract a list of indices from LLM ranking output."""
    if not raw:
        return None
    try:
        cleaned = re.sub(r"```json|```", "", raw).strip()
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict) and "ranking" in parsed:
            return parsed["ranking"]
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        # Try to extract numbers from the output
        numbers = re.findall(r'\d+', raw)
        if numbers:
            return [int(n) for n in numbers]
    return None


def rank_videos(goal: str, videos: list[dict], top_n: int = 5) -> list[dict]:
    """
    Rank videos by relevance to the user's learning goal.

    Uses Groq LLM to judge which videos are most relevant based on
    title + description + transcript snippet. Falls back to simple
    keyword matching if LLM is unavailable.

    Returns the top_n most relevant videos, sorted by relevance score.
    """
    if not videos:
        return []

    if len(videos) <= top_n:
        # No ranking needed — just score them all equally
        for i, v in enumerate(videos):
            v["relevance_score"] = 1.0 - (i * 0.01)
        return videos

    # Build video summaries for ranking
    video_list = []
    for i, v in enumerate(videos):
        parts = [v.get("title", "")]
        desc = v.get("description", "")
        if desc:
            parts.append(desc[:150])
        transcript = v.get("transcript", "")
        if transcript:
            parts.append(transcript[:200])
        video_list.append(f"[{i}] {' | '.join(parts)}")

    videos_text = "\n".join(video_list)

    prompt = f"""You are ranking YouTube videos by relevance to a learning goal.

Learning goal: "{goal}"

Videos:
{videos_text}

Rank the top {top_n} most relevant videos for learning this topic.
Return ONLY valid JSON: {{"ranking": [indices in order of relevance]}}

Example: {{"ranking": [2, 0, 5, 1, 3]}}"""

    ranking = _parse_ranking(_call_groq_ranking(prompt))

    if ranking:
        # Use LLM ranking
        result = []
        seen = set()
        for rank, idx in enumerate(ranking):
            if idx < len(videos) and idx not in seen:
                seen.add(idx)
                video_copy = videos[idx].copy()
                video_copy["relevance_score"] = 1.0 - (rank * 0.1)
                result.append(video_copy)
                if len(result) >= top_n:
                    break

        # If LLM didn't return enough, pad with remaining videos
        if len(result) < top_n:
            for i, v in enumerate(videos):
                if i not in seen:
                    video_copy = v.copy()
                    video_copy["relevance_score"] = 0.3
                    result.append(video_copy)
                    if len(result) >= top_n:
                        break

        logger.info(f"Ranked {len(videos)} videos → top {len(result)} by LLM relevance to '{goal}'")
        return result
    else:
        # Fallback: simple keyword overlap scoring
        logger.info("LLM ranking unavailable — falling back to keyword matching")
        return _keyword_rank(goal, videos, top_n)


def _keyword_rank(goal: str, videos: list[dict], top_n: int) -> list[dict]:
    """Fallback ranking using simple keyword overlap."""
    goal_words = set(goal.lower().split())

    scored = []
    for v in videos:
        text = f"{v.get('title', '')} {v.get('description', '')}".lower()
        text_words = set(text.split())
        overlap = len(goal_words & text_words)
        score = overlap / max(len(goal_words), 1)

        video_copy = v.copy()
        video_copy["relevance_score"] = round(score, 3)
        scored.append(video_copy)

    scored.sort(key=lambda x: x["relevance_score"], reverse=True)

    # Deduplicate by channel — keep at most 2 videos per channel
    channel_count = {}
    deduplicated = []
    for v in scored:
        ch = v.get("channel", "Unknown")
        channel_count[ch] = channel_count.get(ch, 0) + 1
        if channel_count[ch] <= 2:
            deduplicated.append(v)

    result = deduplicated[:top_n]
    logger.info(f"Keyword-ranked {len(videos)} videos → top {len(result)} for '{goal}'")
    return result
