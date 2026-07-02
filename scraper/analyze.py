"""Classify posts and write the daily analytical brief.

Usage:
    python scraper/analyze.py                      # analyze yesterday (UTC)
    python scraper/analyze.py --date 2026-07-01    # analyze one specific day
    python scraper/analyze.py --backfill 30        # classify last 30 days, no briefs
    python scraper/analyze.py --date 2026-07-01 --brief-only  # (re)write brief only

Two models (hybrid setup):
  - claude-haiku-4-5  classifies every post (topic, subtopic, sentiment) — cheap
  - claude-opus-4-8   writes the daily brief, narrative watch and flag texts

Outputs:
  data/analysis/days/YYYY-MM-DD.json      full day analysis (the dashboard reads these)
  data/analysis/index.json                 one summary row per day (for trend charts)
  data/analysis/classified-YYYY-MM.csv     flat CSV of all classifications (for Excel)
"""

import argparse
import csv
import datetime
import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from taxonomy import TAXONOMY, WATCHLIST, CHANNEL_LABELS

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "data" / "posts"
DAYS_DIR = ROOT / "data" / "analysis" / "days"
INDEX_PATH = ROOT / "data" / "analysis" / "index.json"

CLASSIFY_MODEL = "claude-haiku-4-5"
BRIEF_MODEL = "claude-opus-4-8"
BATCH_SIZE = 25
MIN_TEXT_LEN = 40  # posts shorter than this are counted but not classified

load_dotenv(ROOT / ".env")
client = anthropic.Anthropic()


# ---------------------------------------------------------------- data loading

def load_posts_for_day(day: str) -> list[dict]:
    """All raw posts whose UTC date matches `day` (YYYY-MM-DD)."""
    month_csv = POSTS_DIR / f"{day[:7]}.csv"
    if not month_csv.exists():
        return []
    with open(month_csv, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if r["date_utc"].startswith(day)]


def load_day_json(day: str) -> dict | None:
    path = DAYS_DIR / f"{day}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def prior_subtopic_history(day: str, lookback: int = 14) -> dict:
    """(topic, subtopic) -> total posts in the `lookback` days before `day`."""
    counts: dict = {}
    d = datetime.date.fromisoformat(day)
    for i in range(1, lookback + 1):
        prev = load_day_json(str(d - datetime.timedelta(days=i)))
        if not prev:
            continue
        for row in prev.get("subtopics", []):
            key = (row["topic"], row["subtopic"])
            counts[key] = counts.get(key, 0) + row["posts"]
    return counts


# ---------------------------------------------------------------- classification

def taxonomy_prompt() -> str:
    lines = []
    for tkey, t in TAXONOMY.items():
        subs = ", ".join(f"{sk} ({sv})" for sk, sv in t["subtopics"].items())
        lines.append(f"- {tkey} ({t['label']}): subtopics: {subs}")
    return "\n".join(lines)


CLASSIFY_SYSTEM = f"""You classify posts from pro-Kremlin Russian military Telegram channels for an OSINT analyst.

For each post decide:
1. substantive: false for ads, fundraisers, merchandise, channel promos, podcasts/stream announcements, memes, greetings, personal notes and content with no analytical value. true otherwise.
2. topic and subtopic (only for substantive posts), from this fixed taxonomy:
{taxonomy_prompt()}
   Use topic "criticism" when the post's MAIN point is complaint or blame directed at Russian institutions or officials.
   If nothing fits well, pick the closest topic and subtopic "other".
3. sentiment: the blogger's own mood about the subject, seen from Russia's perspective.
   "pos" = celebrating, triumphant, confident. "neg" = worried, angry, frustrated, mournful. "neu" = factual/mixed.
   For criticism posts always use "neg".
4. summary_en: one short English sentence (max 25 words) stating the post's key claim, specific and factual.

For non-substantive posts set topic to "none", subtopic to "none", sentiment to "neu", summary_en to "".
Return one result per input post, matching each post's "n"."""

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "posts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "substantive": {"type": "boolean"},
                    "topic": {"type": "string", "enum": list(TAXONOMY.keys()) + ["none"]},
                    "subtopic": {"type": "string"},
                    "sentiment": {"type": "string", "enum": ["pos", "neu", "neg"]},
                    "summary_en": {"type": "string"},
                },
                "required": ["n", "substantive", "topic", "subtopic", "sentiment", "summary_en"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["posts"],
    "additionalProperties": False,
}


def classify_posts(posts: list[dict]) -> list[dict]:
    """Classify raw posts. Returns one dict per post with classification merged in."""
    results = []
    to_classify = []
    for p in posts:
        item = {
            "channel": p["channel"],
            "channel_label": CHANNEL_LABELS.get(p["channel"], p["channel"]),
            "message_id": p["message_id"],
            "link": p["link"],
            "date_utc": p["date_utc"],
            "views": int(p["views"] or 0),
            "forwards": int(p["forwards"] or 0),
            "text": p["text"],
        }
        if len(p["text"].strip()) < MIN_TEXT_LEN:
            item.update(substantive=False, topic="none", subtopic="none",
                        sentiment="neu", summary_en="")
            results.append(item)
        else:
            to_classify.append(item)

    for start in range(0, len(to_classify), BATCH_SIZE):
        batch = to_classify[start:start + BATCH_SIZE]
        payload = [{"n": i, "channel": it["channel_label"], "text": it["text"][:900]}
                   for i, it in enumerate(batch)]
        response = client.messages.create(
            model=CLASSIFY_MODEL,
            max_tokens=6000,
            system=[{"type": "text", "text": CLASSIFY_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            output_config={"format": {"type": "json_schema", "schema": CLASSIFY_SCHEMA}},
        )
        text = next(b.text for b in response.content if b.type == "text")
        by_n = {r["n"]: r for r in json.loads(text)["posts"]}
        for i, it in enumerate(batch):
            r = by_n.get(i, {})
            topic = r.get("topic", "none")
            subtopic = r.get("subtopic", "other")
            if topic in TAXONOMY and subtopic not in TAXONOMY[topic]["subtopics"]:
                subtopic = "other"
            it.update(
                substantive=bool(r.get("substantive", False)) and topic in TAXONOMY,
                topic=topic if topic in TAXONOMY else "none",
                subtopic=subtopic if topic in TAXONOMY else "none",
                sentiment=r.get("sentiment", "neu"),
                summary_en=r.get("summary_en", ""),
            )
        results.extend(batch)
        done = min(start + BATCH_SIZE, len(to_classify))
        print(f"  classified {done}/{len(to_classify)}")

    return results


# ---------------------------------------------------------------- aggregation

def aggregate(classified: list[dict]) -> dict:
    subs = [p for p in classified if p["substantive"]]
    topics = {}
    for tkey, t in TAXONOMY.items():
        tp = [p for p in subs if p["topic"] == tkey]
        neg = sum(1 for p in tp if p["sentiment"] == "neg")
        neu = sum(1 for p in tp if p["sentiment"] == "neu")
        pos = sum(1 for p in tp if p["sentiment"] == "pos")
        n = len(tp)
        topics[tkey] = {
            "label": t["label"], "posts": n,
            "neg": neg, "neu": neu, "pos": pos,
            "net": round((pos - neg) / n * 100) if n else None,
        }
    subtopics = []
    for tkey, t in TAXONOMY.items():
        for skey, slabel in t["subtopics"].items():
            sp = [p for p in subs if p["topic"] == tkey and p["subtopic"] == skey]
            neg = sum(1 for p in sp if p["sentiment"] == "neg")
            pos = sum(1 for p in sp if p["sentiment"] == "pos")
            n = len(sp)
            subtopics.append({
                "topic": tkey, "subtopic": skey, "label": slabel, "posts": n,
                "channels": len({p["channel"] for p in sp}),
                "neg": neg, "neu": n - neg - pos, "pos": pos,
                "net": round((pos - neg) / n * 100) if n else None,
            })
    channels = {}
    for p in subs:
        channels[p["channel_label"]] = channels.get(p["channel_label"], 0) + 1
    top_viewed = sorted(subs, key=lambda p: -p["views"])[:5]
    top_forwarded = sorted(subs, key=lambda p: -p["forwards"])[:3]
    strip = lambda p: {k: p[k] for k in
                       ("channel_label", "link", "views", "forwards", "summary_en")}
    overall_n = len(subs)
    overall_pos = sum(1 for p in subs if p["sentiment"] == "pos")
    overall_neg = sum(1 for p in subs if p["sentiment"] == "neg")
    return {
        "total_posts": len(classified),
        "substantive_posts": overall_n,
        "sentiment_overall": {
            "pos_pct": round(overall_pos / overall_n * 100) if overall_n else 0,
            "neg_pct": round(overall_neg / overall_n * 100) if overall_n else 0,
            "neu_pct": round((overall_n - overall_pos - overall_neg) / overall_n * 100) if overall_n else 0,
        },
        "topics": topics,
        "subtopics": subtopics,
        "channels": dict(sorted(channels.items(), key=lambda kv: -kv[1])),
        "top_viewed": [strip(p) for p in top_viewed],
        "top_forwarded": [strip(p) for p in top_forwarded],
    }


# ---------------------------------------------------------------- flags

def compute_flags(day: str, agg: dict) -> list[dict]:
    flags = []
    history = prior_subtopic_history(day)
    for row in agg["subtopics"]:
        key = (row["topic"], row["subtopic"])
        if row["subtopic"] == "other":
            continue
        if row["posts"] >= 3 and row["channels"] >= 2 and history.get(key, 0) == 0 and history:
            flags.append({"type": "new_topic", "topic": row["topic"],
                          "subtopic": row["subtopic"], "label": row["label"],
                          "posts": row["posts"], "channels": row["channels"]})
    prev = load_day_json(str(datetime.date.fromisoformat(day) - datetime.timedelta(days=1)))
    if prev:
        for tkey, t in agg["topics"].items():
            pt = prev.get("topics", {}).get(tkey, {})
            if t["net"] is not None and pt.get("net") is not None and t["posts"] >= 4:
                move = t["net"] - pt["net"]
                if abs(move) >= 25:
                    flags.append({"type": "mood_swing", "topic": tkey,
                                  "label": t["label"], "net": t["net"], "move": move})
    watch_alerts, watch_quiet = [], []
    sub_by_key = {(r["topic"], r["subtopic"]): r for r in agg["subtopics"]}
    for tkey, skey, wlabel in WATCHLIST:
        row = sub_by_key.get((tkey, skey), {})
        if row.get("posts", 0) > 0 and row.get("channels", 0) >= 2:
            watch_alerts.append({"type": "watchlist_alert", "label": wlabel,
                                 "posts": row["posts"], "channels": row["channels"]})
        else:
            watch_quiet.append(wlabel)
    return flags + watch_alerts + [{"type": "watchlist_quiet", "items": watch_quiet}]


# ---------------------------------------------------------------- brief (Opus)

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "lead": {"type": "string"},
        "developments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "corroboration": {"type": "string", "enum": ["multi", "single"]},
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"label": {"type": "string"}, "url": {"type": "string"}},
                            "required": ["label", "url"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["title", "body", "corroboration", "sources"],
                "additionalProperties": False,
            },
        },
        "narrative_watch": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "enum": ["RISING", "STEADY", "NEW"]},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["tag", "title", "body", "url"],
                "additionalProperties": False,
            },
        },
        "mood_lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "arrow": {"type": "string", "enum": ["up", "down", "flat"]},
                    "text": {"type": "string"},
                },
                "required": ["topic", "arrow", "text"],
                "additionalProperties": False,
            },
        },
        "flag_texts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["type", "title", "body"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["headline", "lead", "developments", "narrative_watch", "mood_lines", "flag_texts"],
    "additionalProperties": False,
}

BRIEF_SYSTEM = """You are an OSINT analyst writing the daily brief for ZBloggers Monitor, a tool that tracks 10 major pro-Kremlin military Telegram channels for a Eurasia Group analyst covering the Russia-Ukraine war.

You receive one day's classified posts (with one-line English summaries and links), aggregate statistics, and machine-computed flags. Write:

- headline: max 10 words naming the day's 1-2 defining stories (for the archive list).
- lead: 1-2 sentences on the day's dominant story and the overall tone.
- developments: the 4-6 most analytically important developments, ordered by importance. Each: title (max 12 words), body (1-3 sentences, concrete numbers/places/claims, note when a claim is MoD-sourced or unconfirmed), corroboration ("multi" if 2+ channels independently, else "single"), sources (2-5 links to the actual posts, label = channel name).
- narrative_watch: 1-3 recurring propaganda frames or notable rhetoric worth tracking (not events), each with one source link.
- mood_lines: one line per topic that had posts, describing where sentiment is and any movement. text max 25 words.
- flag_texts: for each machine-computed flag given to you (new_topic, mood_swing, watchlist_alert), a title and 1-2 sentence body explaining it with specifics from the posts. Do not invent flags.

Rules: these channels are propaganda outlets — treat claims as signals, not facts; attribute claims to channels; never adopt their framing as your own voice. Be specific and concrete; no filler. Use only links that appear in the input."""


def write_brief(day: str, agg: dict, flags: list[dict], classified: list[dict]) -> dict:
    subs = [p for p in classified if p["substantive"]]
    posts_in = [{
        "channel": p["channel_label"], "link": p["link"], "topic": p["topic"],
        "subtopic": p["subtopic"], "sentiment": p["sentiment"],
        "views": p["views"], "summary": p["summary_en"],
    } for p in sorted(subs, key=lambda p: (p["topic"], -p["views"]))]
    user_payload = json.dumps({
        "date": day,
        "stats": {k: agg[k] for k in ("total_posts", "substantive_posts",
                                      "sentiment_overall", "topics", "channels")},
        "flags": flags,
        "posts": posts_in,
    }, ensure_ascii=False)
    with client.messages.stream(
        model=BRIEF_MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=BRIEF_SYSTEM,
        messages=[{"role": "user", "content": user_payload}],
        output_config={"format": {"type": "json_schema", "schema": BRIEF_SCHEMA}},
    ) as stream:
        response = stream.get_final_message()
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


# ---------------------------------------------------------------- outputs

def save_day(day: str, agg: dict, flags: list[dict], classified: list[dict],
             brief: dict | None):
    DAYS_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_day_json(day) or {}
    doc = {
        "date": day,
        **agg,
        "flags": flags,
        "brief": brief if brief is not None else existing.get("brief"),
        "posts": [{k: p[k] for k in ("channel", "channel_label", "message_id", "link",
                                     "date_utc", "views", "forwards", "substantive",
                                     "topic", "subtopic", "sentiment", "summary_en")}
                  for p in classified],
    }
    (DAYS_DIR / f"{day}.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def battlefield_block(d: dict) -> dict:
    """Frontline sentiment counts + the day's main battlefield story
    (the most-viewed substantive frontline post's one-line summary)."""
    t = d["topics"].get("frontline", {})
    fl = [p for p in d.get("posts", [])
          if p.get("topic") == "frontline" and p.get("substantive")]
    story = max(fl, key=lambda p: p.get("views") or 0)["summary_en"] if fl else ""
    return {"pos": t.get("pos", 0), "neg": t.get("neg", 0), "neu": t.get("neu", 0),
            "net": t.get("net"), "story": story}


def rebuild_index():
    days = []
    for path in sorted(DAYS_DIR.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        days.append({
            "battlefield": battlefield_block(d),
            "date": d["date"],
            "total": d["total_posts"],
            "substantive": d["substantive_posts"],
            "headline": (d.get("brief") or {}).get("headline", ""),
            "topics": {k: v["posts"] for k, v in d["topics"].items()},
            "nets": {k: v["net"] for k, v in d["topics"].items()},
            "subtopics": {f"{r['topic']}/{r['subtopic']}": r["posts"]
                          for r in d["subtopics"] if r["posts"]},
            "flags": len([f for f in d["flags"]
                          if f["type"] in ("new_topic", "mood_swing", "watchlist_alert")]),
        })
    INDEX_PATH.write_text(json.dumps({"days": days}, ensure_ascii=False, indent=1),
                          encoding="utf-8")


def rebuild_month_csv(month: str):
    """Flat CSV mirror of classifications for one month (openable in Excel)."""
    rows = []
    for path in sorted(DAYS_DIR.glob(f"{month}-*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(d["posts"])
    if not rows:
        return
    out = ROOT / "data" / "analysis" / f"classified-{month}.csv"
    fields = ["date_utc", "channel", "message_id", "link", "substantive",
              "topic", "subtopic", "sentiment", "summary_en", "views", "forwards"]
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["date_utc"]))


# ---------------------------------------------------------------- main

def analyze_day(day: str, with_brief: bool = True, brief_only: bool = False):
    print(f"=== {day} ===")
    if brief_only:
        doc = load_day_json(day)
        if not doc:
            raise SystemExit(f"No classification saved for {day} yet")
        classified = doc["posts"]
        for p in classified:
            p.setdefault("channel_label", CHANNEL_LABELS.get(p["channel"], p["channel"]))
        agg = {k: doc[k] for k in ("total_posts", "substantive_posts", "sentiment_overall",
                                   "topics", "subtopics", "channels",
                                   "top_viewed", "top_forwarded")}
        flags = doc["flags"]
    else:
        posts = load_posts_for_day(day)
        if not posts:
            print("  no posts for this day, skipping")
            return
        print(f"  {len(posts)} posts collected")
        classified = classify_posts(posts)
        agg = aggregate(classified)
        flags = compute_flags(day, agg)
        print(f"  {agg['substantive_posts']} substantive, "
              f"{len([f for f in flags if f['type'] != 'watchlist_quiet'])} flags")
    brief = None
    if with_brief or brief_only:
        print("  writing brief (Opus)...")
        brief = write_brief(day, agg, flags, classified)
        print(f"  headline: {brief['headline']}")
    save_day(day, agg, flags, classified, brief)
    rebuild_index()
    rebuild_month_csv(day[:7])
    print("  saved")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="UTC day to analyze (YYYY-MM-DD); default yesterday")
    parser.add_argument("--backfill", type=int, help="classify the last N days (no briefs)")
    parser.add_argument("--no-brief", action="store_true")
    parser.add_argument("--brief-only", action="store_true")
    args = parser.parse_args()

    today = datetime.datetime.now(datetime.timezone.utc).date()
    if args.backfill:
        for i in range(args.backfill, 0, -1):
            day = str(today - datetime.timedelta(days=i))
            if load_day_json(day):
                print(f"=== {day} === already analyzed, skipping")
                continue
            analyze_day(day, with_brief=False)
    else:
        day = args.date or str(today - datetime.timedelta(days=1))
        analyze_day(day, with_brief=not args.no_brief, brief_only=args.brief_only)


if __name__ == "__main__":
    sys.exit(main())
