import json
import re
import requests
from google import genai
from src.config import GEMINI_API_KEY, logger

ai_client = genai.Client(api_key=GEMINI_API_KEY)

TARGET_ACCOUNTS = [
    "ThePrimeagen",
    "t3dotgg",
    "firaborge",
    "kelseyhightower",
    "dan_abramov",
    "swyx",
    "levelsio",
    "antirez",
    "raaboroge",
]


def extract_tweet_id(url: str) -> str | None:
    match = re.search(r"status/(\d+)", url)
    return match.group(1) if match else None


def fetch_tweet_text(url: str) -> dict | None:
    tweet_id = extract_tweet_id(url)
    if not tweet_id:
        return None
    try:
        resp = requests.get(f"https://api.fxtwitter.com/status/{tweet_id}", timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json().get("tweet", {})
        return {
            "text": data.get("text", ""),
            "author": data.get("author", {}).get("screen_name", "unknown"),
            "tweet_id": tweet_id,
            "url": url,
        }
    except Exception as e:
        logger.error(f"Failed to fetch tweet: {e}")
        return None


def generate_reply(tweet_text: str, author: str) -> str:
    prompt = (
        f"@{author} just tweeted this:\n\n"
        f'"{tweet_text}"\n\n'
        "Write a reply that will get noticed. You're a senior dev who's genuinely engaged.\n\n"
        "RULES:\n"
        "- under 200 characters. shorter is better.\n"
        "- lowercase. casual. sounds like a real dev, not a bot.\n"
        "- add something to the conversation — agree with a twist, share a related experience, or make a sharp observation.\n"
        "- be funny if it fits, but don't force it.\n"
        "- NEVER be sycophantic ('great point!', 'so true!', 'this!')\n"
        "- NEVER just agree. add value or an angle.\n"
        "- no hashtags in replies. no emojis unless perfect.\n"
        "- do NOT start with the @username.\n\n"
        "GOOD REPLY EXAMPLES:\n"
        '- "we had this exact problem. our fix was worse than the bug."\n'
        '- "the real question is who approved this in code review"\n'
        '- "tried this last week. my docker container is still running somewhere."\n\n'
        "Return ONLY the reply text."
    )

    response = ai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text.strip().strip('"')


def fetch_recent_from_account(username: str) -> list[dict]:
    """Fetch recent tweets from an account via RSS/fxtwitter."""
    try:
        resp = requests.get(
            f"https://api.fxtwitter.com/{username}",
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        tweets = data.get("tweets", [])
        results = []
        for t in tweets[:5]:
            results.append({
                "text": t.get("text", ""),
                "author": username,
                "tweet_id": str(t.get("id", "")),
                "url": f"https://x.com/{username}/status/{t.get('id', '')}",
                "likes": t.get("likes", 0),
            })
        return results
    except Exception as e:
        logger.error(f"Failed to fetch tweets from @{username}: {e}")
        return []
