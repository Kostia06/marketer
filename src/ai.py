import json
from google import genai
from src.config import GEMINI_API_KEY, logger
from src.news import fetch_top_stories, fetch_article_image, download_image

client = genai.Client(api_key=GEMINI_API_KEY)


def generate_post() -> dict:
    """Generate a post based on real tech news.

    Returns {"text": str, "source_url": str, "image_path": str | None}
    """
    stories = fetch_top_stories(10)
    headlines = "\n".join(f"- {s['title']} ({s['url']})" for s in stories)

    prompt = (
        f"Here are today's top tech news stories:\n\n"
        f"{headlines}\n\n"
        "Pick the MOST interesting one and write an engaging social media post about it. "
        "Under 280 characters. Include 2-3 hashtags. Sound human and casual/witty. "
        'Return JSON only: {"text": "the post", "source_url": "the article url you picked"}'
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    result = json.loads(response.text.strip())
    source_url = result.get("source_url", "")

    image_path = None
    if source_url:
        image_url = fetch_article_image(source_url)
        if image_url:
            image_path = download_image(image_url)
            if image_path:
                logger.info(f"Downloaded article image from {image_url}")

    return {
        "text": result["text"],
        "source_url": source_url,
        "image_path": image_path,
    }
