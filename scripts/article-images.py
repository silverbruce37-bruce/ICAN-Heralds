#!/usr/bin/env python3
"""ICAN Heralds — article-matched photoreal image pipeline.

For every main article of an edition (cover story, featured news, news grid) this
script produces one photorealistic editorial photograph that matches the story,
stores it under images/editions/<date>/ and records it in
data/image-manifest-<date>.json. scripts/inject-direct.py reads that manifest and
links the local file, so the page loads fast, never depends on a random-photo
service, and keeps working on Vercel/GitHub Pages.

Providers, in order (first acceptable image wins):
  1. local   — a file already in images/editions/<date>/ (committed or pre-seeded)
  2. openai  — OpenAI Images API (gpt-image-1 family / dall-e-3) when OPENAI_API_KEY is set
  3. og      — the article's own og:image (real news photograph of that story)
  4. wikimedia — a free-licence photograph from Wikimedia Commons matching the query
  5. flickr  — keyword photo from loremflickr (last resort)

Every candidate is checked for size, resolution, aspect and brightness, so a dark,
abstract or logo-like image is rejected and the next provider is tried instead.

Usage:
    python3 scripts/article-images.py [--date YYYY-MM-DD] [--force]
                                      [--provider openai|og|wikimedia|flickr]
                                      [--only cover,feat,news1] [--no-retry]
"""

import argparse
import base64
import glob
import html as html_mod
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

try:  # Pillow is installed by generate-daily.sh; the script still runs without it.
    from PIL import Image, ImageStat
except Exception:  # pragma: no cover
    Image = None
    ImageStat = None

ROOT = Path(__file__).resolve().parent.parent
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# Wikimedia's robot policy wants a descriptive UA with a contact.
UA = BROWSER_UA
WIKI_UA = (
    "ICAN-Heralds/1.0 (https://ican-heralds.vercel.app; heralds@ican.academy) "
    "python-urllib/3.12 editorial-photo"
)
PHT = timezone.utc

# Display sizes: one file per article is reused for the hero and the 280x220 thumb
# (CSS object-fit: cover crops it), so the hero size decides the file.
TARGETS = {
    "cover": (1440, 960),
    "feat": (1200, 800),
    "news": (960, 720),
}
JPEG_QUALITY = 78
MIN_LUMA = 62          # reject dark, moody images — the paper uses a bright light theme
MAX_LUMA = 248         # reject blown-out / white-on-white images
MIN_STDDEV = 14        # reject flat colour fields / blank images

STYLE = (
    "A real press photograph. CRITICAL: the picture contains no words, letters, numbers, logos or "
    "brand marks anywhere — no signage, posters, banners, badges, number plates, product labels, "
    "newspaper mastheads, news tickers or on-screen graphics; any screen, board or display is blank "
    "or soft out-of-focus light. "
    "Photorealistic editorial news photograph, natural bright daylight, well-lit clean scene, "
    "true-to-life colours, sharp focus, shallow depth of field, 35mm lens, wide landscape framing. "
    "No illustration, no 3D render, no digital art, no collage. Bright and optimistic tone; avoid "
    "night scenes, heavy shadows, neon and abstract patterns. Show anonymous everyday people only — "
    "no recognizable public figures or politicians."
)

# Subjects that make an image model draw text; they are rewritten to plain visuals.
TEXT_PRONE = [
    (re.compile(r"\bscreens?\b", re.I), "plain displays seen at a distance"),
    (re.compile(r"\bmonitors?\b", re.I), "desks with plain displays"),
    (re.compile(r"\bnewsroom\b", re.I), "modern open-plan office"),
    (re.compile(r"\btickers?\b", re.I), "glowing display panels"),
    (re.compile(r"\bnews ?paper\b", re.I), "folded papers"),
]

# Words that suggest a photo of the story's own place. Used to enrich short queries.
COUNTRY_HINTS = ("philippin", "manila", "cebu", "davao", "visayas", "mindanao", "luzon", "pasig", "makati")

PUBLIC_FIGURE = re.compile(
    r"\b(marcos|duterte|sara duterte|romualdez|trump|xi jinping|putin|kim jong|lee jae|"
    r"president|vice president|senator|congressman|governor|mayor)\b",
    re.I,
)


def log(msg):
    print(f"  [img] {msg}", flush=True)


def warn(msg):
    print(f"  [img] {msg}", file=sys.stderr, flush=True)


# ── edition loading ────────────────────────────────────────────────────────────

def resolve_date(explicit):
    if explicit:
        return explicit
    files = sorted(glob.glob(str(ROOT / "data" / "daily-*.json")))
    if not files:
        raise SystemExit("ERROR: no data/daily-*.json found")
    return Path(files[-1]).stem.replace("daily-", "")


def load_jobs(date):
    path = ROOT / "data" / f"daily-{date}.json"
    if not path.exists():
        raise SystemExit(f"ERROR: {path} not found")
    daily = json.loads(path.read_text(encoding="utf-8"))
    jobs = []
    if daily.get("cover_story"):
        jobs.append(("cover", "cover", daily["cover_story"]))
    if daily.get("featured_news"):
        jobs.append(("feat", "feat", daily["featured_news"]))
    for i, item in enumerate(daily.get("news_grid", [])[:4], 1):
        jobs.append((f"news{i}", "news", item))
    return jobs


# ── prompt building ────────────────────────────────────────────────────────────

def anonymize(text):
    """Drop real names from a photo brief: an image model cannot show a real person."""
    out = PUBLIC_FIGURE.sub("a government official", str(text or ""))
    out = re.sub(r"\bthe a government official", "a government official", out, flags=re.I)
    return out


def scene_words(article):
    """A concrete, photo-able subject line for the article."""
    query = " ".join(str(article.get("image_query") or "").split())
    headline = " ".join(str(article.get("headline_en") or "").split())
    summary = " ".join(
        str(article.get("summary_en") or article.get("lead_en") or article.get("subtitle_en") or "").split()
    )

    subject = query
    if not subject or len(subject) < 4:
        # Fall back to the headline, minus any public figure's name.
        subject = anonymize(headline).strip(" ,.-")
    subject = anonymize(subject).strip(" ,.-")
    for pattern, replacement in TEXT_PRONE:
        subject = pattern.sub(replacement, subject)
    if not subject:
        subject = "Philippine daily life"

    detail = ""
    if summary:
        first = re.split(r"(?<=[.!?])\s", summary)[0]
        first = anonymize(first)
        if len(first) > 24:
            detail = first[:220]

    place = ""
    blob = f"{subject} {headline}".lower()
    if not any(h in blob for h in COUNTRY_HINTS):
        place = "Set in the Philippines, Southeast Asia."

    parts = [f"Subject: {subject}."]
    if detail:
        parts.append(f"Story context: {detail}")
    if place:
        parts.append(place)
    parts.append(STYLE)
    return " ".join(parts)


def thumb_query(article):
    q = " ".join(str(article.get("image_query") or "").split())
    if not q:
        q = " ".join(str(article.get("headline_en") or "").split())[:80]
    return q


def compose_search(article):
    """Search terms for Wikimedia Commons: the story subject plus its setting."""
    q = thumb_query(article)
    q = anonymize(q).strip(" ,.")
    blob = q.lower()
    if not any(h in blob for h in COUNTRY_HINTS):
        q = f"{q} Philippines"
    return q.strip() or "Philippines"


# ── image validation & finishing ───────────────────────────────────────────────

def analyse(raw):
    """Return (width, height, luma, stddev) or None when the bytes are not an image."""
    if not Image or not raw:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im = im.convert("RGB")
            w, h = im.size
            small = im.copy()
            small.thumbnail((240, 240))
            grey = small.convert("L")
            stat = ImageStat.Stat(grey)
            return w, h, float(stat.mean[0]), float(stat.stddev[0])
    except Exception:
        return None


def acceptable(raw, kind, min_width=640):
    info = analyse(raw)
    if info is None:
        # No Pillow: fall back to a plain byte-size sanity check.
        return (len(raw) >= 22000, {"bytes": len(raw)})
    w, h, luma, sd = info
    if w < min_width or h < int(min_width * 0.55):
        return False, {"reason": f"small {w}x{h}"}
    ratio = w / max(h, 1)
    if ratio < 1.05 or ratio > 2.6:
        return False, {"reason": f"aspect {ratio:.2f}"}
    if luma < MIN_LUMA:
        return False, {"reason": f"too dark luma {luma:.0f}"}
    if luma > MAX_LUMA:
        return False, {"reason": f"too bright luma {luma:.0f}"}
    if sd < MIN_STDDEV:
        return False, {"reason": f"flat stddev {sd:.0f}"}
    return True, {"width": w, "height": h, "luma": round(luma, 1), "stddev": round(sd, 1)}


def finish(raw, target, quality=JPEG_QUALITY):
    """Crop to the target aspect, resize, and re-encode as a progressive JPEG."""
    if not Image:
        return raw, None
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im = im.convert("RGB")
            tw, th = target
            target_ratio = tw / th
            w, h = im.size
            ratio = w / h
            if ratio > target_ratio:  # too wide → crop sides
                new_w = int(h * target_ratio)
                left = (w - new_w) // 2
                im = im.crop((left, 0, left + new_w, h))
            elif ratio < target_ratio:  # too tall → crop top/bottom
                new_h = int(w / target_ratio)
                top = max(0, int((h - new_h) * 0.45))
                im = im.crop((0, top, w, top + new_h))
            if im.size[0] > tw:
                im = im.resize((tw, th), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
            return buf.getvalue(), {"width": tw, "height": th}
    except Exception as exc:  # pragma: no cover
        warn(f"finish failed ({exc}); keeping original bytes")
        return raw, None


# ── providers ──────────────────────────────────────────────────────────────────

def http_get(url, timeout=25, accept=None, referer=None, ua=None):
    headers = {"User-Agent": ua or UA}
    if accept:
        headers["Accept"] = accept
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("Content-Type", ""), resp.geturl()


def http_post_json(url, payload, headers, timeout=180):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body[:400]}
        return exc.code, parsed
    except Exception as exc:
        return 0, {"error": {"message": str(exc)}}


OPENAI_MODELS = ["gpt-image-1", "gpt-image-1-mini", "dall-e-3"]


def provider_openai(prompt, kind, deadline):
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return None, {"reason": "no OPENAI_API_KEY"}
    forced = os.environ.get("OPENAI_IMAGE_MODEL", "").strip()
    models = ([forced] if forced else []) + [m for m in OPENAI_MODELS if m != forced]
    size_map = {
        "cover": "1536x1024",
        "feat": "1536x1024",
        "news": "1536x1024",
    }
    last = {}
    for model in models:
        if time.time() > deadline:
            return None, {"reason": "deadline"}
        payload = {"model": model, "prompt": prompt, "n": 1}
        if model.startswith("dall-e"):
            payload.update({"size": "1792x1024", "quality": "standard", "response_format": "url"})
        else:
            payload.update(
                {
                    "size": size_map.get(kind, "1536x1024"),
                    "quality": os.environ.get("OPENAI_IMAGE_QUALITY", "medium"),
                    "output_format": "jpeg",
                    "background": "opaque",
                }
            )
        code, body = http_post_json(
            "https://api.openai.com/v1/images/generations",
            payload,
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        if code == 200 and body.get("data"):
            item = body["data"][0]
            raw = None
            if item.get("b64_json"):
                raw = base64.b64decode(item["b64_json"])
            elif item.get("url"):
                try:
                    raw, _, _ = http_get(item["url"], timeout=60)
                except Exception as exc:
                    last = {"reason": f"{model} download: {exc}"}
                    continue
            if raw:
                return raw, {"provider": "openai", "model": model, "prompt": prompt}
            last = {"reason": f"{model}: empty response"}
            continue
        msg = str(body.get("error", {}).get("message", body))[:220]
        last = {"reason": f"{model} HTTP {code}: {msg}"}
        warn(f"openai {model} → HTTP {code}: {msg}")
        # 401/403/429 → the key or the quota is the problem; other models won't help,
        # except for a 429 where a short wait is worth one retry.
        if code in (401, 403):
            break
        if code == 429:
            time.sleep(min(20, max(5, deadline - time.time())))
        if code == 400 and "model" not in msg.lower():
            # Parameter problem for this model family — try the next model anyway.
            continue
    return None, last or {"reason": "openai failed"}


def candidate_og_urls(page_html):
    urls = []
    patterns = [
        r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
    ]
    for pat in patterns:
        for m in re.finditer(pat, page_html, re.I):
            url = html_mod.unescape(m.group(1)).strip()
            if url and url not in urls:
                urls.append(url)
    return urls


BAD_IMAGE_URL = re.compile(r"(logo|icon|avatar|placeholder|default[-_]|sprite|banner|favicon|seal|watermark)", re.I)


def provider_og(article, deadline):
    page = article.get("source_url")
    if not page:
        return None, {"reason": "no source_url"}
    try:
        body, _, _ = http_get(page, timeout=18, accept="text/html")
        page_html = body.decode("utf-8", "ignore")
    except Exception as exc:
        return None, {"reason": f"page fetch: {exc}"}
    for url in candidate_og_urls(page_html)[:4]:
        if time.time() > deadline:
            return None, {"reason": "deadline"}
        if BAD_IMAGE_URL.search(url):
            continue
        try:
            raw, ctype, _ = http_get(url, timeout=25, referer=page)
        except Exception:
            continue
        if "image" not in ctype and not raw[:3] == b"\xff\xd8\xff":
            continue
        ok, meta = acceptable(raw, "og", min_width=900)
        if ok:
            return raw, {"provider": "og", "credit": article.get("source_name", ""), "source_url": page, "image_url": url}
        warn(f"og rejected ({meta.get('reason')}): {url[-60:]}")
    return None, {"reason": "no usable og:image"}


STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "for", "to", "and", "with", "over", "under",
    "after", "before", "from", "by", "as", "is", "are", "its", "his", "her", "new", "says",
}


def provider_wikimedia(query, deadline):
    words = [w for w in re.findall(r"[A-Za-z]{3,}", query.lower()) if w not in STOPWORDS]
    if not words:
        return None, {"reason": "empty query"}
    search = "filetype:bitmap " + " ".join(words[:5])
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": search,
        "gsrnamespace": "6",
        "gsrlimit": "10",
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": "1400",
    }
    api = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    try:
        body, _, _ = http_get(api, timeout=20, accept="application/json", ua=WIKI_UA)
        data = json.loads(body.decode("utf-8", "ignore"))
    except Exception as exc:
        return None, {"reason": f"commons api: {exc}"}
    pages = list((data.get("query") or {}).get("pages", {}).values())
    pages.sort(key=lambda p: -(p.get("imageinfo", [{}])[0].get("width") or 0))
    for page in pages:
        if time.time() > deadline:
            return None, {"reason": "deadline"}
        title = page.get("title", "")
        if re.search(r"(logo|map|diagram|seal|flag|chart|coat of arms|plaque|sign)", title, re.I):
            continue
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("mime") not in ("image/jpeg", "image/png"):
            continue
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        try:
            raw, ctype, _ = http_get(url, timeout=25, ua=WIKI_UA)
        except Exception:
            continue
        ok, meta = acceptable(raw, "wikimedia", min_width=800)
        if ok:
            return raw, {"provider": "wikimedia", "credit": "Wikimedia Commons", "image_url": url, "title": title}
        warn(f"wikimedia rejected ({meta.get('reason')}): {title[:60]}")
    return None, {"reason": "no usable commons image"}


def provider_openverse(query, deadline):
    """CC-licensed real photographs from Openverse (no key needed)."""
    words = [w for w in re.findall(r"[A-Za-z]{3,}", query.lower()) if w not in STOPWORDS]
    attempts = [" ".join(words[:4]), " ".join(words[-2:]) if len(words) > 1 else ""]
    for terms in [t for t in attempts if t.strip()]:
        if time.time() > deadline:
            return None, {"reason": "deadline"}
        params = {"q": terms, "page_size": "8", "license_type": "all", "aspect_ratio": "wide"}
        api = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params)
        try:
            body, _, _ = http_get(api, timeout=20, accept="application/json", ua=WIKI_UA)
            data = json.loads(body.decode("utf-8", "ignore"))
        except Exception as exc:
            warn(f"openverse api: {exc}")
            continue
        results = [r for r in data.get("results", []) if r.get("url")]
        results.sort(key=lambda r: -(r.get("width") or 0))
        for item in results:
            if time.time() > deadline:
                return None, {"reason": "deadline"}
            title = str(item.get("title") or "")
            if re.search(r"(logo|map|diagram|seal|flag|chart|clipart|icon)", title, re.I):
                continue
            if (item.get("width") or 0) < 800:
                continue
            try:
                raw, ctype, _ = http_get(item["url"], timeout=25, ua=WIKI_UA)
            except Exception:
                continue
            ok, meta = acceptable(raw, "openverse", min_width=800)
            if ok:
                return raw, {
                    "provider": "openverse",
                    "credit": item.get("creator") or "Openverse",
                    "license": item.get("license", ""),
                    "image_url": item.get("url", ""),
                    "title": title,
                }
            warn(f"openverse rejected ({meta.get('reason')}): {title[:60]}")
    return None, {"reason": "no usable openverse image"}


def provider_flickr(query, deadline):
    words = [w for w in re.findall(r"[A-Za-z]{3,}", query.lower()) if w not in STOPWORDS]
    keyword = ",".join(words[:2]) or "philippines"
    lock = int(hashlib_md5(query)[:6], 16) % 90000
    url = f"https://loremflickr.com/1200/800/{urllib.parse.quote(keyword)}?lock={lock}"
    raw = None
    for attempt in range(2):
        if time.time() > deadline:
            return None, {"reason": "deadline"}
        try:
            raw, ctype, _ = http_get(url, timeout=30)
            break
        except Exception as exc:
            if attempt == 0:
                time.sleep(3)
                continue
            return None, {"reason": f"flickr: {exc}"}
    if not raw:
        return None, {"reason": "flickr: empty"}
    ok, meta = acceptable(raw, "flickr", min_width=500)
    if ok:
        return raw, {"provider": "flickr", "query": keyword}
    return None, {"reason": f"flickr rejected ({meta.get('reason')})"}


def hashlib_md5(text):
    import hashlib

    return hashlib.md5(text.encode("utf-8")).hexdigest()


# ── one article ────────────────────────────────────────────────────────────────

def process(job, date, force, only_provider, deadline):
    key, kind, article = job
    target = TARGETS["cover" if kind == "cover" else ("feat" if kind == "feat" else "news")]
    out_dir = ROOT / "images" / "editions" / date
    out_path = out_dir / f"{key}.jpg"
    rel = f"images/editions/{date}/{key}.jpg"

    if out_path.exists() and not force:
        size = out_path.stat().st_size
        if size > 20000:
            return {
                "key": key,
                "src": rel,
                "provider": "local",
                "query": thumb_query(article),
                "bytes": size,
                "status": "kept",
            }

    prompt = scene_words(article)
    query = thumb_query(article)
    attempts = []

    chain = [
        ("openai", lambda: provider_openai(prompt, kind, deadline)),
        ("og", lambda: provider_og(article, deadline)),
        ("wikimedia", lambda: provider_wikimedia(compose_search(article), deadline)),
        ("openverse", lambda: provider_openverse(compose_search(article), deadline)),
        ("flickr", lambda: provider_flickr(query, deadline)),
    ]

    if only_provider:
        chain = [c for c in chain if c[0] == only_provider]

    best = None
    for name, fn in chain:
        if time.time() > deadline:
            attempts.append({"provider": name, "result": "skipped (deadline)"})
            break
        started = time.time()
        try:
            raw, meta = fn()
        except Exception as exc:  # never let one provider kill the edition
            raw, meta = None, {"reason": f"exception: {exc}"}
        took = round(time.time() - started, 1)
        if not raw:
            attempts.append({"provider": name, "result": f"miss ({meta.get('reason', '')}) [{took}s]"})
            continue

        ok, info = acceptable(raw, name, min_width=int(target[0] * 0.62))
        if not ok:
            attempts.append({"provider": name, "result": f"rejected ({info.get('reason')}) [{took}s]"})
            if best is None:
                best = (raw, meta, info)
            continue

        encoded, dims = finish(raw, target)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(encoded)
        _, final_info = acceptable(encoded, name, min_width=int(target[0] * 0.6))
        attempts.append({"provider": name, "result": f"ok [{took}s]"})
        entry = {
            "key": key,
            "src": rel,
            "provider": meta.get("provider", name),
            "model": meta.get("model", ""),
            "query": query,
            "prompt": prompt,
            "credit": meta.get("credit", ""),
            "source_url": meta.get("source_url", article.get("source_url", "")),
            "image_url": meta.get("image_url", ""),
            "bytes": len(encoded),
            "width": (dims or {}).get("width"),
            "height": (dims or {}).get("height"),
            "luma": final_info.get("luma"),
            "status": "created",
            "attempts": attempts,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        return entry

    if best is not None:
        # Nothing passed the quality bar; keep the most usable candidate rather than a placeholder.
        raw, meta, info = best
        encoded, dims = finish(raw, target)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(encoded)
        return {
            "key": key,
            "src": rel,
            "provider": meta.get("provider", "fallback"),
            "query": query,
            "prompt": prompt,
            "credit": meta.get("credit", ""),
            "source_url": article.get("source_url", ""),
            "bytes": len(encoded),
            "width": (dims or {}).get("width"),
            "height": (dims or {}).get("height"),
            "luma": info.get("luma"),
            "status": "below_bar",
            "attempts": attempts,
        }

    return {"key": key, "src": "", "status": "failed", "query": query, "attempts": attempts}


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="edition date (default: newest data/daily-*.json)")
    ap.add_argument("--force", action="store_true", help="regenerate even when a file exists")
    ap.add_argument("--provider", default="", choices=["", "openai", "og", "wikimedia", "flickr"])
    ap.add_argument("--only", default="", help="comma list of keys (cover,feat,news1..4)")
    ap.add_argument("--deadline", type=int, default=int(os.environ.get("IMAGE_DEADLINE_SEC", "540")))
    ap.add_argument("--workers", type=int, default=int(os.environ.get("IMAGE_WORKERS", "2")))
    args = ap.parse_args()

    date = resolve_date(args.date)
    jobs = load_jobs(date)
    if args.only:
        wanted = {k.strip() for k in args.only.split(",") if k.strip()}
        jobs = [j for j in jobs if j[0] in wanted]

    deadline = time.time() + args.deadline
    log(f"edition {date} · {len(jobs)} article images · providers: "
        f"{args.provider or ('openai' if os.environ.get('OPENAI_API_KEY') else 'og/wikimedia/flickr')}"
        f" · Pillow {'yes' if Image else 'no'}")

    results = {}
    if args.workers > 1 and len(jobs) > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(process, job, date, args.force, args.provider, deadline): job[0] for job in jobs}
            for fut, key in futures.items():
                try:
                    results[key] = fut.result()
                except Exception as exc:
                    results[key] = {"key": key, "status": "failed", "error": str(exc)}
    else:
        for job in jobs:
            results[job[0]] = process(job, date, args.force, args.provider, deadline)

    for key in sorted(results):
        r = results[key]
        log(f"{key:6s} {r.get('status','?'):9s} {(r.get('provider') or '-'):9s} "
            f"{r.get('width') or '-'}x{r.get('height') or '-'} "
            f"{round((r.get('bytes') or 0)/1024)}KB luma={r.get('luma')} → {r.get('src') or '(none)'}")
        for a in r.get("attempts", []):
            if not a["result"].startswith("ok") and r.get("status") != "kept":
                log(f"       · {a['provider']}: {a['result']}")

    manifest_path = ROOT / "data" / f"image-manifest-{date}.json"
    existing = {"version": 1, "date": date, "items": {}}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            existing.setdefault("items", {})
        except Exception:
            pass
    existing["date"] = date
    existing["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for key, r in results.items():
        if r.get("src"):
            existing["items"][key] = r
        elif key not in existing["items"]:
            existing["items"][key] = r
    manifest_path.write_text(json.dumps(existing, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    ok = sum(1 for r in results.values() if r.get("src"))
    log(f"manifest → {manifest_path.relative_to(ROOT)} ({ok}/{len(results)} images ready)")
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
