import json
from google import genai
from src.config import GEMINI_API_KEY, logger
from src.news import fetch_top_stories, fetch_article_image, search_unsplash, download_image
from src.toner import load_style_guide

client = genai.Client(api_key=GEMINI_API_KEY)


def build_style_context() -> str:
    guide = load_style_guide()
    if not guide:
        return ""

    sections = []
    if guide.get("tone_rules"):
        sections.append("TONE RULES:\n" + "\n".join(f"- {r}" for r in guide["tone_rules"]))
    if guide.get("hooks"):
        sections.append("EFFECTIVE HOOKS:\n" + "\n".join(f"- {h}" for h in guide["hooks"]))
    if guide.get("avoid"):
        sections.append("AVOID:\n" + "\n".join(f"- {a}" for a in guide["avoid"]))
    if guide.get("engagement_triggers"):
        sections.append("WHAT DRIVES ENGAGEMENT:\n" + "\n".join(f"- {e}" for e in guide["engagement_triggers"]))
    if guide.get("example_structures"):
        sections.append("POST TEMPLATES:\n" + "\n".join(f"- {s}" for s in guide["example_structures"]))

    return "\n\n".join(sections)


def generate_post() -> dict:
    """Generate a post based on real tech news.

    Returns {"text": str, "source_url": str, "image_path": str | None}
    """
    stories = fetch_top_stories(10)
    headlines = "\n".join(f"- {s['title']} ({s['url']})" for s in stories)

    style_context = build_style_context()
    style_block = f"\n\nSTYLE GUIDE (learned from top tech creators):\n{style_context}" if style_context else ""

    prompt = (
        f"Here are today's top tech news stories:\n\n"
        f"{headlines}\n\n"
        "Pick the MOST interesting one and write a social media post about it.\n\n"
        "TONE RULES:\n"
        "- Write like a dev telling a friend something cool over coffee\n"
        "- Lowercase is fine. No corporate speak. No buzzwords.\n"
        "- Be genuinely funny — dry humor, sarcasm, or a witty observation\n"
        "- NEVER use words like: revolutionize, game-changer, exciting, incredible, amazing, mind-blowing, unlock, unleash, leverage\n"
        "- NEVER start with 'Just learned...' or 'Did you know...'\n"
        "- No fake enthusiasm. If something is mid, say it's mid.\n"
        "- One emoji max. Zero is fine.\n"
        "- Under 280 characters. 1-2 hashtags max, placed naturally.\n\n"
        "Good examples:\n"
        "- 'turns out the fastest json parser is written in rust. of course it is. #rust'\n"
        "- 'apple just added a feature linux had in 2004. innovation. #wwdc'\n"
        "- 'new js framework just dropped. we are now truly blessed #javascript'\n"
        f"{style_block}\n\n"
        'Return JSON only: {"text": "the post", "source_url": "the article url you picked", "image_keyword": "1-2 word TECH search term for a stock photo, e.g. server rack, code screen, laptop desk, circuit board, data center"}'
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    result = json.loads(response.text.strip())
    source_url = result.get("source_url", "")
    image_keyword = result.get("image_keyword", "technology")

    image_path = None

    if source_url:
        image_url = fetch_article_image(source_url)
        if image_url:
            image_path = download_image(image_url)
            if image_path:
                logger.info(f"Using article image from {image_url}")

    if not image_path:
        unsplash_url = search_unsplash(image_keyword)
        if unsplash_url:
            image_path = download_image(unsplash_url)
            if image_path:
                logger.info(f"Using Unsplash image for '{image_keyword}'")

    return {
        "text": result["text"],
        "source_url": source_url,
        "image_path": image_path,
    }
