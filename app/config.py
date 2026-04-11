"""
Resync AI Backend — Configuration
Loads environment variables and defines application constants.
"""

import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ─── API Keys ────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ─── LLM Settings ────────────────────────────────────────────
PRIMARY_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "llama-3.1-8b-instant"
LLM_TEMPERATURE = 0.4
LLM_MAX_TOKENS = 4096
LLM_TIMEOUT = 30  # seconds

# ─── YouTube Settings ────────────────────────────────────────
MAX_SEARCH_RESULTS_PER_QUERY = 6
MAX_VIDEOS_TO_PROCESS = 8     # transcripts to fetch
MAX_VIDEOS_TO_RETURN = 5      # final recommendations
MAX_TRANSCRIPT_CHARS = 2000   # per video transcript limit
NUM_SEARCH_QUERIES = 3        # LLM-generated search queries

# Set to "true" to skip transcript fetching (useful for cloud deployments
# where YouTube blocks transcript requests from cloud-provider IPs).
SKIP_TRANSCRIPTS = os.getenv("SKIP_TRANSCRIPTS", "false").lower() in ("true", "1", "yes")

# ─── CORS Settings ───────────────────────────────────────────
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8000",
    "https://resync-liard.vercel.app",
    "*",  # allow all for development — restrict in production
]
