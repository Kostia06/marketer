import json
import os
import tweepy
from google import genai
from src.config import (
    X_API_KEY,
    X_API_SECRET,
    X_ACCESS_TOKEN,
    X_ACCESS_TOKEN_SECRET,
    GEMINI_API_KEY,
    logger,
)

STYLE_GUIDE_PATH = os.path.join(os.path.dirname(__file__), "..", "style_guide.json")

TECH_CREATORS = [
    "levelsio",
    "firaborge",
    "t3dotgg",
    "swyx",
    "dan_abramov",
    "kelseyhightower",
    "antirez",
    "benlorantfy",
    "jaborntowry",
    "raaboroge",
]

ai_client = genai.Client(api_key=GEMINI_API_KEY)


def fetch_creator_tweets(handle: str, count: int = 20) -> list[dict]:
    try:
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_TOKEN_SECRET,
        )
        user = client.get_user(username=handle)
        if not user.data:
            return []

        tweets = client.get_users_tweets(
            user.data.id,
            max_results=count,
            tweet_fields=["public_metrics", "created_at"],
            exclude=["retweets", "replies"],
        )

        if not tweets.data:
            return []

        results = []
        for tweet in tweets.data:
            metrics = tweet.public_metrics or {}
            results.append({
                "text": tweet.text,
                "likes": metrics.get("like_count", 0),
                "retweets": metrics.get("retweet_count", 0),
                "replies": metrics.get("reply_count", 0),
                "impressions": metrics.get("impression_count", 0),
                "handle": handle,
            })
        return results
    except Exception as e:
        logger.warning(f"Could not fetch tweets from @{handle}: {e}")
        return []


def fetch_all_creators() -> list[dict]:
    all_tweets = []
    for handle in TECH_CREATORS:
        logger.info(f"Fetching tweets from @{handle}...")
        tweets = fetch_creator_tweets(handle)
        all_tweets.extend(tweets)
        logger.info(f"  Got {len(tweets)} tweets from @{handle}")
    return all_tweets


def analyze_with_gemini(tweets: list[dict]) -> dict:
    sorted_tweets = sorted(tweets, key=lambda t: t["likes"], reverse=True)
    top_posts = sorted_tweets[:50]

    posts_text = ""
    for t in top_posts:
        posts_text += (
            f"@{t['handle']} ({t['likes']} likes, {t['retweets']} RTs):\n"
            f"{t['text']}\n\n"
        )

    prompt = (
        "You are a social media content analyst specializing in tech/developer Twitter.\n\n"
        "Here are the top-performing tweets from popular tech creators:\n\n"
        f"{posts_text}\n\n"
        "Analyze these posts and create a detailed style guide. Return JSON:\n"
        "{\n"
        '  "patterns": ["list of 5-8 patterns you see in high-engagement posts"],\n'
        '  "hooks": ["list of 5-8 effective opening styles/hooks"],\n'
        '  "tone_rules": ["list of 5-8 tone guidelines based on what works"],\n'
        '  "formats": ["list of 3-5 post format templates that get engagement"],\n'
        '  "avoid": ["list of 5-8 things that low-engagement posts do"],\n'
        '  "engagement_triggers": ["list of 5-8 things that drive likes/RTs"],\n'
        '  "example_structures": ["list of 3-5 post structure templates with placeholders"]\n'
        "}\n\n"
        "Be specific and practical. No generic advice. Base everything on the actual data above."
    )

    response = ai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    return json.loads(response.text.strip())


def analyze_from_knowledge() -> dict:
    """Fallback: use Gemini's knowledge of tech creators instead of live data."""
    prompt = (
        "You are a social media analyst who has studied thousands of viral tech/developer tweets "
        "from creators like @levelsio, @fireship_dev, @t3dotgg, @swyx, @dan_abramov, "
        "@kelseyhightower, @antirez, and other popular dev accounts.\n\n"
        "Based on your knowledge of what makes tech tweets go viral, create a style guide.\n\n"
        "Return JSON:\n"
        "{\n"
        '  "patterns": ["5-8 specific patterns in high-engagement dev tweets"],\n'
        '  "hooks": ["5-8 effective opening styles that grab attention"],\n'
        '  "tone_rules": ["5-8 tone guidelines — be very specific, not generic"],\n'
        '  "formats": ["3-5 post format templates that get engagement"],\n'
        '  "avoid": ["5-8 specific things that make tech tweets flop"],\n'
        '  "engagement_triggers": ["5-8 things that drive likes and RTs in tech"],\n'
        '  "example_structures": ["3-5 tweet templates with [TOPIC] placeholders"]\n'
        "}\n\n"
        "Be brutally specific. No 'be authentic' or 'provide value' nonsense. "
        "Real patterns from real creators. What actually works."
    )

    response = ai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    return json.loads(response.text.strip())


def run_analysis() -> dict:
    logger.info("Starting content creator analysis...")

    tweets = fetch_all_creators()

    if len(tweets) >= 10:
        logger.info(f"Analyzing {len(tweets)} tweets from creators...")
        style_guide = analyze_with_gemini(tweets)
    else:
        logger.info("Not enough tweets fetched, using Gemini knowledge fallback...")
        style_guide = analyze_from_knowledge()

    with open(STYLE_GUIDE_PATH, "w") as f:
        json.dump(style_guide, f, indent=2)

    logger.info(f"Style guide saved to {STYLE_GUIDE_PATH}")
    return style_guide


def load_style_guide() -> dict | None:
    if os.path.exists(STYLE_GUIDE_PATH):
        with open(STYLE_GUIDE_PATH) as f:
            return json.load(f)
    return None
