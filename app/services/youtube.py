"""
Resync AI Backend — YouTube Service
Handles video search and transcript extraction.
Uses youtube-search-python (no API key) and youtube-transcript-api.
"""

import logging
from typing import Optional
from youtubesearchpython import VideosSearch
from youtube_transcript_api import YouTubeTranscriptApi

from app.config import MAX_SEARCH_RESULTS_PER_QUERY, MAX_TRANSCRIPT_CHARS

logger = logging.getLogger(__name__)


def search_videos(query: str, max_results: int = MAX_SEARCH_RESULTS_PER_QUERY) -> list[dict]:
    """
    Search YouTube for videos matching the query.
    Returns a list of dicts with video metadata.
    """
    try:
        search = VideosSearch(query, limit=max_results)
        raw_results = search.result().get("result", [])

        videos = []
        for item in raw_results:
            video_id = item.get("id", "")
            title = item.get("title", "")
            link = item.get("link", f"https://www.youtube.com/watch?v={video_id}")
            channel = item.get("channel", {}).get("name", "Unknown")
            duration = item.get("duration", "")
            description = item.get("descriptionSnippet", [])

            # descriptionSnippet is a list of text fragments
            desc_text = ""
            if isinstance(description, list):
                desc_text = " ".join(
                    seg.get("text", "") for seg in description if isinstance(seg, dict)
                )
            elif isinstance(description, str):
                desc_text = description

            view_count = ""
            vc = item.get("viewCount", {})
            if isinstance(vc, dict):
                view_count = vc.get("short", "")

            videos.append({
                "video_id": video_id,
                "title": title,
                "url": link,
                "channel": channel,
                "duration": duration,
                "description": desc_text,
                "view_count": view_count,
            })

        logger.info(f"YouTube search for '{query}': found {len(videos)} results")
        return videos

    except Exception as e:
        logger.error(f"YouTube search failed for '{query}': {e}")
        return []


def extract_transcript(video_id: str, max_chars: int = MAX_TRANSCRIPT_CHARS) -> Optional[str]:
    """
    Fetch auto-generated or manual transcript from a YouTube video.
    Returns concatenated transcript text, truncated to max_chars.
    """
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Try to get English transcript first
        transcript = None
        try:
            transcript = transcript_list.find_transcript(["en"])
        except Exception:
            # Fall back to any auto-generated transcript
            try:
                generated = transcript_list.find_generated_transcript(["en"])
                transcript = generated
            except Exception:
                # Try the first available and translate
                for t in transcript_list:
                    try:
                        transcript = t.translate("en")
                        break
                    except Exception:
                        continue

        if transcript is None:
            logger.warning(f"No transcript available for video {video_id}")
            return None

        # Fetch the transcript data
        fetched = transcript.fetch()

        # Concatenate all text segments
        full_text = " ".join(
            snippet.text for snippet in fetched
        )

        # Truncate
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + "..."

        logger.info(f"Transcript for {video_id}: {len(full_text)} chars")
        return full_text

    except Exception as e:
        logger.debug(f"Transcript extraction failed for {video_id}: {e}")
        return None


def search_and_extract(queries: list[str], max_per_query: int = MAX_SEARCH_RESULTS_PER_QUERY) -> list[dict]:
    """
    Run multiple searches, deduplicate, and extract transcripts for each video.
    Returns enriched video dicts with 'transcript' field.
    """
    seen_ids = set()
    all_videos = []

    for query in queries:
        results = search_videos(query, max_per_query)
        for video in results:
            vid = video["video_id"]
            if vid and vid not in seen_ids:
                seen_ids.add(vid)

                # Try to extract transcript
                transcript = extract_transcript(vid)
                video["transcript"] = transcript
                video["has_transcript"] = transcript is not None

                all_videos.append(video)

    logger.info(f"Total unique videos found: {len(all_videos)}, "
                f"with transcripts: {sum(1 for v in all_videos if v['has_transcript'])}")
    return all_videos
