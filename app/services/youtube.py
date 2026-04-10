"""
Resync AI Backend — YouTube Service
Handles video search and transcript extraction.
Uses yt-dlp for search and youtube-transcript-api for transcripts.
"""

import logging
from typing import Optional
import concurrent.futures
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

from app.config import MAX_SEARCH_RESULTS_PER_QUERY, MAX_TRANSCRIPT_CHARS, MAX_VIDEOS_TO_PROCESS, SKIP_TRANSCRIPTS

logger = logging.getLogger(__name__)

# Track whether transcripts are being IP-blocked so we can fast-fail
_transcript_blocked = False


def _format_duration(seconds) -> str:
    """Convert duration in seconds to human-readable format."""
    if not seconds:
        return ""
    try:
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"
    except (ValueError, TypeError):
        return ""


def _format_views(count) -> str:
    """Convert view count to short format."""
    if not count:
        return ""
    try:
        count = int(count)
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M views"
        if count >= 1_000:
            return f"{count / 1_000:.1f}K views"
        return f"{count} views"
    except (ValueError, TypeError):
        return ""


def search_videos(query: str, max_results: int = MAX_SEARCH_RESULTS_PER_QUERY) -> list[dict]:
    """
    Search YouTube for videos matching the query using yt-dlp.
    Returns a list of dicts with video metadata.
    """
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'skip_download': True,
            'no_check_certificates': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(
                f"ytsearch{max_results}:{query}",
                download=False,
            )

        videos = []
        for entry in (results or {}).get('entries', []):
            if not entry:
                continue
            video_id = entry.get('id', '')
            url = (
                entry.get('url', '')
                or entry.get('webpage_url', '')
                or f"https://www.youtube.com/watch?v={video_id}"
            )

            # Ensure URL is a full YouTube watch URL
            if url and not url.startswith('http'):
                url = f"https://www.youtube.com/watch?v={video_id}"

            videos.append({
                'video_id': video_id,
                'title': entry.get('title', ''),
                'url': url,
                'channel': entry.get('channel', entry.get('uploader', 'Unknown')) or 'Unknown',
                'duration': _format_duration(entry.get('duration')),
                'description': (entry.get('description', '') or '')[:200],
                'view_count': _format_views(entry.get('view_count')),
            })

        logger.info(f"YouTube search for '{query}': found {len(videos)} results")
        return videos

    except Exception as e:
        logger.error(f"YouTube search failed for '{query}': {e}")
        return []


def extract_transcript(video_id: str, max_chars: int = MAX_TRANSCRIPT_CHARS) -> Optional[str]:
    """
    Fetch auto-generated or manual transcript from a YouTube video.
    Uses youtube-transcript-api v1.x API.
    Returns concatenated transcript text, truncated to max_chars.
    Returns None immediately if transcripts are disabled or IP-blocked.
    """
    global _transcript_blocked

    # Fast-fail if we already know transcripts are blocked or disabled
    if SKIP_TRANSCRIPTS:
        return None
    if _transcript_blocked:
        logger.debug(f"Skipping transcript for {video_id} (IP blocked)")
        return None

    ytt = YouTubeTranscriptApi()

    # Try English first, then fall back to any available language
    for languages in [['en', 'en-US', 'en-GB'], None]:
        try:
            if languages:
                transcript = ytt.fetch(video_id, languages=languages)
            else:
                # Fetch whatever is available — list transcripts and pick the first
                transcript_list = ytt.list(video_id)
                first_transcript = next(iter(transcript_list), None)
                if first_transcript is None:
                    return None
                first_lang = first_transcript.language_code
                transcript = ytt.fetch(video_id, languages=[first_lang])

            full_text = " ".join(snippet.text for snippet in transcript)

            if len(full_text) > max_chars:
                full_text = full_text[:max_chars] + "..."

            logger.info(f"Transcript for {video_id}: {len(full_text)} chars")
            return full_text

        except Exception as e:
            error_name = type(e).__name__

            # Detect IP blocking and enable fast-fail for remaining videos
            if error_name == "RequestBlocked":
                if not _transcript_blocked:
                    logger.warning(
                        f"YouTube is blocking transcript requests from this IP. "
                        f"Disabling transcript fetching for remaining videos. "
                        f"Set SKIP_TRANSCRIPTS=true to suppress this warning. "
                        f"Videos will still be recommended using title + description."
                    )
                    _transcript_blocked = True
                return None

            if languages:
                logger.debug(f"English transcript not available for {video_id}: {error_name}")
                continue
            logger.debug(f"Transcript extraction failed for {video_id}: {error_name}")
            return None

    return None


def search_and_extract(queries: list[str], max_per_query: int = MAX_SEARCH_RESULTS_PER_QUERY, max_total: int = MAX_VIDEOS_TO_PROCESS) -> list[dict]:
    """
    Run multiple searches, deduplicate, and extract transcripts concurrently.
    Returns enriched video dicts with 'transcript' field.
    """
    seen_ids = set()
    all_videos = []

    # 1. Gather all unique videos first (fast)
    for query in queries:
        results = search_videos(query, max_per_query)
        for video in results:
            vid = video["video_id"]
            if vid and vid not in seen_ids:
                seen_ids.add(vid)
                all_videos.append(video)
                if len(all_videos) >= max_total:
                    break
        if len(all_videos) >= max_total:
            break

    # 2. Fetch transcripts concurrently (skipped if SKIP_TRANSCRIPTS or IP-blocked)
    def fetch_and_attach(video):
        transcript = extract_transcript(video["video_id"])
        video["transcript"] = transcript
        video["has_transcript"] = transcript is not None
        return video

    if SKIP_TRANSCRIPTS:
        logger.info("Transcript fetching disabled (SKIP_TRANSCRIPTS=true). Ranking by title + description only.")
        for video in all_videos:
            video["transcript"] = None
            video["has_transcript"] = False
        enriched_videos = all_videos
    else:
        enriched_videos = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_total, 5)) as executor:
            futures = [executor.submit(fetch_and_attach, video) for video in all_videos]
            for future in concurrent.futures.as_completed(futures):
                try:
                    enriched_videos.append(future.result())
                except Exception as e:
                    logger.error(f"Transcript fetch error: {e}")

    transcript_count = sum(1 for v in enriched_videos if v['has_transcript'])
    logger.info(f"Total unique videos processed: {len(enriched_videos)}, with transcripts: {transcript_count}")

    if transcript_count == 0 and not SKIP_TRANSCRIPTS and not _transcript_blocked:
        logger.info("No transcripts available — videos will be ranked using title + description.")

    return enriched_videos
