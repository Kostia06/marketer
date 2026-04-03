import json
from google import genai
from src.config import GEMINI_API_KEY, logger
import random
from src.news import fetch_top_stories, fetch_article_image, search_unsplash, download_image

BROAD_TECH_KEYWORDS = [
    "programming code screen",
    "software developer laptop",
    "server data center",
    "coding terminal dark",
    "tech workspace monitor",
    "developer typing keyboard",
    "computer science abstract",
]
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
    stories = fetch_top_stories(30)
    headlines = "\n".join(f"- {s['title']} (score: {s['score']}) ({s['url']})" for s in stories)

    style_context = build_style_context()
    style_block = f"\n\nSTYLE GUIDE (learned from top tech creators):\n{style_context}" if style_context else ""

    prompt = (
        f"Here are today's top tech news stories:\n\n"
        f"{headlines}\n\n"
        "TOPIC SELECTION — pick the story that:\n"
        "- Would get the most engagement from a BROAD dev audience (not just niche hobbyists)\n"
        "- Is about something developers actually care about: languages, frameworks, big tech drama, AI, tools, career, industry shifts\n"
        "- SKIP stories about: obscure utilities, hardware quirks, academic papers nobody reads, niche OS tools, random personal blogs\n"
        "- Prefer: controversial takes, big company moves, new language/framework releases, security breaches, AI developments, developer culture\n\n"
        "Write a social media post about it using this voice:\n\n"
        "VOICE:\n"
        "- lowercase always. talk like a smart dev texting a friend.\n"
        "- dry humor. short sentences. no fluff.\n"
        "- never use: revolutionize, game-changer, exciting, incredible, amazing, innovative, cutting-edge, leverage\n\n"
        "STRUCTURE — every post must have 3 parts:\n"
        "1. HOOK (first line) — a bold claim, ironic observation, or uncomfortable truth. make them stop scrolling.\n"
        "2. BODY (1-2 lines max) — back it up or twist it. keep it punchy.\n"
        "3. REPLY HOOK (last line) — ALWAYS end with something that forces a reply. rotate between:\n"
        '   - "am i wrong?"\n'
        '   - "how many of you have done this?"\n'
        '   - "which side are you on?"\n'
        '   - "be honest."\n'
        '   - "change my mind."\n'
        '   - "your team does this too, admit it."\n\n'
        "POST TYPES — rotate between these:\n"
        '1. HOT TAKE: "[uncomfortable truth devs won\'t say]. change my mind."\n'
        '2. QUESTION: "why do we still accept [thing everyone does]? be honest."\n'
        '3. POLL BAIT: "[option a] vs [option b]. no wrong answers, but there are wrong answers."\n'
        '4. CONFESSION: "every dev has done [relatable thing]. how many of you have done this?"\n'
        '5. OBSERVATION: "funny how [ironic tech observation]. am i wrong?"\n\n'
        "GOOD EXAMPLES:\n"
        '- "we don\'t have bugs. we have undocumented features that somehow made it to prod. your team does this too, admit it."\n'
        '- "tabs vs spaces ended friendships. light mode vs dark mode ended careers. which side are you on?"\n'
        '- "you don\'t have a deployment pipeline. you have a prayer and a bash script. am i wrong?"\n\n'
        "RULES:\n"
        "- under 280 characters total\n"
        "- 1 hashtag max, only if it fits naturally at the end\n"
        "- zero corporate speak\n"
        "- the reply hook is NOT optional. every post ends with one.\n"
        f"{style_block}\n\n"
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
                logger.info(f"Using article image from {image_url}")

    if not image_path:
        keyword = random.choice(BROAD_TECH_KEYWORDS)
        unsplash_url = search_unsplash(keyword)
        if unsplash_url:
            image_path = download_image(unsplash_url)
            if image_path:
                logger.info(f"Using Unsplash image for '{keyword}'")

    return {
        "text": result["text"],
        "source_url": source_url,
        "image_path": image_path,
    }
