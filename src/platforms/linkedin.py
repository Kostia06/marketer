import requests
from src.config import LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_ID, logger

API_URL = "https://api.linkedin.com/v2/ugcPosts"


def post_to_linkedin(content: str) -> bool:
    try:
        headers = {
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        payload = {
            "author": f"urn:li:person:{LINKEDIN_PERSON_ID}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": content},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }
        response = requests.post(API_URL, json=payload, headers=headers)
        if response.status_code in (200, 201):
            logger.info("Posted to LinkedIn successfully")
            return True
        logger.error(f"LinkedIn failed: {response.status_code} — {response.text}")
        return False
    except Exception as e:
        logger.error(f"LinkedIn posting failed: {e}")
        return False
