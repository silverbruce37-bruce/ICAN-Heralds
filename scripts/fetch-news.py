#!/usr/bin/env python3
"""ICAN Heralds — real news grounding.

Fetches Philippine / Korea-Philippines headlines from public RSS feeds with a
short timeout and no third-party dependency, then prints a compact digest that
generate-daily.sh injects into the AI prompt. Also writes
data/news-context-<date>.json so scripts/fetch-live-data.py can verify that any
`source_url` the AI returns really came from a feed (no invented links).

Usage:
    python3 scripts/fetch-news.py [--date YYYY-MM-DD] [--json-out PATH]
                                  [--max-items 45] [--digest-only]

The digest is sanitised for safe embedding in a bash double-quoted string
(no backticks, no `$`, no double quotes, no backslashes).
"""

import argparse
import email.utils
import html as html_mod
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

PHT = timezone(timedelta(hours=8))
USER_AGENT = "Mozilla/5.0 (compatible; ICAN-Heralds/2.0; +https://ican-heralds.vercel.app)"
TIMEOUT = 10
MAX_AGE_DAYS = 3
PER_FEED_LIMIT = 10
# Social aggregator noise that Google News sometimes surfaces as an 'outlet'
BLOCKED_SOURCES = {
    "facebook", "youtube", "x", "twitter", "instagram", "tiktok", "linkedin", "reddit", "threads",
}

# cite=True  → the item link is a real article URL the AI may quote as source_url
# cite=False → headline grounding only (Google News links are aggregator redirects)
FEEDS = [
    {"name": "GMA News", "url": "https://data.gmanetwork.com/gno/rss/news/feed.xml", "cite": True},
    {"name": "Philstar", "url": "https://www.philstar.com/rss/headlines", "cite": True},
    {"name": "Rappler", "url": "https://www.rappler.com/feed/", "cite": True},
    {"name": "GMA News · Nation", "url": "https://data.gmanetwork.com/gno/rss/news/nation/feed.xml", "cite": True},
    {
        "name": "Google News · Korea-Philippines",
        "url": "https://news.google.com/rss/search?q=Korea+Philippines&hl=en-PH&gl=PH&ceid=PH:en",
        "cite": False,
    },
    {
        "name": "Google News · Philippines",
        "url": "https://news.google.com/rss/search?q=Philippines&hl=en-PH&gl=PH&ceid=PH:en",
        "cite": False,
    },
    {
        "name": "Google News · Metro Manila",
        "url": "https://news.google.com/rss/search?q=%22Metro+Manila%22&hl=en-PH&gl=PH&ceid=PH:en",
        "cite": False,
    },
    {
        "name": "Google News · Korean community PH",
        "url": "https://news.google.com/rss/search?q=Korean+community+Philippines&hl=en-PH&gl=PH&ceid=PH:en",
        "cite": False,
    },
]


def log(msg):
    print(msg, file=sys.stderr)


def fetch_feed(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_tags(text):
    text = html_mod.unescape(str(text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def parse_date(value):
    if not value:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_feed(raw, feed):
    items = []
    root = ET.fromstring(raw)
    channel = root.find("channel") if root.tag.lower() == "rss" else root
    if channel is None:
        return items
    for node in channel.findall("item"):
        title = strip_tags(node.findtext("title"))
        if not title or len(title) < 12:
            continue
        link = (node.findtext("link") or "").strip()
        desc = strip_tags(node.findtext("description"))[:240]
        pub = parse_date(node.findtext("pubDate") or node.findtext("{http://purl.org/dc/elements/1.1/}date"))
        # Google News wraps the outlet in <source>
        source = strip_tags(node.findtext("source")) or feed["name"]
        if "google.com" in link and source == feed["name"]:
            source = "Google News"
        items.append(
            {
                "title": title,
                "link": link,
                "summary": desc,
                "source": source,
                "feed": feed["name"],
                "published": pub.isoformat() if pub else "",
                "cite": feed["cite"] and link.startswith("http") and "news.google.com" not in link,
                "_pub": pub,
            }
        )
    return items


def normalise(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def sanitize_for_bash(text, limit=150):
    text = " ".join(str(text).split())
    text = text.replace("\\", "/").replace('"', "'").replace("`", "'").replace("$", "")
    text = "".join(ch for ch in text if ch.isprintable())
    return text[:limit]


def clean_title(title, source):
    """Google News appends ' - Outlet' to titles; drop that tail."""
    title = " ".join(title.split())
    for tail in (" - " + source, " | " + source):
        if source and title.endswith(tail):
            title = title[: -len(tail)].strip()
    return title


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(PHT).strftime("%Y-%m-%d"))
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--max-items", type=int, default=45)
    parser.add_argument("--digest-only", action="store_true")
    args = parser.parse_args()

    json_out = args.json_out or "data/news-context-%s.json" % args.date

    collected = []
    report = []
    seen = set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    for feed in FEEDS:
        try:
            raw = fetch_feed(feed["url"])
            items = parse_feed(raw, feed)
        except (urllib.error.URLError, ET.ParseError, OSError, ValueError) as exc:
            report.append({"name": feed["name"], "url": feed["url"], "status": "error:%s" % type(exc).__name__, "count": 0})
            log("  [rss] %-38s FAILED (%s)" % (feed["name"], exc))
            continue

        fresh = 0
        for item in items:
            pub = item.pop("_pub", None)
            if pub is not None and pub < cutoff:
                continue
            if item["source"].strip().lower() in BLOCKED_SOURCES:
                continue
            item["title"] = clean_title(item["title"], item["source"])
            key = normalise(item["title"])
            if not key or key in seen or len(item["title"]) < 25:
                continue
            seen.add(key)
            collected.append(item)
            fresh += 1
            if fresh >= PER_FEED_LIMIT:
                break
        report.append({"name": feed["name"], "url": feed["url"], "status": "ok", "count": fresh})
        log("  [rss] %-38s ok — %d new" % (feed["name"], fresh))

    # Citable real-article links first (newest first), then headline-only items.
    citable = sorted([i for i in collected if i["cite"]], key=lambda i: i["published"], reverse=True)
    headline_only = sorted([i for i in collected if not i["cite"]], key=lambda i: i["published"], reverse=True)
    collected = (citable + headline_only)[: args.max_items]

    payload = {
        "date": args.date,
        "generated_at": datetime.now(PHT).isoformat(),
        "feeds": report,
        "items": collected,
    }

    if not args.digest_only:
        try:
            with open(json_out, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            log("  [rss] saved %s (%d items)" % (json_out, len(collected)))
        except OSError as exc:
            log("  [rss] could not write %s: %s" % (json_out, exc))

    lines = []
    for idx, item in enumerate(collected, 1):
        stamp = (item["published"] or "")[:10]
        head = "[%02d] %s | %s | %s" % (idx, stamp or "undated", sanitize_for_bash(item["source"], 40), sanitize_for_bash(item["title"]))
        if item["cite"]:
            head += " | %s" % sanitize_for_bash(item["link"], 200)
        else:
            head += " | (headline only, no direct link)"
        lines.append(head)

    print("\n".join(lines) if lines else "(no headlines available)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
