"""Collect posts from the monitored Telegram channels into monthly CSV files.

Usage:
    python scraper/collect.py            # last 24 hours (the daily run)
    python scraper/collect.py --days 31  # backfill a month

Posts land in data/posts/YYYY-MM.csv (UTF-8 with BOM so Excel shows Cyrillic
correctly). Re-running never duplicates: rows are keyed by channel + message id.
"""

import argparse
import csv
import datetime
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
import os

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "posts"

FIELDS = [
    "date_utc", "channel", "message_id", "link", "text",
    "views", "forwards", "replies", "is_forward", "has_media", "media_type",
]


def read_channels():
    channels = []
    for line in (ROOT / "channels.txt").read_text(encoding="utf-8").splitlines():
        name = line.split("#")[0].strip()
        if name:
            channels.append(name)
    return channels


def load_month(path):
    """Existing rows for one month, keyed by (channel, message_id)."""
    rows = {}
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                rows[(row["channel"], row["message_id"])] = row
    return rows


def save_month(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows.values(), key=lambda r: r["date_utc"])
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(ordered)


def msg_to_row(channel, msg):
    media_type = type(msg.media).__name__.replace("MessageMedia", "").lower() if msg.media else ""
    return {
        "date_utc": msg.date.strftime("%Y-%m-%d %H:%M:%S"),
        "channel": channel,
        "message_id": str(msg.id),
        "link": f"https://t.me/{channel}/{msg.id}",
        "text": (msg.text or "").replace("\r", ""),
        "views": msg.views if msg.views is not None else "",
        "forwards": msg.forwards if msg.forwards is not None else "",
        "replies": msg.replies.replies if msg.replies else "",
        "is_forward": "1" if msg.forward else "0",
        "has_media": "1" if msg.media else "0",
        "media_type": media_type,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=float, default=1, help="how many days back to collect")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.days)

    # Locally the login lives in zbloggers.session; on GitHub Actions it is
    # provided as a compact string in the TELEGRAM_SESSION secret.
    session = (StringSession(os.environ["TELEGRAM_SESSION"].strip())
               if os.environ.get("TELEGRAM_SESSION", "").strip() else str(ROOT / "zbloggers"))
    client = TelegramClient(
        session,
        int(os.environ["TELEGRAM_API_ID"]),
        os.environ["TELEGRAM_API_HASH"],
    )
    client.flood_sleep_threshold = 120  # auto-wait through Telegram rate limits

    new_by_month = {}   # "YYYY-MM" -> list of rows
    with client:
        for channel in read_channels():
            count = 0
            for msg in client.iter_messages(channel):
                if msg.date < cutoff:
                    break
                row = msg_to_row(channel, msg)
                month = row["date_utc"][:7]
                new_by_month.setdefault(month, []).append(row)
                count += 1
            print(f"{channel}: {count} posts")

    total_new = 0
    for month, rows in sorted(new_by_month.items()):
        path = DATA_DIR / f"{month}.csv"
        existing = load_month(path)
        before = len(existing)
        for row in rows:
            existing[(row["channel"], row["message_id"])] = row
        save_month(path, existing)
        added = len(existing) - before
        total_new += added
        print(f"{path.name}: +{added} new rows ({len(existing)} total)")

    print(f"Done: {total_new} new posts saved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
