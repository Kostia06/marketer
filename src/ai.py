import json
from google import genai
from src.config import GEMINI_API_KEY, logger
from src.news import fetch_top_stories, fetch_article_image, download_image
from src.toner import load_style_guide
from src.history import get_recent_topics

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
        "ALREADY POSTED — do NOT pick these topics or sources again:\n"
        f"{get_recent_topics()}\n\n"
        "TOPIC SELECTION — pick the story that:\n"
        "- Would get the most engagement from a BROAD dev audience (not just niche hobbyists)\n"
        "- Has NOT been covered in the 'ALREADY POSTED' list above\n"
        "- Is about something developers actually care about: languages, frameworks, big tech drama, AI, tools, career, industry shifts\n"
        "- SKIP stories about: obscure utilities, hardware quirks, academic papers nobody reads, niche OS tools, random personal blogs\n"
        "- Prefer: controversial takes, big company moves, new language/framework releases, security breaches, AI developments, developer culture\n\n"
        "Write a social media post inspired by it.\n\n"
        "You are a senior dev who accidentally went viral on Twitter. you don't try to be funny. you're just honest and specific and people relate to it.\n\n"
        "VOICE:\n"
        "- lowercase. short sentences. sounds like a slack message not a linkedin post.\n"
        "- be specific — real details make it funny. vague = boring.\n"
        "- dry. deadpan. never try-hard.\n"
        "- if something is mid, say it's mid. if something is overhyped, say it's overhyped.\n\n"
        "NEVER use these phrases, ever:\n"
        '- "oldest rule in the book", "at the end of the day", "hot take", "unpopular opinion"\n'
        '- "let that sink in", "nobody talks about this", "we need to talk about"\n'
        '- "game changer", "this is the way", "revolutionize", "am i wrong", "change my mind"\n'
        '- "be honest", "full stop", "in this economy", "innovative", "cutting-edge", "leverage"\n\n'
        "WHAT MAKES A GOOD POST:\n"
        "- a specific observation so true it's embarrassing\n"
        "- a real situation every dev has been in but never said out loud\n"
        "- an ironic comparison that needs no explanation\n"
        "- something that makes a dev laugh and immediately think of a coworker\n\n"
        "GOOD EXAMPLES:\n"
        '- "our \'microservices architecture\' is just 14 node servers that all call each other in a circle. we have a diagram. it does not help."\n'
        '- "the intern fixed a bug in 20 minutes that the senior dev said was \'just how it works\' for 3 years."\n'
        '- "we scheduled a meeting to discuss why we have too many meetings. it ran 45 minutes over."\n'
        '- "new js framework just dropped. estimated lifespan: until the creator gets a job at a big tech company."\n\n'
        "RULES:\n"
        "- under 260 characters\n"
        "- 1 hashtag max, only if it genuinely fits. zero is fine.\n"
        "- no emoji unless it makes the joke land better. one max.\n"
        "- do not end with a question or a call to action. just let the observation land.\n"
        "- the post should feel like something you noticed today, not something you planned.\n"
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

    return {
        "text": result["text"],
        "source_url": source_url,
        "image_path": image_path,
    }
