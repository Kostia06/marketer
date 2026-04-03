import json
import random
import tempfile
import requests
from google import genai
from src.config import GEMINI_API_KEY, logger

ai_client = genai.Client(api_key=GEMINI_API_KEY)

MEME_TEMPLATES = [
    {"id": "181913649", "name": "Drake", "box_count": 2},
    {"id": "87743020", "name": "Two Buttons", "box_count": 2},
    {"id": "112126428", "name": "Distracted Boyfriend", "box_count": 3},
    {"id": "131087935", "name": "Running Away Balloon", "box_count": 5},
    {"id": "438680", "name": "Batman Slapping Robin", "box_count": 2},
    {"id": "93895088", "name": "Expanding Brain", "box_count": 4},
    {"id": "61579", "name": "One Does Not Simply", "box_count": 2},
    {"id": "101470", "name": "Ancient Aliens", "box_count": 2},
    {"id": "188390779", "name": "Woman Yelling at Cat", "box_count": 2},
    {"id": "129242436", "name": "Change My Mind", "box_count": 2},
    {"id": "124822590", "name": "Left Exit 12 Off Ramp", "box_count": 3},
    {"id": "247375501", "name": "Buff Doge vs Cheems", "box_count": 4},
    {"id": "217743513", "name": "UNO Draw 25 Cards", "box_count": 2},
    {"id": "91538330", "name": "X X Everywhere", "box_count": 2},
    {"id": "252600902", "name": "Always Has Been", "box_count": 2},
]


def generate_meme() -> dict | None:
    template = random.choice(MEME_TEMPLATES)
    templates_list = "\n".join(
        f"- {t['name']} ({t['box_count']} text boxes)" for t in MEME_TEMPLATES
    )

    prompt = (
        f"You're making a coding/dev meme using the '{template['name']}' template "
        f"which has {template['box_count']} text boxes.\n\n"
        f"Available templates for reference:\n{templates_list}\n\n"
        "Write the text for each box. Make it about developer life, coding, "
        "debugging, meetings, deployments, or tech culture. Be specific and funny.\n\n"
        "RULES:\n"
        "- each box text should be short (under 40 chars)\n"
        "- the joke should land visually with the meme format\n"
        "- think about what makes this specific template funny\n"
        "- no hashtags in the meme text\n\n"
        f"Return JSON: {{\"template_name\": \"{template['name']}\", "
        f"\"boxes\": [\"text for box 1\", \"text for box 2\", ...], "
        f"\"caption\": \"optional tweet caption under 100 chars, with 1 hashtag\"}}"
    )

    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        result = json.loads(response.text.strip())

        image_path = create_meme_image(template["id"], result["boxes"])
        if not image_path:
            return None

        return {
            "text": result.get("caption", f"dev life. #{template['name'].lower().replace(' ', '')}"),
            "source_url": "",
            "image_path": image_path,
        }
    except Exception as e:
        logger.error(f"Meme generation failed: {e}")
        return None


def create_meme_image(template_id: str, boxes: list[str]) -> str | None:
    try:
        params = {
            "template_id": template_id,
            "username": "imgflip_hubot",
            "password": "imgflip_hubot",
        }
        for i, text in enumerate(boxes):
            params[f"boxes[{i}][text]"] = text

        resp = requests.post(
            "https://api.imgflip.com/caption_image",
            data=params,
            timeout=15,
        )
        data = resp.json()

        if not data.get("success"):
            logger.error(f"Imgflip failed: {data.get('error_message')}")
            return None

        image_url = data["data"]["url"]
        img_resp = requests.get(image_url, timeout=15)
        if img_resp.status_code != 200:
            return None

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(img_resp.content)
        tmp.close()
        logger.info(f"Created meme image: {image_url}")
        return tmp.name
    except Exception as e:
        logger.error(f"Meme image creation failed: {e}")
        return None
