import re
import random
import tempfile
import requests
from src.config import logger, UNSPLASH_ACCESS_KEY

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


JUNK_IMAGE_PATTERNS = [
    r"logo",
    r"icon",
    r"favicon",
    r"brand",
    r"avatar",
    r"default",
    r"placeholder",
    r"og[-_]?image",
    r"social[-_]?share",
    r"twitter[-_]?card",
    r"github\.com",
    r"gist\.github",
    r"substack\.com.*?/icons/",
    r"substack-post-media.*?_256x256",
    r"medium\.com/_/stat",
    r"gravatar",
    r"cdn\.substack",
    r"substackcdn",
    r"subscribe[-_]?card",
    r"substack\.com",
    r"wp-content/uploads.*?site[-_]?icon",
]

MIN_IMAGE_SIZE = 10_000  # 10KB minimum — logos are usually tiny


def is_junk_image(url: str) -> bool:
    url_lower = url.lower()
    return any(re.search(p, url_lower) for p in JUNK_IMAGE_PATTERNS)


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
                image_url = match.group(1)
                if is_junk_image(image_url):
                    logger.info(f"Skipping junk og:image: {image_url}")
                    return None
                return image_url
    except Exception as e:
        logger.error(f"Failed to fetch og:image from {url}: {e}")
    return None


def search_unsplash(query: str) -> str | None:
    """Search Unsplash for a relevant photo. Returns image URL or None."""
    if not UNSPLASH_ACCESS_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": f"{query} technology coding", "per_page": 3, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error(f"Unsplash search failed: {resp.status_code}")
            return None
        results = resp.json().get("results", [])
        if not results:
            return None
        pick = random.choice(results)
        return pick["urls"]["regular"]
    except Exception as e:
        logger.error(f"Unsplash search failed: {e}")
        return None


def download_image(url: str) -> str | None:
    try:
        response = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0"
        })
        content_type = response.headers.get("content-type", "")
        if response.status_code != 200 or "image" not in content_type:
            return None
        if len(response.content) < MIN_IMAGE_SIZE:
            logger.info(f"Skipping tiny image ({len(response.content)} bytes)")
            return None
        suffix = ".png" if "png" in content_type else ".jpg"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(response.content)
        tmp.close()
        return tmp.name
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
    return None
