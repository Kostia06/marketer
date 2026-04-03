import requests
from src.config import LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_ID, logger

HEADERS = {
    "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
    "X-Restli-Protocol-Version": "2.0.0",
}
AUTHOR = f"urn:li:person:{LINKEDIN_PERSON_ID}"


def upload_image(image_path: str) -> str | None:
    """Upload image to LinkedIn. Returns asset URN."""
    try:
        register_payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": AUTHOR,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }
        resp = requests.post(
            "https://api.linkedin.com/v2/assets?action=registerUpload",
            json=register_payload,
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            logger.error(f"LinkedIn image register failed: {resp.status_code} — {resp.text}")
            return None

        data = resp.json()
        upload_url = data["value"]["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
        ]["uploadUrl"]
        asset = data["value"]["asset"]

        with open(image_path, "rb") as f:
            upload_resp = requests.put(
                upload_url,
                data=f,
                headers={"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"},
                timeout=30,
            )
        if upload_resp.status_code not in (200, 201):
            logger.error(f"LinkedIn image upload failed: {upload_resp.status_code}")
            return None

        logger.info(f"Uploaded image to LinkedIn (asset={asset})")
        return asset
    except Exception as e:
        logger.error(f"LinkedIn image upload failed: {e}")
        return None


def post_to_linkedin(content: str, image_path: str | None = None) -> tuple[bool, str | None]:
    """Post to LinkedIn. Returns (success, post_urn)."""
    try:
        asset = None
        if image_path:
            asset = upload_image(image_path)

        if asset:
            media_category = "IMAGE"
            media = [{"status": "READY", "media": asset}]
        else:
            media_category = "NONE"
            media = []

        payload = {
            "author": AUTHOR,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": content},
                    "shareMediaCategory": media_category,
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }

        if media:
            payload["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = media

        response = requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
            json=payload,
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=15,
        )
        if response.status_code in (200, 201):
            post_urn = response.json().get("id")
            logger.info(f"Posted to LinkedIn (urn={post_urn})")
            return True, post_urn
        logger.error(f"LinkedIn failed: {response.status_code} — {response.text}")
        return False, None
    except Exception as e:
        logger.error(f"LinkedIn posting failed: {e}")
        return False, None


def delete_from_linkedin(post_urn: str) -> bool:
    try:
        resp = requests.delete(
            f"https://api.linkedin.com/v2/ugcPosts/{post_urn}",
            headers=HEADERS,
            timeout=15,
        )
        if resp.status_code in (200, 204):
            logger.info(f"Deleted LinkedIn post {post_urn}")
            return True
        logger.error(f"LinkedIn delete failed: {resp.status_code} — {resp.text}")
        return False
    except Exception as e:
        logger.error(f"LinkedIn deletion failed: {e}")
        return False
