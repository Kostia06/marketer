import json
import os
from src.config import logger

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "post_history.json")
MAX_HISTORY = 50


def load_history() -> list[dict]:
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH) as f:
            return json.load(f)
    return []


def save_post(text: str, source_url: str):
    history = load_history()
    history.append({"text": text, "source_url": source_url})
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)
    logger.info(f"Saved to history ({len(history)} posts tracked)")


def get_recent_topics(count: int = 15) -> str:
    history = load_history()
    if not history:
        return ""
    recent = history[-count:]
    lines = []
    for h in recent:
        lines.append(f"- {h['text'][:100]}")
        if h.get("source_url"):
            lines.append(f"  source: {h['source_url']}")
    return "\n".join(lines)
