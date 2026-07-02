"""One-time Telegram login.

Run this once in a terminal:  python connect_telegram.py
Telegram will text you a login code; type it in when asked.
This saves a "session" file so future runs don't need to log in again.
"""

import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient

load_dotenv()

api_id = os.getenv("TELEGRAM_API_ID")
api_hash = os.getenv("TELEGRAM_API_HASH")
phone = os.getenv("TELEGRAM_PHONE")

if not api_id or not api_hash or not phone:
    raise SystemExit(
        "Missing credentials. Copy .env.example to .env and fill in "
        "TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_PHONE first."
    )

with TelegramClient("zbloggers", int(api_id), api_hash) as client:
    client.start(phone=phone)
    me = client.get_me()
    print(f"\nConnected to Telegram as {me.first_name} ({me.phone}). Setup complete!")
