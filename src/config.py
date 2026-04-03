import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("marketer")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")

LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = os.getenv("LINKEDIN_PERSON_ID")

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

POST_INTERVAL_HOURS = int(os.getenv("POST_INTERVAL_HOURS", "6"))
MIN_DELAY_MINUTES = int(os.getenv("MIN_DELAY_MINUTES", "5"))
MAX_DELAY_MINUTES = int(os.getenv("MAX_DELAY_MINUTES", "120"))
