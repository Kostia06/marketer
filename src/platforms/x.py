import tweepy
from src.config import (
    X_API_KEY,
    X_API_SECRET,
    X_ACCESS_TOKEN,
    X_ACCESS_TOKEN_SECRET,
    logger,
)


def post_to_x(content: str, image_path: str | None = None) -> bool:
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

        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_TOKEN_SECRET,
        )

        kwargs = {"text": content}
        if media_id:
            kwargs["media_ids"] = [media_id]

        client.create_tweet(**kwargs)
        logger.info("Posted to X successfully")
        return True
    except Exception as e:
        logger.error(f"X posting failed: {e}")
        return False
