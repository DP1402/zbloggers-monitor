"""Email the daily brief as a short newsletter.

Usage:
    python scraper/newsletter.py                    # latest day that has a brief
    python scraper/newsletter.py --date 2026-07-02  # specific day
    python scraper/newsletter.py --dry-run          # print instead of sending

Recipients come from subscribers.txt (one address per line).
Sending uses Gmail SMTP with an app password:
    EMAIL_ADDRESS      the Gmail address to send from
    EMAIL_APP_PASSWORD a Google "app password" (not the normal password)
If those are not set, the script prints a notice and exits cleanly (exit 0),
so the daily automation never fails just because email isn't configured.
"""

import argparse
import json
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DAYS_DIR = ROOT / "data" / "analysis" / "days"
INDEX_PATH = ROOT / "data" / "analysis" / "index.json"
DASHBOARD_URL = "https://dp1402.github.io/zbloggers-monitor/dashboard/"

load_dotenv(ROOT / ".env")


def read_subscribers() -> list[str]:
    out = []
    path = ROOT / "subscribers.txt"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            addr = line.split("#")[0].strip()
            if addr and "@" in addr:
                out.append(addr)
    return out


def latest_day_with_brief() -> str | None:
    if not INDEX_PATH.exists():
        return None
    days = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["days"]
    for d in reversed(days):
        if d.get("headline"):
            return d["date"]
    return None


def nice_date(day: str) -> str:
    import datetime
    return datetime.date.fromisoformat(day).strftime("%A %d %B %Y").replace(" 0", " ")


def compose(day: str, doc: dict) -> tuple[str, str, str]:
    """Returns (subject, plain_text, html)."""
    brief = doc["brief"]
    flags = brief.get("flag_texts", [])
    devs = brief["developments"][:7 - min(len(flags), 2)]
    so = doc["sentiment_overall"]

    subject = f"ZBloggers Monitor · {nice_date(day)} — {brief['headline']}"

    # ---- plain text ----
    lines = [f"ZBLOGGERS MONITOR — {nice_date(day)}", "", brief["lead"], ""]
    for f in flags:
        lines.append(f"[FLAG] {f['title']}: {f['body']}")
    if flags:
        lines.append("")
    for i, d in enumerate(devs, 1):
        src = d["sources"][0]["url"] if d["sources"] else ""
        corr = "multiple channels" if d["corroboration"] == "multi" else "single source"
        lines.append(f"{i}. {d['title']} ({corr})")
        lines.append(f"   {d['body']} {src}")
    lines += ["",
              f"Mood of coverage: {so['pos_pct']}% positive / {so['neu_pct']}% neutral / {so['neg_pct']}% negative "
              f"across {doc['substantive_posts']} substantive posts.",
              "",
              f"Full brief, charts and sources: {DASHBOARD_URL}",
              "",
              "Source channels are pro-Kremlin propaganda outlets; claims are signals to investigate, not facts.",
              "To subscribe or unsubscribe, reply to this email."]
    plain = "\n".join(lines)

    # ---- html ----
    def esc(s):
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    h = [f"""<div style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #000; max-width: 640px">
<h2 style="color: #00205B; margin: 0 0 2px">ZBloggers Monitor</h2>
<p style="font-style: italic; margin: 0 0 14px">{nice_date(day)} — daily read on 10 pro-Kremlin military Telegram channels</p>
<p style="margin: 0 0 14px">{esc(brief['lead'])}</p>"""]
    for f in flags:
        h.append(f"""<p style="margin: 0 0 10px; padding: 8px 12px; background: #fdf0f2; border-left: 3px solid #BA0C2F">
<strong>🚩 {esc(f['title'])}.</strong> {esc(f['body'])}</p>""")
    h.append('<ol style="padding-left: 20px; margin: 14px 0">')
    for d in devs:
        corr = "✓ multiple channels" if d["corroboration"] == "multi" else "◌ single source"
        src = (f' <a href="{esc(d["sources"][0]["url"])}" style="color:#1D4F91">source ↗</a>'
               if d["sources"] else "")
        h.append(f"""<li style="margin-bottom: 10px"><strong>{esc(d['title'])}</strong>
<span style="color: #555; font-size: 12px">({corr})</span><br>{esc(d['body'])}{src}</li>""")
    h.append("</ol>")
    h.append(f"""<p style="margin: 0 0 14px">Mood of coverage: <strong style="color:#658D18">{so['pos_pct']}% positive</strong>
/ {so['neu_pct']}% neutral / <strong style="color:#BA0C2F">{so['neg_pct']}% negative</strong>
across {doc['substantive_posts']} substantive posts.</p>
<p style="margin: 0 0 16px"><a href="{DASHBOARD_URL}" style="color:#fff; background:#00205B; padding:8px 16px; text-decoration:none; font-weight:bold">Open the full dashboard →</a></p>
<p style="font-size: 11px; color: #666">⚠️ Source channels are pro-Kremlin propaganda outlets; claims are signals to investigate, not facts.<br>
To subscribe or unsubscribe, reply to this email.</p></div>""")
    html = "\n".join(h)
    return subject, plain, html


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="day to send (YYYY-MM-DD); default latest with a brief")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    day = args.date or latest_day_with_brief()
    if not day:
        print("No day with a brief found; nothing to send.")
        return 0
    path = DAYS_DIR / f"{day}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not doc.get("brief"):
        print(f"{day} has no brief; nothing to send.")
        return 0

    subject, plain, html = compose(day, doc)
    recipients = read_subscribers()

    if args.dry_run:
        print("TO:", ", ".join(recipients))
        print("SUBJECT:", subject)
        print()
        print(plain)
        return 0

    sender = os.environ.get("EMAIL_ADDRESS", "").strip()
    password = os.environ.get("EMAIL_APP_PASSWORD", "").strip()
    if not sender or not password:
        print("EMAIL_ADDRESS / EMAIL_APP_PASSWORD not configured — skipping newsletter.")
        return 0
    if not recipients:
        print("No subscribers — skipping newsletter.")
        return 0

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"ZBloggers Monitor <{sender}>"
    msg["To"] = sender
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port) as server:
        server.login(sender, password)
        # recipients go in BCC so colleagues don't see each other's addresses
        server.sendmail(sender, [sender] + recipients, msg.as_string())
    print(f"Newsletter for {day} sent to {len(recipients)} recipient(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
