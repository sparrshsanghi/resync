"""
Resync AI Backend — Roadmap Service
Handles LLM-powered roadmap generation with rich step metadata.
"""

import json
import re
import logging

from app.config import (
    GROQ_API_KEY,
    PRIMARY_MODEL,
    FALLBACK_MODEL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    LLM_TIMEOUT,
)

logger = logging.getLogger(__name__)


# ─── LLM Helper ───────────────────────────────────────────────

def _call_groq(prompt: str) -> str | None:
    """Call Groq LLM with automatic fallback to smaller model."""
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set — skipping roadmap LLM call")
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
        logger.warning("Failed to parse roadmap LLM output as JSON")
        return None


# ─── Roadmap Generation ───────────────────────────────────────

def generate_roadmap(goal: str, videos: list[dict]) -> list[dict]:
    """
    Use LLM to generate a rich, step-by-step learning roadmap.

    Each step includes:
      - step_number, title, description, difficulty
      - concepts (list), video_urls (list)
      - estimated_time (e.g. "2-3 hours")
      - resources (list of strings — books, docs, practice links)
      - prerequisites (list of step titles required before this one)
    """
    video_summaries = []
    for v in videos[:6]:
        video_summaries.append(f"- {v.get('title', '')} ({v.get('url', '')})")
    videos_text = "\n".join(video_summaries) if video_summaries else "No videos available."

    prompt = f"""You are an expert curriculum designer. Create a detailed, step-by-step learning roadmap for:
"{goal}"

Available video resources:
{videos_text}

Requirements:
- Generate 5-7 steps covering the full learning journey from beginner to advanced.
- Each step must have a realistic estimated_time.
- Include practical resources (documentation links, exercises, or project ideas) as resources.
- Specify which earlier steps are prerequisites for each step.
- Assign video_urls from the available resources above where relevant.

Return ONLY valid JSON with NO extra text:
{{
  "roadmap": [
    {{
      "step_number": 1,
      "title": "Step title",
      "description": "Clear explanation of what to learn in this step and why it matters",
      "difficulty": "beginner",
      "estimated_time": "2-3 hours",
      "concepts": ["concept1", "concept2", "concept3"],
      "video_urls": ["url1"],
      "resources": ["https://docs.example.com", "Practice: build a small project"],
      "prerequisites": []
    }}
  ]
}}

Difficulty must be one of: beginner, intermediate, advanced."""

    parsed = _parse_json(_call_groq(prompt))
    if parsed and "roadmap" in parsed:
        steps = parsed["roadmap"]
        # Normalise — ensure all expected fields exist
        for step in steps:
            step.setdefault("estimated_time", "1-2 hours")
            step.setdefault("resources", [])
            step.setdefault("prerequisites", [])
            step.setdefault("concepts", [])
            step.setdefault("video_urls", [])
            step.setdefault("difficulty", "beginner")
        logger.info(f"Generated {len(steps)}-step roadmap for '{goal}'")
        return steps

    # ── Fallback roadmap ──────────────────────────────────────
    logger.warning(f"Falling back to default roadmap for '{goal}'")
    return _default_roadmap(goal, videos)


def _default_roadmap(goal: str, videos: list[dict]) -> list[dict]:
    """Return a sensible 5-step fallback roadmap when LLM is unavailable."""
    video_urls = [v.get("url", "") for v in videos[:2] if v.get("url")]

    return [
        {
            "step_number": 1,
            "title": "Understand the Fundamentals",
            "description": f"Get a solid foundation in the core concepts of {goal}. Focus on understanding the 'why' before the 'how'.",
            "difficulty": "beginner",
            "estimated_time": "2-3 hours",
            "concepts": ["core concepts", "terminology", "mental models"],
            "video_urls": video_urls[:1],
            "resources": ["Official documentation", "Beginner-friendly articles"],
            "prerequisites": [],
        },
        {
            "step_number": 2,
            "title": "Set Up Your Environment",
            "description": "Install all necessary tools, configure your workspace, and run your first 'hello world' example.",
            "difficulty": "beginner",
            "estimated_time": "1-2 hours",
            "concepts": ["installation", "configuration", "tooling"],
            "video_urls": [],
            "resources": ["Setup guides", "Official getting-started tutorial"],
            "prerequisites": ["Understand the Fundamentals"],
        },
        {
            "step_number": 3,
            "title": "Learn Core Patterns & Syntax",
            "description": "Dive into the primary patterns, syntax, and idioms you'll use day-to-day.",
            "difficulty": "beginner",
            "estimated_time": "4-6 hours",
            "concepts": ["syntax", "patterns", "best practices"],
            "video_urls": video_urls[1:],
            "resources": ["Interactive exercises", "Cheatsheet"],
            "prerequisites": ["Set Up Your Environment"],
        },
        {
            "step_number": 4,
            "title": "Build a Hands-On Project",
            "description": f"Apply everything learned by building a small but complete project using {goal}.",
            "difficulty": "intermediate",
            "estimated_time": "6-8 hours",
            "concepts": ["application", "debugging", "project structure"],
            "video_urls": [],
            "resources": ["Project ideas list", "Community forums"],
            "prerequisites": ["Learn Core Patterns & Syntax"],
        },
        {
            "step_number": 5,
            "title": "Explore Advanced Topics",
            "description": "Push beyond the basics — performance, edge cases, advanced patterns, and real-world best practices.",
            "difficulty": "advanced",
            "estimated_time": "8-10 hours",
            "concepts": ["advanced patterns", "optimisation", "real-world usage"],
            "video_urls": [],
            "resources": ["Advanced documentation", "Open-source projects to study"],
            "prerequisites": ["Build a Hands-On Project"],
        },
    ]
