"""On-demand theme search over the collected archive.

Triggered by the dashboard's search box via .github/workflows/search.yml
(a workflow_dispatch run), not by the daily pipeline. Reads every post
already classified into data/analysis/days/*.json, asks Claude which ones
match the given theme/query, and writes the result to
data/search/<request_id>.json for the dashboard to poll and render.

Usage:
    SEARCH_QUERY=... REQUEST_ID=... ANTHROPIC_API_KEY=... python scraper/search.py
"""

import datetime
import json
import os
import re
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DAYS_DIR = ROOT / "data" / "analysis" / "days"
RESULTS_DIR = ROOT / "data" / "search"

MODEL = "claude-opus-4-8"
MAX_RESULTS = 30

PRICING = {
    "claude-opus-4-8": {"input": 5.00, "output": 25.00, "cache_write": 6.25, "cache_read": 0.50},
}

load_dotenv(ROOT / ".env")
client = anthropic.Anthropic()

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "matches": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["summary", "matches"],
    "additionalProperties": False,
}

SYSTEM = """You search an archive of already-classified Telegram posts from pro-Kremlin military channels, for an OSINT analyst.

You are given a numbered list of posts (date, channel, topic/subtopic, sentiment, one-line English summary) and a search query describing a theme or question.

Return:
- summary: 2-4 sentences synthesizing what the matching posts actually say about the query, with specifics (numbers, places, claims). If nothing substantive matches, say so plainly rather than stretching a weak match.
- matches: the "n" values of posts that substantively relate to the query, most relevant first, capped at %d entries. Do not pad the list with weakly related posts.""" % MAX_RESULTS


def load_all_posts() -> list[dict]:
    posts = []
    for path in sorted(DAYS_DIR.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        for p in d.get("posts", []):
            if not p.get("substantive"):
                continue
            posts.append({
                "date": (p.get("date_utc") or "")[:10],
                "channel": p.get("channel_label", p.get("channel", "")),
                "topic": p.get("topic"),
                "subtopic": p.get("subtopic"),
                "sentiment": p.get("sentiment"),
                "summary_en": p.get("summary_en", ""),
                "link": p.get("link"),
            })
    return posts


def sanitize_id(request_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", request_id)[:64] or "unknown"


def cost_usd(model: str, usage) -> float | None:
    rate = PRICING.get(model)
    if not rate:
        return None
    return round((
        usage.input_tokens * rate["input"]
        + usage.output_tokens * rate["output"]
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * rate["cache_write"]
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * rate["cache_read"]
    ) / 1_000_000, 4)


def main():
    query = os.environ["SEARCH_QUERY"].strip()
    request_id = sanitize_id(os.environ["REQUEST_ID"])
    generated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    posts = load_all_posts()
    result = {"query": query, "generated_at": generated_at, "posts_searched": len(posts)}

    if not posts:
        result.update(summary="No posts have been collected yet.", matches=[])
    elif not query:
        result.update(summary="Empty query.", matches=[], error="empty_query")
    else:
        payload = [{"n": i, "date": p["date"], "channel": p["channel"], "topic": p["topic"],
                    "subtopic": p["subtopic"], "sentiment": p["sentiment"], "summary": p["summary_en"]}
                   for i, p in enumerate(posts)]
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=2000,
                system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": f"Query: {query}\n\nPosts:\n{json.dumps(payload, ensure_ascii=False)}"}],
                output_config={"format": {"type": "json_schema", "schema": RESULT_SCHEMA}},
            )
            text = next(b.text for b in response.content if b.type == "text")
            parsed = json.loads(text)
            matches = [posts[i] for i in parsed["matches"] if 0 <= i < len(posts)][:MAX_RESULTS]
            result.update(summary=parsed["summary"], matches=matches,
                          cost_usd=cost_usd(MODEL, response.usage))
        except Exception as e:
            result.update(summary="", matches=[], error=str(e))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"{request_id}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {request_id}.json — {len(result.get('matches', []))} matches"
          + (f", ${result['cost_usd']}" if result.get("cost_usd") is not None else ""))


if __name__ == "__main__":
    main()
