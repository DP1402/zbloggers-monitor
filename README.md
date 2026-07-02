# ZBloggers Monitor

Daily monitoring of 10 major pro-Kremlin military Telegram channels for OSINT analysis.

**Dashboard:** https://dp1402.github.io/zbloggers-monitor/dashboard/

## How it works

Every morning at 05:30 UTC a GitHub Actions run:
1. **Collects** the previous day's posts from all channels via the Telegram API → `data/posts/YYYY-MM.csv`
2. **Classifies** every post with Claude (Haiku): substantive or noise, topic, subtopic, sentiment, one-line English summary
3. **Flags** new stories (subtopic unseen in 14 days, now in 2+ channels), mood swings (net sentiment moves ≥25 pts), and a standing watchlist (mobilisation rumours, criticism of Putin)
4. **Writes the daily brief** with Claude (Opus): developments with source links, narrative watch, mood summary
5. **Publishes** everything to this repo; the dashboard (GitHub Pages) reads it directly

⚠️ All monitored channels are propaganda outlets. Claims are signals to investigate, not facts.

## Data files

| Path | Contents |
|---|---|
| `data/posts/YYYY-MM.csv` | every raw post: date, channel, link, full Russian text, views, forwards |
| `data/analysis/classified-YYYY-MM.csv` | every classification: topic, subtopic, sentiment, English summary |
| `data/analysis/days/YYYY-MM-DD.json` | full daily analysis incl. the brief (what the dashboard renders) |
| `data/analysis/index.json` | one summary row per day (feeds the trend charts) |

CSVs are UTF-8 with BOM — they open directly in Excel with Cyrillic intact.

## Project layout

- `channels.txt` — monitored channels (one username per line)
- `scraper/collect.py` — Telegram collector (`--days N` to backfill)
- `scraper/analyze.py` — classifier + brief writer (`--date`, `--backfill N`, `--brief-only`)
- `scraper/taxonomy.py` — the fixed topic/subtopic taxonomy and watchlist
- `dashboard/` — the static dashboard (EG-styled, no build step)
- `.github/workflows/daily.yml` — the daily automation

## Local setup (one time)

1. Get Telegram API credentials at https://my.telegram.org → "API development tools"
2. Copy `.env.example` to `.env`; fill in Telegram credentials and `ANTHROPIC_API_KEY`
3. `pip install -r requirements.txt`
4. `python connect_telegram.py` (Telegram texts you a login code)
5. View the dashboard locally: `python -m http.server` → http://localhost:8000/dashboard/

Secrets (`.env`, `*.session`) are gitignored — never commit them. The GitHub Actions run
uses repository secrets: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION`
(Telethon string session), `ANTHROPIC_API_KEY`.
