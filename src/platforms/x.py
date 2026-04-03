import time
import tweepy
from src.config import (
    X_API_KEY,
    X_API_SECRET,
    X_ACCESS_TOKEN,
    X_ACCESS_TOKEN_SECRET,
    logger,
)

MAX_RETRIES = 3
RETRY_DELAY = 30


def get_client() -> tweepy.Client:
    return tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_TOKEN_SECRET,
    )


def post_to_x(content: str, image_path: str | None = None) -> tuple[bool, str | None]:
    """Post to X with retries. Returns (success, tweet_id)."""
    for attempt in range(MAX_RETRIES):
        try:
            media_id = None
            if image_path:
                auth = tweepy.OAuth1UserHandler(
                    X_API_KEY, X_API_SECRET,
                    X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET,
                )
                api_v1 = tweepy.API(auth)
                media = api_v1.media_upload(filename=image_path)
                media_id = media.media_id
                logger.info(f"Uploaded image to X (media_id={media_id})")

            client = get_client()
            kwargs = {"text": content}
            if media_id:
                kwargs["media_ids"] = [media_id]

            response = client.create_tweet(**kwargs)
            tweet_id = response.data["id"]
            logger.info(f"Posted to X (tweet_id={tweet_id})")
            return True, tweet_id
        except Exception as e:
            logger.error(f"X posting failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    return False, None


def delete_from_x(tweet_id: str) -> bool:
    try:
        client = get_client()
        client.delete_tweet(tweet_id)
        logger.info(f"Deleted tweet {tweet_id}")
        return True
    except Exception as e:
        logger.error(f"X deletion failed: {e}")
        return False
