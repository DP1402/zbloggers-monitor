# ZBloggers Monitor

Daily monitoring of pro-Russian Telegram "milblogger" channels for OSINT analysis.

## What it does
1. **Scrapes** a list of Telegram channels once a day
2. **Analyses** the posts and compiles the major updates
3. **Publishes** a dashboard for the team
4. **Archives** every post and daily analysis in a database for later reference

## Project layout
- `channels.txt` — the list of channels to monitor (one per line)
- `scraper/` — code that collects Telegram posts
- `data/` — the database of posts and daily analyses
- `dashboard/` — the team-facing dashboard

## Setup (one time)
1. Get Telegram API credentials at https://my.telegram.org → "API development tools"
2. Copy `.env.example` to `.env` and fill in your credentials
3. Install dependencies: `pip install -r requirements.txt`
4. Run `python connect_telegram.py` and enter the login code Telegram sends you

> `.env` and your Telegram session file contain secrets. They are excluded from
> GitHub via `.gitignore` — never commit them.
