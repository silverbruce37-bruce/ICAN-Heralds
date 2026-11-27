#!/usr/bin/env python3
"""ICAN Heralds — Direct HTML builder (no SLOT markers needed).

Builds full ican_news.html from JSON data + HTML template structure.
"""

import json
import sys
import os
import glob
import re
import hashlib
import html
import urllib.parse
from datetime import datetime
from pathlib import Path


CACHE_DIR = Path("images/cache")
EMERGENCY_IMAGE = "images/emergency-placeholder.svg"
# data/image-manifest-<date>.json — article-matched local photos built by
# scripts/article-images.py. Keyed by cover / feat / news1..news4.
IMAGE_MANIFEST = {}

# article key -> deepest knowledge layer that article carries, read from
# data/academy-<date>.json. The LEARN modal and the level pills both read it, so
# a card never promises a level its article does not have.
ACADEMY_DEPTHS = {}
ACADEMY_LAYERS = {}

# Weekly content names fixed places (Manam, Intramuros, museums); these photos live
# in images/static/ and are matched by their content query.
STATIC_RULES = [
    (re.compile(r"sisig|manam"), "images/static/manam.jpg"),
    (re.compile(r"restaurant interior"), "images/static/gallery-food-1.jpg"),
    (re.compile(r"food plating"), "images/static/gallery-food-2.jpg"),
    (re.compile(r"storefront"), "images/static/gallery-food-3.jpg"),
    (re.compile(r"ayala triangle"), "images/static/ayala-triangle.jpg"),
    (re.compile(r"intramuros.*(heritage|walking|walk)|heritage.*intramuros"), "images/static/intramuros-walk.jpg"),
    (re.compile(r"intramuros"), "images/static/intramuros.jpg"),
    (re.compile(r"ayala museum"), "images/static/ayala-museum.jpg"),
    (re.compile(r"national museum"), "images/static/national-museum.jpg"),
    (re.compile(r"pinto art"), "images/static/pinto-art.jpg"),
]
IMAGE_RENDER_LOG = []
IMAGE_STATS = {
    "total": 0,
    "local": 0,
    "remote": 0,
    "emergency": 0,
}


_TOPIC_MAP = [
    (['police', 'patrol', 'crime', 'arrest', 'security', 'guard', 'scam', 'trafficking'],
     'police,philippines'),
    (['military', 'army', 'soldier', 'naval', 'marines', 'defense', 'weapon'],
     'military'),
    (['hospital', 'doctor', 'medical', 'health', 'medicine', 'nurse', 'vaccine', 'disease'],
     'health,philippines'),
    (['school', 'student', 'education', 'university', 'teacher', 'classroom', 'learning'],
     'education,philippines'),
    (['typhoon', 'flood', 'disaster', 'earthquake', 'storm', 'weather', 'rain', 'rescue'],
     'typhoon,philippines'),
    (['technology', 'digital', 'internet', 'computer', 'tech', 'software', 'cyber', 'startup'],
     'technology'),
    (['trade', 'export', 'import', 'commerce', 'tariff', 'customs'],
     'trade,philippines'),
    (['tourism', 'tourist', 'beach', 'travel', 'resort', 'hotel', 'visitor'],
     'tourism,philippines'),
    (['farm', 'rice', 'crop', 'harvest', 'fishing', 'agriculture', 'food'],
     'agriculture,philippines'),
    (['transport', 'traffic', 'train', 'road', 'highway', 'transit', 'infrastructure'],
     'transport,philippines'),
    (['sports', 'athlete', 'game', 'championship', 'basketball', 'boxing', 'tournament'],
     'sports,philippines'),
    (['economy', 'economic', 'finance', 'market', 'investment', 'gdp', 'growth', 'inflation'],
     'economy,philippines'),
    (['official', 'president', 'government', 'senate', 'congress', 'election', 'minister',
      'mayor', 'policy', 'diplomatic', 'agreement', 'signing', 'summit', 'bilateral', 'handshake'],
     'government,philippines'),
]
_TOPIC_DEFAULT = 'philippines,manila'


def _topic_keyword(prompt):
    """Map an article description to a reliable loremflickr keyword pair."""
    text = str(prompt).lower()
    for signals, keyword in _TOPIC_MAP:
        if any(s in text for s in signals):
            return keyword
    return _TOPIC_DEFAULT


def img_url(prompt, w=400, h=200, seed=None, pass_no=1):
    """Realistic editorial photo — loremflickr (pass 1) or Unsplash source (pass 2).

    Topic keyword is inferred from the article description.
    Daily seed ensures a fresh Flickr photo every day for the same topic.
    """
    import urllib.parse

    keyword_str = _topic_keyword(prompt)
    encoded_kw = urllib.parse.quote(keyword_str)

    today = datetime.utcnow().strftime('%Y%m%d')
    seed_source = (str(seed) if seed is not None else str(prompt)[:60]) + today + f"p{pass_no}"
    lock = int(hashlib.md5(seed_source.encode()).hexdigest()[:8], 16) % 50000

    if pass_no == 1:
        return f"https://loremflickr.com/{w}/{h}/{encoded_kw}?lock={lock}"
    else:
        return f"https://source.unsplash.com/{w}x{h}/?{encoded_kw}&sig={lock}"


def cache_key_for_url(url):
    return hashlib.md5(str(url).encode("utf-8")).hexdigest()[:16]


def cache_path_for_url(url):
    return CACHE_DIR / f"{cache_key_for_url(url)}.jpg"


def resolve_cached_url(url):
    if not url:
        return EMERGENCY_IMAGE
    if not str(url).startswith("http"):
        return url
    cache_path = cache_path_for_url(url)
    if cache_path.exists():
        return str(cache_path)
    return url


def classify_image_src(src):
    if not src:
        return "emergency"
    src = str(src)
    if src.startswith("images/"):
        if src.endswith("emergency-placeholder.svg"):
            return "emergency"
        return "local"
    if src.startswith("https://"):
        return "remote"
    return "other"


def manifest_source(key):
    """Local article photo recorded by scripts/article-images.py, when it exists."""
    if not key:
        return None
    entry = (IMAGE_MANIFEST or {}).get(key)
    if not entry:
        return None
    src = str(entry.get("src") or "")
    if not src:
        return None
    if src.startswith("images/") and not Path(src).exists():
        return None
    return entry


def static_source(prompt):
    """Fixed places of the weekly Food & Travel / Events sections — real local photos."""
    text = str(prompt or "").lower()
    for pattern, path in STATIC_RULES:
        if pattern.search(text) and Path(path).exists():
            return path
    return None


def image_sources(prompt, w=400, h=200, seed=None, key=None):
    """Return primary, secondary, and fallback image sources.

    Primary: the article's own local photo (images/editions/<date>/<key>.jpg) when
    scripts/article-images.py produced one for this edition.
    Otherwise: loremflickr keyword photo, then a curated bright editorial photo, then
    the emergency placeholder (source.unsplash.com is retired, so it is not used).
    """
    entry = manifest_source(key)
    if entry is not None:
        return entry["src"], "", entry.get("fallback", EMERGENCY_IMAGE)

    fixed = static_source(prompt)
    if fixed:
        return fixed, "", EMERGENCY_IMAGE

    primary = img_url(prompt, w, h, seed=seed, pass_no=1)
    secondary = fallback_img_url(seed, w, h)
    fallback = EMERGENCY_IMAGE
    return primary, secondary, fallback


def fallback_img_url(seed, w=400, h=200):
    """Stable, bright editorial photo used when the local article photo is absent."""
    photo_map = {
        "cover": "1436491865332-7a61a109cc05",   # airliner taking off, bright sky
        "feat": "1436491865332-7a61a109cc05",
        "news1": "1500382017468-9049fed747ef",   # farm field at golden hour
        "news2": "1492684223066-81342ee5ff30",   # stage with warm lights
        "news3": "1560179707-f14e90ef3623",      # city skyline daylight
        "news4": "1473341304170-971dccb5ac1e",   # power lines / utility poles
        "food": "1414235077428-338989a2e8c0",
        "travel1": "1508009603885-50cf7c579365",
        "travel2": "1518509562904-e7ef99cdcc86",
        "event1": "1492684223066-81342ee5ff30",
        "event2": "1540039155733-5bb30b53aa14",
        "event3": "1570168007204-dfb528c6958f",
        "event4": "1517245386807-bb43f82c33c4",
    }

    seed = str(seed or "cover-default")
    for prefix, photo_id in photo_map.items():
        if seed.startswith(prefix):
            return f"https://images.unsplash.com/photo-{photo_id}?w={w}&h={h}&fit=crop&q=80"

    return f"https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w={w}&h={h}&fit=crop&q=80"


def render_img(src, fallback_src, alt, loading="lazy", class_name="", secondary_src="", extra_attrs=""):
    src = src or EMERGENCY_IMAGE
    class_attr = f' class="{class_name}"' if class_name else ""
    secondary_attr = f' data-secondary-src="{secondary_src}"' if secondary_src else ""
    cache_attr = f' data-cache-path="{cache_path_for_url(src)}"' if src and str(src).startswith("http") else ""
    render_state = classify_image_src(src)
    IMAGE_STATS["total"] += 1
    if render_state in IMAGE_STATS:
        IMAGE_STATS[render_state] += 1
    IMAGE_RENDER_LOG.append(
        {
            "alt": alt or class_name or "image",
            "state": render_state,
            "src": src,
            "secondary": secondary_src or "",
            "fallback": fallback_src or "",
        }
    )
    return (
        f'<img src="{src}"{secondary_attr}{cache_attr} data-fallback-src="{fallback_src}"'
        f' onerror="if(this.dataset.secondarySrc&&this.dataset.retryState!==\'1\'&&this.src!==this.dataset.secondarySrc)'
        f'{{this.dataset.retryState=\'1\';this.src=this.dataset.secondarySrc;return;}}'
        f'if(this.dataset.fallbackSrc&&this.src!==this.dataset.fallbackSrc)'
        f'{{this.onerror=null;this.src=this.dataset.fallbackSrc;}}"'
        f' alt="{alt}"{class_attr} {extra_attrs} loading="{loading}">'
    )


def plain_words(text):
    text = re.sub(r"[^A-Za-z0-9\s-]", " ", str(text or ""))
    return [w for w in text.split() if w]


def derive_key_phrases(article, fallback_text=""):
    raw = str(article.get("image_query", "")).strip()
    if raw:
        phrases = [p.strip() for p in raw.split(",") if p.strip()]
        if phrases:
            return phrases[:3]

    words = plain_words(article.get("headline_en") or fallback_text)
    if not words:
        return ["daily english"]

    chunks = []
    for size in (2, 3):
        for i in range(0, min(len(words) - size + 1, 3)):
            phrase = " ".join(words[i:i + size]).lower()
            if phrase not in chunks:
                chunks.append(phrase)
            if len(chunks) == 3:
                return chunks
    return chunks[:3] or ["daily english"]


def phrase_chips_html(phrases, extra_class=""):
    cls = f"phrase-chip {extra_class}".strip()
    return "".join(f'<span class="{cls}">{phrase}</span>' for phrase in phrases[:3])


def compact_text(text, limit=140):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def load_academy_layers(edition_date):
    """Remember how many knowledge layers each article carries this edition."""
    ACADEMY_DEPTHS.clear()
    ACADEMY_LAYERS.clear()
    path = Path(f"data/academy-{edition_date}.json")
    if not path.exists():
        print(f"  No academy JSON for {edition_date} — level pills fall back to L1-L4")
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"  WARNING: academy JSON unreadable ({exc}) — level pills fall back to L1-L4",
              file=sys.stderr)
        return
    for key, art in data.items():
        layers = [l for l in (art.get("layers") or []) if isinstance(l, dict)]
        depths = sorted({int(l.get("depth", 0) or 0) for l in layers} - {0})
        if depths:
            ACADEMY_DEPTHS[key] = max(depths)
            ACADEMY_LAYERS[key] = {int(l.get("depth", 0) or 0): l for l in layers}
    short = [k for k in ("cover", "featured", "news_1", "news_2", "news_3", "news_4")
             if ACADEMY_DEPTHS.get(k, 0) < 4]
    if short:
        print(f"  WARNING: {', '.join(short)} carry fewer than four layers this edition", file=sys.stderr)


def level_label(article_key, fallback=4):
    depth = ACADEMY_DEPTHS.get(article_key, fallback)
    return "L1" if depth <= 1 else f"L1-L{depth}"


def layer_text(article_key, depth, field):
    layer = (ACADEMY_LAYERS.get(article_key) or {}).get(depth) or {}
    return str(layer.get(field, "") or "").strip()


def build_today_brief(daily):
    cover = daily.get("cover_story", {})
    featured = daily.get("featured_news", {})
    news = daily.get("news_grid", [])
    cards = [
        {
            "label": "Big Story",
            "article_id": "cover",
            "title": cover.get("headline_en", ""),
            "summary": cover.get("subtitle_en", ""),
            "tag": cover.get("author", "Editorial"),
            "level": level_label("cover"),
            "cta": "Start Learning",
        },
        {
            "label": "Must Know",
            "article_id": "featured",
            "title": featured.get("headline_en", ""),
            "summary": featured.get("lead_en", ""),
            "tag": featured.get("tag", "News"),
            "level": level_label("featured"),
            "cta": "See Why",
        },
    ]

    for idx, item in enumerate(news[:2], start=1):
        cards.append(
            {
                "label": "Quick Hit",
                "article_id": f"news_{idx}",
                "title": item.get("headline_en", ""),
                "summary": item.get("summary_en", ""),
                "tag": item.get("tag", "News"),
                "level": level_label(f"news_{idx}"),
                "cta": "Learn Fast",
            }
        )

    cards_html = ""
    for card in cards:
        phrases = phrase_chips_html(
            derive_key_phrases({"headline_en": card["title"]}, card["summary"]),
            "is-quiet",
        )
        cards_html += f"""
            <article class="brief-card">
                <div class="brief-card-top">
                    <span class="brief-label">{card["label"]}</span>
                    <span class="brief-level">{card["level"]}</span>
                </div>
                <h3>{card["title"]}</h3>
                <p>{compact_text(card["summary"], 150)}</p>
                <div class="brief-phrases">{phrases}</div>
                <div class="brief-actions">
                    <span class="brief-tag">{card["tag"]}</span>
                    <button class="learn-btn learn-btn-compact" onclick="openAcademyAtLevel('{card['article_id']}', 1)"><span class="learn-icon">📚</span>{card["cta"]}</button>
                </div>
            </article>"""

    return f"""
        <section class="today-brief">
            <div class="today-brief-heading">
                <div>
                    <span class="section-kicker">Today Brief</span>
                    <h2 class="today-brief-title"><span class="en-content">Today at a Glance — Learn as You Read</span><span class="kr-content">오늘 한눈에 보고, 바로 학습까지</span></h2>
                </div>
                <p class="today-brief-copy"><span class="en-content">Catch the key points first, then jump straight into level-based English learning.</span><span class="kr-content">뉴스를 읽기 전에 핵심만 먼저 잡고, 바로 레벨별 영어 학습으로 이어지게 구성했습니다.</span></p>
            </div>
            <div class="brief-grid">{cards_html}
            </div>
        </section>"""


def build_learning_path(daily):
    """The textbook spine: news -> background layers -> TED-Ed x TOK -> DET/essay."""
    steps = [
        ("01", "Today&rsquo;s News", "오늘의 뉴스", "Read the story first", "오늘 기사를 먼저 읽습니다", "#coverStory", "BRIEF"),
        ("02", "Background Layers", "배경지식 레이어", "Widen L1 → L2 → L3 → L4", "L1 → L2 → L3 → L4로 넓히기", "#learning-track", "L1 – L4"),
        ("03", "TED-Ed × TOK", "TED-Ed × TOK 사고 확장", "Ask what we can know, then face the conundrum", "무엇을 알 수 있는지 묻고, 난제에 도전하기", "#tok-lab", "AOK · WOK · CONUNDRUM"),
        ("04", "DET · Essay", "DET · 에세이 실전", "Say it in 60s, write 150 words", "60초로 말하고 150단어로 쓰기", "#practice-studio", "60 SEC"),
    ]

    cards = ""
    for num, label_en, label_kr, copy_en, copy_kr, anchor, tag in steps:
        cards += f'''
                <a class="learn-path-step" href="{anchor}">
                    <span class="learn-path-num">{num}</span>
                    <span class="learn-path-label">
                        <span class="en-content">{label_en}</span>
                        <span class="kr-content">{label_kr}</span>
                    </span>
                    <span class="learn-path-copy">
                        <span class="en-content">{copy_en}</span>
                        <span class="kr-content">{copy_kr}</span>
                    </span>
                    <span class="learn-path-tag">{tag}</span>
                </a>'''

    return f'''
        <section id="learning-path" class="learn-path">
            <div class="learn-path-head">
                <span class="section-kicker">Today&rsquo;s Learning Flow</span>
                <h2 class="learn-path-title">
                    <span class="en-content">Read it like a newspaper. Study it like a textbook.</span>
                    <span class="kr-content">신문처럼 읽고, 교재처럼 배웁니다</span>
                </h2>
                <p class="learn-path-intro">
                    <span class="en-content">One story, four steps: read the news, widen the background knowledge layer by layer, stretch your thinking with TED-Ed and TOK, then speak and write it yourself.</span>
                    <span class="kr-content">기사 하나로 네 단계: 뉴스를 읽고, 배경지식을 레이어로 넓히고, TED-Ed와 TOK로 사고를 확장한 뒤 직접 말하고 씁니다.</span>
                </p>
            </div>
            <div class="learn-path-track">{cards}
            </div>
        </section>'''


def build_learning_track(daily):
    cover = daily.get("cover_story", {})
    featured = daily.get("featured_news", {})
    news = daily.get("news_grid", [])
    practical = news[3] if len(news) > 3 else featured

    tracks = [
        {
            "eyebrow": "Starter Track",
            "title": "Level 1로 오늘 이슈 시작",
            "copy": featured.get("lead_en", cover.get("subtitle_en", "")),
            "article_id": "featured",
            "level": 1,
            "level_copy": "Foundation",
            "article_name": featured.get("headline_en", ""),
        },
        {
            "eyebrow": "Context Builder",
            "title": "커버스토리로 배경지식 채우기",
            "copy": cover.get("subtitle_en", ""),
            "article_id": "cover",
            "level": 2,
            "level_copy": "Context",
            "article_name": cover.get("headline_en", ""),
        },
        {
            "eyebrow": "Real-life English",
            "title": "생활형 기사로 실전 표현 익히기",
            "copy": practical.get("summary_en", featured.get("lead_en", "")),
            "article_id": "news_4" if len(news) > 3 else "featured",
            "level": 3,
            "level_copy": "Practical",
            "article_name": practical.get("headline_en", ""),
        },
        {
            "eyebrow": "Debate & Insight",
            "title": "L4 토론 질문으로 한 걸음 더",
            "copy": layer_text("cover", 4, "bilingual_en") or "토론과 통찰로 오늘 이슈를 더 깊이 읽습니다.",
            "article_id": "cover",
            "level": 4,
            "level_copy": "Insight",
            "article_name": cover.get("headline_en", ""),
        },
    ]
    tracks = [t for t in tracks if t["level"] <= ACADEMY_DEPTHS.get(t["article_id"], 4)]

    cards_html = ""
    for track in tracks:
        cards_html += f"""
            <article class="learning-track-card">
                <div class="learning-track-top">
                    <span class="learning-track-eyebrow">{track["eyebrow"]}</span>
                    <span class="learning-track-badge">L{track["level"]} · {track["level_copy"]}</span>
                </div>
                <h3>{track["title"]}</h3>
                <p>{compact_text(track["copy"], 150)}</p>
                <div class="learning-track-article">{track["article_name"]}</div>
                <div class="learning-track-actions">
                    <button class="learn-btn" onclick="openAcademyAtLevel('{track['article_id']}', {track['level']})"><span class="learn-icon">📚</span>Start L{track["level"]}</button>
                </div>
            </article>"""

    return f"""
        <section id="learning-track" class="learning-track">
            <span class="step-chip"><b>STEP 02</b><span class="en-content">Background Layers</span><span class="kr-content">배경지식 레이어</span></span>
            <h2 class="section-title">
                <span class="en-content">Learning Track</span>
                <span class="kr-content">레벨별 학습 트랙</span>
            </h2>
            <p class="section-intro">기사를 읽고 끝나지 않도록, 기초 개념(L1)에서 맥락(L2), 실전 표현(L3), 토론·통찰(L4)까지 배경지식을 레이어로 하나씩 쌓는 구간입니다.</p>
            <div class="learning-track-grid">{cards_html}
            </div>
        </section>"""


def build_cache_check_section():
    total = IMAGE_STATS["total"]
    local = IMAGE_STATS["local"]
    remote = IMAGE_STATS["remote"]
    emergency = IMAGE_STATS["emergency"]
    hit_rate = (local / total * 100.0) if total else 0.0
    recent_logs = IMAGE_RENDER_LOG[:12]
    log_html = ""
    for item in recent_logs:
        title = html.escape(item["alt"])
        state = item["state"]
        src = html.escape(item["src"])
        badge_class = f"cache-state-{state}"
        log_html += (
            f'<div class="cache-log-item {badge_class}">'
            f'<span class="cache-log-title">{title}</span>'
            f'<span class="cache-log-state">{state}</span>'
            f'<span class="cache-log-src">{src}</span>'
            f'</div>'
        )

    return f"""
        <section id="image-cache-check" class="cache-check">
            <div class="cache-check-head">
                <div>
                    <span class="section-kicker">Cache Check</span>
                    <h2 class="section-title">이미지 캐시 적중률 점검</h2>
                </div>
                <p class="cache-check-copy">로컬 파일을 먼저 쓰고, 부족할 때만 원격 소스로 내려가는지 확인하는 운영 패널입니다.</p>
            </div>
            <div class="cache-check-stats">
                <div class="cache-stat">
                    <span class="cache-stat-label">Total</span>
                    <span class="cache-stat-value">{total}</span>
                </div>
                <div class="cache-stat">
                    <span class="cache-stat-label">Local Hits</span>
                    <span class="cache-stat-value">{local}</span>
                </div>
                <div class="cache-stat">
                    <span class="cache-stat-label">Remote</span>
                    <span class="cache-stat-value">{remote}</span>
                </div>
                <div class="cache-stat">
                    <span class="cache-stat-label">Emergency</span>
                    <span class="cache-stat-value">{emergency}</span>
                </div>
                <div class="cache-stat cache-stat-wide">
                    <span class="cache-stat-label">Hit Rate</span>
                    <span class="cache-stat-value">{hit_rate:.1f}%</span>
                </div>
            </div>
            <div class="cache-log">{log_html}</div>
        </section>"""


def build_news_cards(news):
    cards = ""
    for i, item in enumerate(news[:4], 1):
        primary, secondary, fallback = image_sources(
            item.get("image_query") or item.get("headline_en", f"news {i}"),
            280,
            220,
            seed=item.get("image_seed"),
            key=f"news{i}",
        )
        phrases = derive_key_phrases(item, item.get("summary_en", ""))
        cards += f'''
                <div class="news-card">
                    <div class="news-thumb">{render_img(primary, fallback, item.get('tag', 'News'), secondary_src=secondary)}</div>
                    <div class="news-card-body">
                        <span class="tag {item.get('tag_class', 'tag-economy')}">{item.get('tag', 'News')}</span>
                        <h3>
                            <span class="en-content">{item.get('headline_en', '')}</span>
                            <span class="kr-content">{item.get('headline_kr', '')}</span>
                        </h3>
                        <p>
                            <span class="en-content">{item.get('summary_en', '')}</span>
                            <span class="kr-content">{item.get('summary_kr', '')}</span>
                        </p>
                        <div class="article-study-meta">
                            <span class="study-pill">{level_label(f'news_{i}')} Path</span>
                            <span class="study-key-label">Key phrase</span>
                        </div>
                        <div class="article-phrase-row">{phrase_chips_html(phrases)}</div>
                        <span class="news-read-time">
                            <span class="en-content">{item.get('read_time_min', 2)} min read</span>
                            <span class="kr-content">{item.get('read_time_min', 2)}분 읽기</span>
                        </span>
                        <button class="learn-btn" onclick="openAcademy('news_{i}')"><span class="learn-icon">📚</span> LEARN</button>
                    </div>
                </div>'''
    return cards


def build_weekly_sections(weekly, date_dot):
    if not weekly:
        return "", "", "", ""

    # ── Food Feature (magazine-style full layout) ──
    food_html = ""
    food = weekly.get("food_feature", {})
    if food:
        must_try_items = ""
        for it in food.get("must_try", []):
            must_try_items += f'''
                            <li>
                                <span class="en-content">{it["en"]} — <strong>{it.get("price","")}</strong></span>
                                <span class="kr-content">{it["kr"]} — <strong>{it.get("price","")}</strong></span>
                            </li>'''

        tags = "\n".join(
            f'<span class="food-type-tag"><span class="en-content">{t["en"]}</span>'
            f'<span class="kr-content">{t["kr"]}</span></span>'
            for t in food.get("cuisine_tags", [])
        )

        food_name = food.get('name_en', 'modern restaurant')
        cuisine = ""
        if food.get('cuisine_tags'):
            cuisine = food['cuisine_tags'][0].get('en', '')
        
        # Simplified gallery prompts to ensure 100% generation success
        gallery_aspects = [
            f"modern restaurant interior design",
            f"Filipino gourmet food plating",
            f"fancy restaurant storefront facade"
        ]
        gallery_seeds = food.get("gallery_seeds", ["food-g1", "food-g2", "food-g3"])
        gallery_imgs = ""
        for i in range(3):
            gallery_primary, gallery_secondary, gallery_fallback = image_sources(
                gallery_aspects[i],
                400,
                300,
                seed=gallery_seeds[i] if i < len(gallery_seeds) else None,
            )
            gallery_imgs += render_img(
                gallery_primary,
                gallery_fallback,
                f"Gallery {i+1}",
                secondary_src=gallery_secondary,
            ) + "\n"

        food_html = f'''
        <section id="food-travel">
            <h2 class="section-title">
                <span class="en-content">Food & Travel</span>
                <span class="kr-content">맛집 · 여행</span>
            </h2>

            <div class="food-feature">
                <div class="food-feature-badge">
                    <span class="en-content">{food.get('badge_en','EDITOR&#39;S CHOICE')}</span>
                    <span class="kr-content">{food.get('badge_kr','에디터 추천')}</span>
                </div>
                <div class="food-feature-gallery">
                    {(
                        lambda hero_primary, hero_secondary, hero_fallback: render_img(
                            hero_primary,
                            hero_fallback,
                            food.get('name_en',''),
                            class_name='food-hero-img',
                            secondary_src=hero_secondary,
                        )
                    )(*image_sources(
                        food.get('image_query') or f"{food.get('name_en','restaurant')} {cuisine} signature dish",
                        1600,
                        900,
                        seed=food.get('hero_image_seed'),
                    ))}
                    <div class="food-gallery-strip">
                        {gallery_imgs}
                    </div>
                </div>
                <div class="food-feature-content">
                    <div class="food-tags">{tags}</div>
                    <h3>
                        <span class="en-content">{food.get('name_en','')}</span>
                        <span class="kr-content">{food.get('name_kr','')}</span>
                    </h3>
                    <div class="food-rating">
                        <span class="stars">{food.get('stars','★★★★★')}</span>
                        <span class="rating-score">{food.get('rating', 4.8)}</span>
                    </div>
                    <p class="food-lead">
                        <span class="en-content">{food.get('lead_en','')}</span>
                        <span class="kr-content">{food.get('lead_kr','')}</span>
                    </p>
                    <blockquote class="food-quote">
                        <span class="en-content">"{food.get('quote_en','')}"</span>
                        <span class="kr-content">"{food.get('quote_kr','')}"</span>
                    </blockquote>
                    <div class="food-details">
                        <div class="food-detail-item">
                            <span class="food-detail-icon">📍</span>
                            <div><strong>Location</strong><br>{food.get('location','')}</div>
                        </div>
                        <div class="food-detail-item">
                            <span class="food-detail-icon">💰</span>
                            <div><strong>Price</strong><br>{food.get('price_range','')}</div>
                        </div>
                        <div class="food-detail-item">
                            <span class="food-detail-icon">🕐</span>
                            <div><strong>Hours</strong><br>{food.get('hours','')}<br>
                            <span class="en-content" style="color:var(--muted);font-size:0.85rem;">{food.get('hours_closed_en','')}</span>
                            <span class="kr-content" style="color:var(--muted);font-size:0.85rem;">{food.get('hours_closed_kr','')}</span></div>
                        </div>
                        <div class="food-detail-item">
                            <span class="food-detail-icon">🗣️</span>
                            <div><strong>Language</strong><br>
                            <span class="en-content">{food.get('language_en','')}</span>
                            <span class="kr-content">{food.get('language_kr','')}</span></div>
                        </div>
                    </div>
                    <div class="food-must-try">
                        <h4>
                            <span class="en-content">Must-Try</span>
                            <span class="kr-content">꼭 먹어볼 것</span>
                        </h4>
                        <ul>{must_try_items}
                        </ul>
                    </div>
                    <div class="food-tip">
                        <span class="food-tip-label">💡 TIP</span>
                        <span class="en-content">{food.get('tip_en','')}</span>
                        <span class="kr-content">{food.get('tip_kr','')}</span>
                    </div>
                </div>
            </div>

            <!-- Travel Cards -->
            <div class="section-intro" style="margin-top:50px;">
                <h3 class="section-title">
                    <span class="en-content">Weekend Escapes</span>
                    <span class="kr-content">주말 여행</span>
                </h3>
            </div>
            {_build_travel_cards(weekly)}
        </section>'''

    # ── Events (with full actionable details) ──
    events_html = ""
    events = weekly.get("events", [])
    if events:
        ecards = ""
        for i, ev in enumerate(events[:4], 1):
            # Support both old format (location_en) and new format (venue_en + address_en)
            venue_en = ev.get('venue_en', ev.get('location_en', ''))
            venue_kr = ev.get('venue_kr', ev.get('location_kr', ''))
            address_en = ev.get('address_en', '')
            address_kr = ev.get('address_kr', '')
            time_en = ev.get('time_en', '')
            time_kr = ev.get('time_kr', '')
            contact = ev.get('contact', '')
            note_en = ev.get('note_en', '')
            note_kr = ev.get('note_kr', '')
            day_en = ev.get('day_of_week_en', '')
            day_kr = ev.get('day_of_week_kr', '')

            date_line = ev.get('date_badge', '')
            if day_en:
                date_line_full = f'{ev.get("date_badge","")} ({day_en})'
                date_line_full_kr = f'{ev.get("date_badge","")} ({day_kr})'
            else:
                date_line_full = date_line
                date_line_full_kr = date_line

            # Build detail rows
            details = ""
            if venue_en:
                details += f'''
                        <div class="event-detail-row">
                            <span class="event-detail-icon">📍</span>
                            <div>
                                <strong><span class="en-content">{venue_en}</span><span class="kr-content">{venue_kr}</span></strong>
                                {"<br><span class='en-content'>" + address_en + "</span><span class='kr-content'>" + address_kr + "</span>" if address_en else ""}
                            </div>
                        </div>'''
            if time_en:
                details += f'''
                        <div class="event-detail-row">
                            <span class="event-detail-icon">🕐</span>
                            <div><span class="en-content">{time_en}</span><span class="kr-content">{time_kr}</span></div>
                        </div>'''
            details += f'''
                        <div class="event-detail-row">
                            <span class="event-detail-icon">🎟️</span>
                            <div><span class="en-content">{ev.get('price_en','')}</span><span class="kr-content">{ev.get('price_kr','')}</span></div>
                        </div>'''
            if contact:
                details += f'''
                        <div class="event-detail-row">
                            <span class="event-detail-icon">📞</span>
                            <div>{contact}</div>
                        </div>'''
            if note_en:
                details += f'''
                        <div class="event-detail-row event-note">
                            <span class="event-detail-icon">💡</span>
                            <div><span class="en-content">{note_en}</span><span class="kr-content">{note_kr}</span></div>
                        </div>'''

            ecards += f'''
                <div class="event-card">
                    <div class="event-date-badge">
                        <span class="en-content">{date_line_full}</span>
                        <span class="kr-content">{date_line_full_kr}</span>
                    </div>
                    <div class="event-image">
                    {(
                        lambda event_primary, event_secondary, event_fallback: render_img(
                            event_primary,
                            event_fallback,
                            ev.get('title',''),
                            secondary_src=event_secondary,
                        )
                    )(*image_sources(
                        ev.get('image_query') or ev.get('title', f'event {i}'),
                        600,
                        400,
                        seed=ev.get('image_seed'),
                    ))}
                    </div>
                    <h3>{ev.get('title','')}</h3>
                    <p class="event-desc">
                        <span class="en-content">{ev.get('desc_en','')}</span>
                        <span class="kr-content">{ev.get('desc_kr','')}</span>
                    </p>
                    <div class="event-details">{details}
                    </div>
                </div>'''
        events_html = f'''
        <section id="events">
            <h2 class="section-title">
                <span class="en-content">Upcoming Events</span>
                <span class="kr-content">주요 행사</span>
            </h2>
            <div class="events-grid">{ecards}
            </div>
        </section>'''

    # ── Herald's Pick ──
    picks_html = ""
    picks = weekly.get("picks", {})
    if picks:
        pbody = "\n".join(
            f'<p><span class="en-content">{en}</span><span class="kr-content">{kr}</span></p>'
            for en, kr in zip(picks.get("body_en", []), picks.get("body_kr", []))
        )
        picks_html = f'''
        <section id="picks">
            <h2 class="section-title">
                <span class="en-content">Herald&rsquo;s Pick</span>
                <span class="kr-content">헤럴드 픽</span>
            </h2>
            <div class="picks-card">
                <div class="picks-date">{picks.get('date', date_dot)}</div>
                <h3>
                    <span class="en-content">{picks.get('title_en','')}</span>
                    <span class="kr-content">{picks.get('title_kr','')}</span>
                </h3>
                {pbody}
            </div>
        </section>'''

    return food_html, "", events_html, picks_html


def _build_travel_cards(weekly):
    """Build travel cards with full design: badge, image, rating, details, tip."""
    travel = weekly.get("travel_cards", [])
    if not travel:
        return ""

    cards = ""
    for i, tc in enumerate(travel[:2], 1):
        tags = "\n".join(
            f'<span class="food-type-tag"><span class="en-content">{t["en"]}</span>'
            f'<span class="kr-content">{t["kr"]}</span></span>'
            for t in tc.get("tags", [])
        )
        cards += f'''
            <div class="travel-card">
                <div class="travel-card-image">
                    {(
                        lambda travel_primary, travel_secondary, travel_fallback: render_img(
                            travel_primary,
                            travel_fallback,
                            tc.get('name_en',''),
                            secondary_src=travel_secondary,
                        )
                    )(*image_sources(
                        tc.get('image_query') or f"{tc.get('name_en','destination')} philippines travel scenic",
                        800,
                        500,
                        seed=tc.get('image_seed'),
                    ))}
                    <div class="travel-badge">
                        <span class="en-content">{tc.get('badge_en','')}</span>
                        <span class="kr-content">{tc.get('badge_kr','')}</span>
                    </div>
                </div>
                <div class="travel-card-body">
                    <div class="food-tags">{tags}</div>
                    <h3>
                        <span class="en-content">{tc.get('name_en','')}</span>
                        <span class="kr-content">{tc.get('name_kr','')}</span>
                    </h3>
                    <div class="food-rating">
                        <span class="stars">{tc.get('stars','★★★★☆')}</span>
                        <span class="rating-score">{tc.get('rating', 4.5)}</span>
                    </div>
                    <p class="food-lead">
                        <span class="en-content">{tc.get('lead_en','')}</span>
                        <span class="kr-content">{tc.get('lead_kr','')}</span>
                    </p>
                    <div class="food-details travel-details-compact">
                        <div class="food-detail-item"><span class="food-detail-icon">📍</span> {tc.get('location','')}</div>
                        <div class="food-detail-item"><span class="food-detail-icon">💰</span> {tc.get('cost','')}</div>
                    </div>
                    <div class="food-tip">
                        <span class="food-tip-label">💡 TIP</span>
                        <span class="en-content">{tc.get('tip_en','')}</span>
                        <span class="kr-content">{tc.get('tip_kr','')}</span>
                    </div>
                </div>
            </div>'''

    return f'<div class="travel-grid">{cards}\n</div>'


def build_practice_studio(daily):
    """DET 1-minute essay practice — one prompt, one timed answer, one evidence link."""
    practice = daily.get("practice", {}) or {}
    word = (daily.get("word_of_day", {}) or {})
    question_en = practice.get("det_question_en", "")
    question_kr = practice.get("det_question_kr", "")
    if not question_en:
        return ""

    steps = [
        ("1", "Position", "입장 밝히기"),
        ("2", "Reason", "이유 제시"),
        ("3", "Example", "예시 들기"),
        ("4", "Close", "마무리"),
    ]
    steps_html = "".join(
        f'<li><span class="practice-step-num">{num}</span>'
        f'<span class="practice-step-en en-content">{en}</span>'
        f'<span class="practice-step-kr kr-content">{kr}</span></li>'
        for num, en, kr in steps
    )

    word_chip = ""
    if word.get("word"):
        word_chip = (
            f'<span class="practice-word-chip"><span class="en-content">today&rsquo;s word</span><span class="kr-content">오늘의 단어</span> · <b>{word.get("word")}</b></span>'
        )

    return f'''
        <section id="practice-studio" class="practice-studio">
            <div class="studio-head">
                <span class="step-chip"><b>STEP 04</b><span class="en-content">DET · Essay Practice</span><span class="kr-content">DET · 에세이 실전</span></span>
                <h2 class="section-title">
                    <span class="en-content">One-Minute Essay Practice</span>
                    <span class="kr-content">1분 에세이 연습</span>
                </h2>
                <p class="studio-copy">
                    <span class="en-content">Last step of the flow: one question, sixty seconds, four moves. Answer out loud first, then write it down.</span>
                    <span class="kr-content">학습 흐름의 마지막 단계입니다. 질문 하나, 60초, 네 단계 — 먼저 소리 내어 말하고, 그 다음 글로 옮겨 보세요.</span>
                </p>
            </div>
            <article class="practice-card">
                <div class="practice-card-top">
                    <span class="practice-badge">DET · 60 SEC</span>
                    {word_chip}
                </div>
                <p class="practice-question">
                    <span class="en-content">{question_en}</span>
                    <span class="kr-content">{question_kr}</span>
                </p>
                <ol class="practice-steps">{steps_html}</ol>
                <p class="practice-note">
                    <span class="en-content">{practice.get("det_link_en", "")}</span>
                    <span class="kr-content">{practice.get("det_link_kr", "")}</span>
                </p>
                <div class="practice-actions">
                    <button class="learn-btn practice-timer-btn" onclick="startDetTimer(this)">
                        <span class="learn-icon">⏱</span>
                        <span class="timer-label">
                            <span class="en-content">Start 60s Timer</span>
                            <span class="kr-content">60초 타이머 시작</span>
                        </span>
                    </button>
                    <a class="learn-btn learn-btn-secondary" href="https://englishtest.duolingo.com/" target="_blank" rel="noopener noreferrer">
                        <span class="learn-icon">↗</span>
                        <span class="en-content">About the DET</span><span class="kr-content">DET 안내</span>
                    </a>
                </div>
            </article>
        </section>'''


def build_dilemma_card(layer):
    """Complex problem-solving challenge: scenario, competing constraints, task, evaluation lens."""
    dilemma = layer.get("complex_dilemma")
    if not isinstance(dilemma, dict):
        return ""

    def pair(key):
        """Read title_en/title_kr style fields, or a single {en, kr} object."""
        base = key[:-3] if key.endswith("_en") else key
        en_raw = dilemma.get(base + "_en") if dilemma.get(base + "_en") is not None else dilemma.get(base)
        kr_raw = dilemma.get(base + "_kr")
        if isinstance(en_raw, dict) or isinstance(kr_raw, dict):
            en, kr = pair_text(en_raw if isinstance(en_raw, dict) else en_raw)
            kr_en, kr_kr = pair_text(kr_raw if isinstance(kr_raw, dict) else kr_raw)
            return en, (kr_kr or kr or en)
        en = str(en_raw or "").strip()
        kr = str(kr_raw or "").strip()
        return en, (kr or en)

    title_en, title_kr = pair("title_en")
    scenario_en, scenario_kr = pair("scenario_en")
    question_en, question_kr = pair("question_en")
    if not question_en:
        return ""

    def item_list(key, minimum=2):
        raw = dilemma.get(key)
        items = []
        for item in raw if isinstance(raw, list) else []:
            en, kr = pair_text(item)
            if en or kr:
                items.append((en, kr))
        return items[:3] if len(items) >= minimum else []

    def pair_text(item):
        if isinstance(item, dict):
            en = str(item.get("en") or item.get("text_en") or "").strip()
            kr = str(item.get("kr") or item.get("text_kr") or "").strip()
        else:
            en = str(item or "").strip()
            kr = ""
        return en, (kr or en)

    def split_criterion(text):
        for dash in (" — ", " – ", " - ", "—"):
            if dash in text:
                head, tail = text.split(dash, 1)
                if head.strip() and tail.strip():
                    return head.strip(), tail.strip()
        return "", text.strip()

    def render_item(index, en, kr):
        return (
            f'<div class="tok-dilemma-item">'
            f'<span class="tok-dilemma-num">{index:02d}</span>'
            f'<p><span class="en-content">{en}</span><span class="kr-content">{kr}</span></p>'
            f'</div>'
        )

    constraints = [
        render_item(i, en, kr) for i, (en, kr) in enumerate(item_list("constraints"), 1)
    ]

    lenses = []
    for en, kr in item_list("evaluation_lens", 2):
        en_head, en_body = split_criterion(en)
        kr_head, kr_body = split_criterion(kr)
        en_html = f'<b>{en_head}</b>{en_body}' if en_head else en_body
        kr_html = f'<b>{kr_head}</b>{kr_body}' if kr_head else kr_body
        if en_head and en_body and not en_body.startswith((" ", "—", "–", "-")):
            en_html = f'<b>{en_head}</b> — {en_body}'
        if kr_head and kr_body and not kr_body.startswith((" ", "—", "–", "-")):
            kr_html = f'<b>{kr_head}</b> — {kr_body}'
        lenses.append(
            f'<span class="tok-lens-chip">'
            f'<span class="en-content">{en_html}</span>'
            f'<span class="kr-content">{kr_html}</span></span>'
        )

    constraints_html = (
        f'''
                <div class="tok-dilemma-block">
                    <span class="tok-dilemma-label"><span class="en-content">Competing constraints</span><span class="kr-content">상충하는 조건</span></span>
                    <div class="tok-dilemma-grid">{"".join(constraints)}</div>
                </div>'''
        if constraints
        else ""
    )
    lens_html = (
        f'''
                <div class="tok-dilemma-block">
                    <span class="tok-dilemma-label"><span class="en-content">Evaluation lens</span><span class="kr-content">평가 기준</span></span>
                    <div class="tok-dilemma-lens">{"".join(lenses)}</div>
                </div>'''
        if lenses
        else ""
    )

    return f'''
                <article class="tok-card tok-card-wide tok-card-dilemma">
                    <div class="tok-dilemma-head">
                        <div class="tok-card-head">
                            <span class="tok-card-icon">🧩</span>
                            <div>
                                <span class="tok-dilemma-kicker">STEP 03 · CONUNDRUM</span>
                                <h3><span class="en-content">{title_en or "Conundrum · Complex Problem-Solving"}</span><span class="kr-content">{title_kr or "Conundrum · 복합 난제 해결 과제"}</span></h3>
                            </div>
                        </div>
                        <span class="tok-dilemma-badge"><span class="en-content">Open-ended · No single answer</span><span class="kr-content">정답 없는 개방형 과제</span></span>
                    </div>
                    <p class="tok-dilemma-scenario">
                        <span class="en-content">{scenario_en}</span>
                        <span class="kr-content">{scenario_kr}</span>
                    </p>{constraints_html}
                <div class="tok-dilemma-task">
                    <span class="tok-dilemma-label"><span class="en-content">Your task</span><span class="kr-content">과제</span></span>
                    <p class="tok-dilemma-question">
                        <span class="en-content">{question_en}</span>
                        <span class="kr-content">{question_kr}</span>
                    </p>
                </div>{lens_html}
                </article>'''


def build_tok_lab(daily):
    """TED-Ed × IB TOK lab: knowledge question, AOK/WOK, Think, Dig Deeper, essay extension."""
    layer = daily.get("knowledge_layer", {}) or {}
    question_en = layer.get("tok_question_en", "")
    question_kr = layer.get("tok_question_kr", "")
    if not question_en:
        return ""

    keyword = str(layer.get("teded_keyword") or "").strip()
    teded_url = "https://ed.ted.com/lessons"
    if keyword:
        teded_url += "?q=" + urllib.parse.quote(keyword)

    concepts = [
        ("Evidence", "근거"),
        ("Certainty", "확실성"),
        ("Interpretation", "해석"),
        ("Perspective", "관점"),
        ("Justification", "정당화"),
        ("Power", "권력"),
        ("Values", "가치"),
        ("Responsibility", "책임"),
    ]
    concepts_html = "".join(
        f'<span class="tok-concept"><span class="en-content">{en}</span>'
        f'<span class="kr-content">{kr}</span></span>'
        for en, kr in concepts
    )

    aok = layer.get("aok_en", "") or ""
    aok_kr = layer.get("aok_kr", "") or aok
    wok = layer.get("wok_en", "") or ""
    wok_kr = layer.get("wok_kr", "") or wok
    dilemma_card = build_dilemma_card(layer)

    return f'''
        <section id="tok-lab" class="tok-lab">
            <div class="tok-head">
                <div>
                    <span class="step-chip"><b>STEP 03</b><span class="en-content">TED-Ed × IB TOK</span><span class="kr-content">TED-Ed × TOK 사고 확장</span></span>
                    <h2 class="section-title tok-title">
                        <span class="en-content">Token of Knowledge Lab</span>
                        <span class="kr-content">토큰 오브 날리지 · TOK 랩</span>
                    </h2>
                    <p class="studio-copy">
                        <span class="en-content">Layers on one story become a question about knowledge itself. Follow the question, test the claim, then face the conundrum and write.</span>
                        <span class="kr-content">한 기사의 레이어가 &lsquo;지식&rsquo;에 대한 질문으로 이어집니다. 질문을 따라가며 주장을 검증하고, 난제에 도전한 뒤 글로 써 보세요.</span>
                    </p>
                </div>
                <span class="tok-badge">TOK · TOKEN OF KNOWLEDGE</span>
            </div>

            <div class="tok-question-block">
                <span class="tok-question-label">
                    <span class="en-content">Knowledge Question</span>
                    <span class="kr-content">지식 질문</span>
                </span>
                <p class="tok-question">
                    <span class="en-content">{question_en}</span>
                    <span class="kr-content">{question_kr}</span>
                </p>
                <div class="tok-tags">
                    <span class="tok-tag"><b>AOK</b><span class="en-content">{aok}</span><span class="kr-content">{aok_kr}</span></span>
                    <span class="tok-tag"><b>WOK</b><span class="en-content">{wok}</span><span class="kr-content">{wok_kr}</span></span>
                </div>
            </div>

            <div class="tok-grid">
                <article class="tok-card tok-card-teded">
                    <div class="tok-card-head">
                        <span class="tok-card-icon">🎬</span>
                        <h3><span class="en-content">TED-Ed Connection</span><span class="kr-content">TED-Ed 연결 탐구</span></h3>
                    </div>
                    <p class="tok-card-copy">
                        <span class="en-content">{layer.get("teded_why_en", "")}</span>
                        <span class="kr-content">{layer.get("teded_why_kr", "")}</span>
                    </p>
                    <span class="tok-keyword">#{keyword or "critical thinking"}</span>
                    <a class="learn-btn" href="{teded_url}" target="_blank" rel="noopener noreferrer">
                        <span class="learn-icon">↗</span>
                        <span class="en-content">Search on TED-Ed</span><span class="kr-content">TED-Ed에서 탐색</span>
                    </a>
                </article>

                <article class="tok-card">
                    <div class="tok-card-head">
                        <span class="tok-card-icon">🧠</span>
                        <h3><span class="en-content">Think</span><span class="kr-content">싱크 · 비판적 사고</span></h3>
                    </div>
                    <p class="tok-card-copy">
                        <span class="en-content">{layer.get("think_task_en", "")}</span>
                        <span class="kr-content">{layer.get("think_task_kr", "")}</span>
                    </p>
                </article>

                <article class="tok-card">
                    <div class="tok-card-head">
                        <span class="tok-card-icon">🔎</span>
                        <h3><span class="en-content">Dig Deeper</span><span class="kr-content">디그 디퍼 · 1차 자료 탐구</span></h3>
                    </div>
                    <p class="tok-card-copy">
                        <span class="en-content">{layer.get("dig_deeper_en", "")}</span>
                        <span class="kr-content">{layer.get("dig_deeper_kr", "")}</span>
                    </p>
                </article>

                <article class="tok-card tok-card-wide">
                    <div class="tok-card-head">
                        <span class="tok-card-icon">⚖️</span>
                        <h3><span class="en-content">Claim vs Counterclaim</span><span class="kr-content">지식 주장 vs 반대 주장</span></h3>
                    </div>
                    <div class="tok-claims">
                        <div class="tok-claim">
                            <span class="tok-claim-label"><span class="en-content">Claim</span><span class="kr-content">주장</span></span>
                            <p><span class="en-content">{layer.get("claim_en", "")}</span><span class="kr-content">{layer.get("claim_kr", "")}</span></p>
                        </div>
                        <div class="tok-claim tok-claim-alt">
                            <span class="tok-claim-label"><span class="en-content">Counterclaim</span><span class="kr-content">반대 주장</span></span>
                            <p><span class="en-content">{layer.get("counterclaim_en", "")}</span><span class="kr-content">{layer.get("counterclaim_kr", "")}</span></p>
                        </div>
                    </div>
                </article>{dilemma_card}

                <article class="tok-card tok-card-wide tok-card-essay">
                    <div class="tok-card-head">
                        <span class="tok-card-icon">✍️</span>
                        <h3><span class="en-content">TOK Essay Extension</span><span class="kr-content">TOK 에세이 확장</span></h3>
                    </div>
                    <div class="tok-essay">
                        <span class="tok-essay-label">
                            <span class="en-content">TOK Essay Extension · 150 words</span>
                            <span class="kr-content">TOK 에세이 확장 · 150단어</span>
                        </span>
                        <p>
                            <span class="en-content">{layer.get("essay_task_en", "")}</span>
                            <span class="kr-content">{layer.get("essay_task_kr", "")}</span>
                        </p>
                    </div>
                </article>
            </div>

            <div class="tok-concepts">
                <span class="tok-concepts-label"><span class="en-content">TOK concepts</span><span class="kr-content">TOK 개념어</span></span>
                {concepts_html}
            </div>
        </section>'''


def build_super_teens_banner():
    """Verified ICAN Academy / Super Teens contact points only (icanacademy.com)."""
    return '''
        <section id="super-teens" class="super-teens">
            <div class="st-inner">
                <div class="st-copy">
                    <span class="st-kicker">NEXT STEP · ICAN ACADEMY · SUPER TEENS</span>
                    <h2 class="st-title">
                        <span class="en-content">Take the flow into class</span>
                        <span class="kr-content">혼자 한 학습 흐름, 수업에서 완성합니다</span>
                    </h2>
                    <p class="st-lead">
                        <span class="en-content">Heralds becomes the textbook: today&rsquo;s story, its background layers, a TOK question and a DET answer — reviewed with a teacher.</span>
                        <span class="kr-content">오늘의 기사 · 배경지식 레이어 · TOK 질문 · DET 답안까지, 헤럴드가 그대로 교재가 됩니다. 상담과 체험 수업으로 이어가세요.</span>
                    </p>
                    <p class="st-meta">16F Strata 100 Building, Emerald Ave, Ortigas Center, Pasig City</p>
                </div>
                <div class="st-actions">
                    <a class="st-btn st-btn-primary" href="https://leveltest.icanacademy.work/" target="_blank" rel="noopener noreferrer">
                        <span class="en-content">Free Level Test</span><span class="kr-content">무료 레벨테스트</span>
                    </a>
                    <a class="st-btn" href="https://pf.kakao.com/_jMuBxb" target="_blank" rel="noopener noreferrer">
                        <span class="en-content">KakaoTalk Chat</span><span class="kr-content">카카오톡 상담</span>
                    </a>
                    <a class="st-btn" href="https://icanacademy.com/" target="_blank" rel="noopener noreferrer">
                        <span class="en-content">Academy Website</span><span class="kr-content">학원 홈페이지</span>
                    </a>
                    <a class="st-btn st-btn-tel" href="tel:070-7014-2233">070-7014-2233</a>
                </div>
            </div>
        </section>'''


def build_html(daily, weekly):
    d = daily
    dash = d.get("dashboard", {})
    cover = d.get("cover_story", {})
    feat = d.get("featured_news", {})
    news = d.get("news_grid", [])
    word = d.get("word_of_day", {})
    date_str = d.get("edition_date", datetime.now().strftime("%Y-%m-%d"))
    date_dot = date_str.replace("-", ".")
    # Append suffix to bust cached static assets after layout update.
    ver = date_str.replace("-", "") + "_v15"

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        date_display = dt.strftime("%A, %B %d, %Y")
    except:
        date_display = date_str

    vol = "05"
    if os.path.exists("data/volume.txt"):
        vol = open("data/volume.txt").read().strip().zfill(2)

    body_en = "\n".join(f"<p>{p}</p>" for p in cover.get("body_en", []))
    body_kr = "\n".join(f"<p>{p}</p>" for p in cover.get("body_kr", []))
    news_cards = build_news_cards(news)
    food_html, _, events_html, picks_html = build_weekly_sections(weekly, date_dot)
    today_brief_html = build_today_brief(daily)
    learning_path_html = build_learning_path(daily)
    learning_track_html = build_learning_track(daily)
    practice_studio_html = build_practice_studio(daily)
    tok_lab_html = build_tok_lab(daily)
    super_teens_html = build_super_teens_banner()
    cache_check_html = "<!--CACHE_CHECK-->"
    cover_phrases = derive_key_phrases(cover, cover.get("subtitle_en", ""))
    feat_phrases = derive_key_phrases(feat, feat.get("lead_en", ""))

    # Live-data honesty: link the original article only when the URL really came from RSS.
    cover_source_url = cover.get("source_url") or "https://www.koreaherald.com/World"
    cover_source_name = cover.get("source_name") or "The Korea Herald · World"
    cover_caption = cover.get("image_caption") or (
        f"Editorial photograph for this story · Source: {cover_source_name}"
    )
    if manifest_source("cover") is not None:
        # Label the caption by what the photo actually is: a real photo or a generated illustration.
        cover_provider = str((IMAGE_MANIFEST.get("cover") or {}).get("provider") or "")
        if cover_provider in ("og", "wikimedia", "openverse", "flickr", "local"):
            cover_caption = re.sub(r"^\s*(Illustration|Illustrative image|Photo):\s*", "Photo: ", cover_caption)
            cover_caption = cover_caption.replace("Editorial illustration", "Editorial photograph")
        elif re.search(r"illustrat|generated", cover_caption, re.I):
            # The model sometimes writes "Photo: Illustrative image …"; drop the contradictory label.
            cover_caption = re.sub(r"^\s*(Illustration|Illustrative image|Photo):\s*", "", cover_caption)
            cover_caption = cover_caption[:1].upper() + cover_caption[1:] if cover_caption else cover_caption
    feat_source_url = feat.get("source_url") or ""
    feat_source_name = feat.get("source_name") or feat.get("desk", "News Desk")
    feat_source_link = (
        f'<a class="learn-btn" href="{feat_source_url}" target="_blank" rel="noopener noreferrer" '
        f'style="margin-left:8px;margin-top:0;"><span class="learn-icon">↗</span> READ</a>'
        if feat_source_url
        else ""
    )
    rate_source_en = dash.get("rate_source_en") or "via exchangerate-api.com"
    rate_source_kr = dash.get("rate_source_kr") or "exchangerate-api.com 기준"
    weather_source = dash.get("weather_source") or ""
    weather_range_en = dash.get("weather_range_en") or ""
    weather_range_kr = dash.get("weather_range_kr") or ""

    word_html = ""
    if word:
        _pron = str(word.get('pronunciation', '')).strip().strip('/').strip('[]')
        _pron = _pron.replace('/', '').strip()
        pron = _pron
        word_html = f'''
        <section class="word-banner">
            <div class="word-inner">
                <div class="word-badge"><span class="en-content">WORD OF THE DAY</span><span class="kr-content">오늘의 단어</span></div>
                <h2 class="word-title">{word.get('word', '')}</h2>
                <div class="word-pronunciation">/{pron}/ — {word.get('type', 'noun')}</div>
                <p class="word-desc"><span class="en-content">{word.get('definition_en', '')}</span><span class="kr-content">{word.get('definition_kr', '')}</span></p>
                <p class="word-example"><span class="en-content"><em>"{word.get('example_en', '')}"</em></span><span class="kr-content"><em>"{word.get('example_kr', '')}"</em></span></p>
                <div class="word-grade">{word.get('grade', 'A+')}</div>
            </div>
        </section>'''

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ICAN HERALDS - Daily Edition</title>
    <link rel="manifest" href="manifest.json">
    <meta name="theme-color" content="#F2F4F6">
    <meta name="description" content="필리핀 한인 커뮤니티를 위한 프리미엄 데일리 뉴스 · 맛집 · 여행 · 문화">
    <link rel="apple-touch-icon" href="images/main_article.png">
    <link rel="stylesheet" href="css/style.css?v={ver}">
</head>
<body>
    <div class="cosmos-bg" aria-hidden="true">
        <div class="stars-layer"></div>
        <div class="orbit-ring orbit-ring-1"></div>
        <div class="orbit-ring orbit-ring-2"></div>
        <div class="constellation-line constellation-1"></div>
        <div class="constellation-line constellation-2"></div>
        <div class="constellation-line constellation-3"></div>
    </div>

    <div id="installBanner" class="install-banner" onclick="installApp()">📲 아이캔헤럴즈를 앱으로 설치하고 매일 아침 필리핀 소식을 받아보세요! (클릭)</div>

    <nav class="nyt-utility-bar">
        <div class="nyt-utility-inner">
            <div class="nyt-utility-left">
                <button class="mobile-menu-btn" onclick="toggleMenu()" aria-label="Menu"><span></span><span></span><span></span></button>
                <button id="langBtn" class="nyt-lang-btn" onclick="toggleLanguage()">EN | 한</button>
            </div>
            <div class="nyt-utility-center"><span class="nyt-dateline-compact">{date_display}</span></div>
            <div class="nyt-utility-right">
                <button class="sos-btn"><span class="en-content">EMERGENCY</span><span class="kr-content">긴급연락</span></button>
            </div>
        </div>
    </nav>

    <header class="nyt-masthead">
        <div class="nyt-masthead-inner">
            <div class="nyt-rule-top"></div>
            <h1 class="nyt-nameplate">ICAN Heralds</h1>
            <div class="nyt-masthead-meta">
                <span class="nyt-meta-left"><span class="en-content">Philippines Edition</span><span class="kr-content">필리핀판</span></span>
                <span class="nyt-meta-motto"><span class="en-content">"Where Value Connects to Create Greater Meaning"</span><span class="kr-content">"가치가 연결되어 더 큰 의미를 만들어 내는 곳"</span></span>
                <span class="nyt-meta-right">Vol. {vol}</span>
            </div>
            <div class="nyt-rule-bottom"></div>
        </div>
    </header>

    <nav class="nyt-sections">
        <div class="nyt-sections-inner">
            <ul class="nyt-section-links">
                <li><a href="#news"><span class="en-content">News</span><span class="kr-content">주요 소식</span></a></li>
                <li><a href="#food-travel"><span class="en-content">Food & Travel</span><span class="kr-content">맛집·여행</span></a></li>
                <li><a href="#events"><span class="en-content">Events</span><span class="kr-content">주요 행사</span></a></li>
                <li><a href="#picks"><span class="en-content">Herald's Pick</span><span class="kr-content">헤럴드 픽</span></a></li>
                <li><a href="#learning-path"><span class="en-content">Learning Flow</span><span class="kr-content">학습 흐름</span></a></li>
                <li><a href="#practice-studio"><span class="en-content">Practice</span><span class="kr-content">1분 연습</span></a></li>
                <li><a href="#tok-lab"><span class="en-content">TOK Lab</span><span class="kr-content">TOK 랩</span></a></li>
                <li><a href="#academy"><span class="en-content">Academy</span><span class="kr-content">아카데미</span></a></li>
                <li><a href="archive.html"><span class="en-content">Archive</span><span class="kr-content">지난 기사</span></a></li>
            </ul>
        </div>
    </nav>

    <div class="container">
        <section class="dashboard">
            <div class="dash-item">
                <span class="dash-label"><span class="en-content">PHP / KRW</span><span class="kr-content">페소 / 원</span></span>
                <span class="dash-value" id="dashRate">{dash.get('php_krw_rate', '')}</span>
                <span class="dash-source"><span class="en-content">{rate_source_en}</span><span class="kr-content">{rate_source_kr}</span></span>
            </div>
            <div class="dash-item">
                <span class="dash-label"><span class="en-content">Manila Weather</span><span class="kr-content">마닐라 날씨</span></span>
                <span class="dash-value">
                    <span class="en-content">{dash.get('weather_en', '')}</span>
                    <span class="kr-content">{dash.get('weather_kr', '')}</span>
                </span>
                <span class="dash-source"><span class="en-content">{weather_range_en}{(' · ' + weather_source) if weather_source else ''}</span><span class="kr-content">{weather_range_kr}{(' · ' + weather_source) if weather_source else ''}</span></span>
            </div>
            <div class="dash-item">
                <span class="dash-label"><span class="en-content">Today's Date</span><span class="kr-content">오늘의 날짜</span></span>
                <span class="dash-value" id="dashDate">{date_dot}</span>
            </div>
            <div class="dash-item">
                <span class="dash-label"><span class="en-content">Embassy Status</span><span class="kr-content">대사관 영사 업무</span></span>
                <span class="dash-value">
                    <span class="en-content">{dash.get('embassy_en', 'Normal')}</span>
                    <span class="kr-content">{dash.get('embassy_kr', '정상 운영')}</span>
                </span>
            </div>
        </section>

        {today_brief_html}

        <section class="headline-section herald-cover-section" id="coverStory">
            <div class="headline-badge"><span class="en-content">WORLD TOP STORY</span><span class="kr-content">월드 탑 스토리</span></div>
            <h2 class="main-title" id="coverStoryTitle"><span class="en-content">{cover.get('headline_en', '')}</span><span class="kr-content">{cover.get('headline_kr', '')}</span></h2>
            <h3 class="sub-title" id="coverStorySubtitle"><span class="en-content">{cover.get('subtitle_en', '')}</span><span class="kr-content">{cover.get('subtitle_kr', '')}</span></h3>
            <div class="cover-learning-strip">
                <div class="cover-learning-summary">
                    <span class="cover-learning-kicker">30-Second Brief</span>
                    <p id="coverStoryBrief">{compact_text(cover.get('subtitle_en', ''), 180)}</p>
                </div>
                <div class="cover-learning-side">
                    <div class="cover-learning-levels">
                        <span class="study-pill">L1 Foundation</span>
                        <span class="study-pill">L2 Context</span>
                        <span class="study-pill">L3 Real-life English</span>{'<span class="study-pill">L4 Debate</span>' if ACADEMY_DEPTHS.get('cover', 4) >= 4 else ''}
                    </div>
                    <div class="article-phrase-row">{phrase_chips_html(cover_phrases)}</div>
                    <div class="cover-learning-actions">
                        <a class="learn-btn" id="coverStoryReadLink" href="{cover_source_url}" target="_blank" rel="noopener noreferrer"><span class="learn-icon">↗</span>Read Original</a>
                        <button class="learn-btn learn-btn-secondary" onclick="openAcademyAtLevel('cover', {ACADEMY_DEPTHS.get('cover', 4)})"><span class="learn-icon">⚡</span>Study English</button>
                    </div>
                </div>
            </div>
            <div class="main-image-container">
                {(
                    lambda cover_primary, cover_secondary, cover_fallback: render_img(
                        cover_primary,
                        cover_fallback,
                        'World Top Story',
                        secondary_src=cover_secondary,
                        extra_attrs='id="coverStoryImage"',
                    )
                )(*image_sources(
                    cover.get('image_query') or cover.get('headline_en', 'cover story'),
                    1200,
                    800,
                    seed=cover.get('image_seed'),
                    key='cover',
                ))}
                <div class="image-caption" id="coverStoryCaption">{cover_caption}</div>
            </div>
            <div class="article-meta">
                <span class="meta-author" id="coverStorySource">{cover_source_name}</span>
                <span class="meta-divider">·</span>
                <span class="meta-time" id="coverStoryPublished"><span class="en-content">Updated daily</span><span class="kr-content">매일 업데이트</span></span>
                <a class="learn-btn" id="coverStoryMetaLink" href="{cover_source_url}" target="_blank" rel="noopener noreferrer" style="margin-left:12px;margin-top:0;"><span class="learn-icon">↗</span> READ</a>
            </div>
            <div class="content-columns" id="coverStoryBody"><div class="column"><div class="en-content">{body_en}</div><div class="kr-content">{body_kr}</div></div></div>
        </section>

        <section id="news">
            <h2 class="section-title"><span class="en-content">Latest Korea-Philippines News</span><span class="kr-content">최신 한-필 주요 뉴스</span><span class="live-badge">LIVE</span></h2>
            <div class="featured-news">
                <div class="featured-news-image">
                    {(
                        lambda feat_primary, feat_secondary, feat_fallback: render_img(
                            feat_primary,
                            feat_fallback,
                            feat.get('tag', 'News'),
                            secondary_src=feat_secondary,
                        )
                    )(*image_sources(
                        feat.get('image_query') or feat.get('headline_en', 'featured news'),
                        900,
                        600,
                        seed=feat.get('image_seed'),
                        key='feat',
                    ))}
                    <span class="tag {feat.get('tag_class', 'tag-security')}">{feat.get('tag', 'News')}</span>
                </div>
                <div class="featured-news-body">
                    <h3><span class="en-content">{feat.get('headline_en', '')}</span><span class="kr-content">{feat.get('headline_kr', '')}</span></h3>
                    <p class="featured-news-lead"><span class="en-content">{feat.get('lead_en', '')}</span><span class="kr-content">{feat.get('lead_kr', '')}</span></p>
                    <div class="article-study-meta">
                        <span class="study-pill">{level_label('featured')} Path</span>
                        <span class="study-key-label">Key phrase</span>
                    </div>
                    <div class="article-phrase-row">{phrase_chips_html(feat_phrases)}</div>
                    <div class="article-meta">
                        <span class="meta-author">{feat_source_name}</span>
                        <span class="meta-divider">·</span>
                        <span class="meta-time"><span class="en-content">{feat.get('read_time_min', 3)} min read</span><span class="kr-content">{feat.get('read_time_min', 3)}분 읽기</span></span>
                        <span class="meta-divider">·</span>
                        <span class="meta-date">{date_dot}</span>
                        {feat_source_link}
                        <button class="learn-btn" onclick="openAcademy('featured')" style="margin-left:8px;margin-top:0;"><span class="learn-icon">📚</span> LEARN</button>
                    </div>
                </div>
            </div>
            <div class="news-grid">{news_cards}
            </div>
        </section>

        {learning_path_html}
        {learning_track_html}
        {word_html}
        {tok_lab_html}
        {practice_studio_html}
        {super_teens_html}
        {food_html}
        {events_html}
        {picks_html}
        {cache_check_html}

    </div>

    <footer class="site-footer">
        <div class="footer-content">
            <div class="footer-brand">
                <svg class="footer-ship" viewBox="0 0 36 56" width="24" height="38" aria-hidden="true">
                    <ellipse cx="18" cy="52" rx="4" ry="3" fill="#2090ff" opacity="0.15"/>
                    <path d="M18 2 C18 2, 13 8, 12.5 16 L12 38 C12 40, 12 44, 13 46 L23 46 C24 44, 24 40, 24 38 L23.5 16 C23 8, 18 2, 18 2Z" fill="#333" stroke="#444" stroke-width="0.4"/>
                    <path d="M12.5 14 L8 19 L9 20 L12.2 17Z" fill="#3a3a3a"/>
                    <path d="M23.5 14 L28 19 L27 20 L23.8 17Z" fill="#3a3a3a"/>
                    <path d="M13 40 L8 47 L10 47 L14 44Z" fill="#3a3a3a"/>
                    <path d="M23 40 L28 47 L26 47 L22 44Z" fill="#3a3a3a"/>
                    <rect x="15" y="10" width="6" height="2.5" rx="1.2" fill="#0047ab" opacity="0.5"/>
                    <circle cx="18" cy="47" r="1.2" fill="#2090ff" opacity="0.2"/>
                </svg>
                <h3>ICAN HERALDS</h3>
                <p><span class="en-content">Where Value Connects to Create Greater Meaning</span><span class="kr-content">가치가 연결되어 더 큰 의미를 만들어 내는 곳</span></p>
            </div>
            <div class="footer-links">
                <a href="#news">News</a><a href="#food-travel">Food & Travel</a><a href="#events">Events</a>
                <a href="#picks">Herald's Pick</a><a href="#academy">Academy</a><a href="archive.html">Archive</a>
            </div>
            <p class="footer-copy"><span class="en-content">&copy; 2026 ICAN Heralds — Daily news for the Korean community in the Philippines.</span><span class="kr-content">&copy; 2026 아이캔 헤럴즈 — 필리핀 한인 커뮤니티를 위한 데일리 뉴스.</span></p>
            <p class="footer-verse">"모든 것을 사랑으로 하라." — 고린도전서 16:14</p>
        </div>
    </footer>

    <div id="sosModal" class="sos-modal-overlay" onclick="closeSOS(event)">
        <div class="sos-modal">
            <button class="sos-close" onclick="closeSOS()">&times;</button>
            <div class="sos-header"><div class="sos-icon">🚨</div><h2><span class="en-content">Emergency Contacts</span><span class="kr-content">긴급 연락처</span></h2></div>
            <div class="sos-grid">
                <a href="tel:911" class="sos-card sos-police"><div class="sos-card-icon">🚔</div><div class="sos-card-title"><span class="en-content">Police / Fire / Ambulance</span><span class="kr-content">경찰 / 소방 / 구급</span></div><div class="sos-card-number">911</div></a>
                <a href="tel:+6328856-9210" class="sos-card sos-embassy"><div class="sos-card-icon">🇰🇷</div><div class="sos-card-title"><span class="en-content">Korean Embassy</span><span class="kr-content">주필리핀 한국대사관</span></div><div class="sos-card-number">+63-2-8856-9210</div></a>
                <a href="tel:+6328856-9210" class="sos-card sos-consular"><div class="sos-card-icon">🆘</div><div class="sos-card-title"><span class="en-content">Consular Emergency (24h)</span><span class="kr-content">영사 긴급전화 (24시간)</span></div><div class="sos-card-number">+63-2-8856-9210</div></a>
                <a href="tel:1382" class="sos-card sos-tourist"><div class="sos-card-icon">🏖️</div><div class="sos-card-title"><span class="en-content">Tourist Assistance</span><span class="kr-content">관광객 도움센터</span></div><div class="sos-card-number">1382</div></a>
            </div>
            <p class="sos-footer"><span class="en-content">Tap a card to call directly. Stay safe!</span><span class="kr-content">카드를 터치하면 바로 전화됩니다. 안전하세요!</span></p>
        </div>
    </div>

    <a href="archive.html" class="archive-fab" title="Past Editions">📰<span class="archive-fab-tooltip"><span class="en-content">Past Editions</span><span class="kr-content">지난 기사</span></span></a>

    <div id="academyOverlay" class="academy-overlay">
        <div class="academy-panel">
            <div class="academy-topbar">
                <div class="academy-topbar-left"><button class="academy-back-btn" onclick="closeAcademy()">&larr;</button><span class="academy-brand">ICAN Academy</span></div>
                <div class="academy-topbar-right"><div class="academy-level-selector"><span class="academy-level-label">Level</span><button class="academy-level-dot active" data-level="1" onclick="setAcademyLevel(1)">1</button><button class="academy-level-dot" data-level="2" onclick="setAcademyLevel(2)">2</button><button class="academy-level-dot" data-level="3" onclick="setAcademyLevel(3)">3</button><button class="academy-level-dot" data-level="4" onclick="setAcademyLevel(4)">4</button></div></div>
            </div>
            <div id="academyContent"></div>
        </div>
    </div>

    <script src="js/main.js?v={ver}"></script>
    <script src="js/academy-data.js?v={ver}"></script>
    <script src="js/academy.js?v={ver}"></script>
</body>
</html>'''
    # The cache panel reports on every image of the page, so it is filled after the
    # whole document (cover and featured photos included) has been rendered.
    html = html.replace("<!--CACHE_CHECK-->", build_cache_check_section())
    return html


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    wanted_date = ""
    for i, a in enumerate(sys.argv[1:]):
        if a == "--date" and i + 2 <= len(sys.argv) - 1:
            wanted_date = sys.argv[i + 2]
            break

    daily_files = sorted(glob.glob("data/daily-*.json"))
    if not daily_files:
        print("ERROR: No daily JSON found", file=sys.stderr)
        sys.exit(1)

    if wanted_date:
        daily_file = f"data/daily-{wanted_date}.json"
        if not Path(daily_file).exists():
            print(f"ERROR: {daily_file} not found", file=sys.stderr)
            sys.exit(1)
    else:
        daily_file = daily_files[-1]
    print(f"  Loading daily: {daily_file}")
    with open(daily_file, encoding="utf-8") as f:
        daily = json.load(f)

    edition_date = Path(daily_file).stem.replace("daily-", "")
    load_academy_layers(edition_date)
    manifest_file = Path(f"data/image-manifest-{edition_date}.json")
    if manifest_file.exists():
        try:
            with open(manifest_file, encoding="utf-8") as f:
                manifest = json.load(f)
            IMAGE_MANIFEST.update(manifest.get("items", {}) or {})
            ready = sum(1 for v in IMAGE_MANIFEST.values() if v.get("src") and Path(str(v["src"])).exists())
            print(f"  Article images: {ready}/{len(IMAGE_MANIFEST)} local ({manifest_file.name})")
        except Exception as exc:
            print(f"  WARNING: image manifest unreadable ({exc}) — using keyword photos", file=sys.stderr)
    else:
        print(f"  No image manifest for {edition_date} — using keyword photos")

    weekly = None
    weekly_files = sorted(glob.glob("data/weekly-*.json"))
    if weekly_files:
        print(f"  Loading weekly: {weekly_files[-1]}")
        with open(weekly_files[-1], encoding="utf-8") as f:
            weekly = json.load(f)

    html = build_html(daily, weekly)
    for filename in ["ican_news.html", "index.html"]:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)
    print(f"  Built ican_news.html and index.html ({len(html)} bytes)")


if __name__ == "__main__":
    main()
