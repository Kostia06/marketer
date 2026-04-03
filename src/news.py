import re
import tempfile
import requests
from src.config import logger

HACKERNEWS_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
HACKERNEWS_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"


def fetch_top_stories(count=10) -> list[dict]:
    response = requests.get(HACKERNEWS_TOP, timeout=10)
    story_ids = response.json()[:count]

    stories = []
    for story_id in story_ids:
        item = requests.get(HACKERNEWS_ITEM.format(story_id), timeout=10).json()
        if item.get("url") and item.get("title"):
            stories.append({
                "title": item["title"],
                "url": item["url"],
                "score": item.get("score", 0),
            })
    return stories


def fetch_article_image(url: str) -> str | None:
    try:
        response = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0"
        })
        for pattern in [
            r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']',
            r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']',
        ]:
            match = re.search(pattern, response.text, re.IGNORECASE)
            if match:
                return match.group(1)
    except Exception as e:
        logger.error(f"Failed to fetch og:image from {url}: {e}")
    return None


def download_image(url: str) -> str | None:
    try:
        response = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0"
        })
        content_type = response.headers.get("content-type", "")
        if response.status_code != 200 or "image" not in content_type:
            return None
        suffix = ".png" if "png" in content_type else ".jpg"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(response.content)
        tmp.close()
        return tmp.name
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
    return None
