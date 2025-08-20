# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN in .env")

DEFAULT_VS_CURRENCY = "usd"
DEFAULT_DAYS = 120
DEFAULT_INTERVAL = "daily"
IMG_DIR = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(IMG_DIR, exist_ok=True)

ENABLE_AFFILIATE_FOOTER = True
AFFILIATE_TEXT = "Try our free analytics — future pro tier coming soon."

DEFAULT_LANG = "en"
