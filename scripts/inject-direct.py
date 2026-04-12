#!/usr/bin/env python3
"""ICAN Heralds — Direct content injector.

Replaces baked-in content in ican_news.html using actual CSS class names.
Works regardless of SLOT markers (which get stripped after first run).

Usage: python3 scripts/inject-direct.py data/daily-YYYY-MM-DD.json
"""

import json
import re
import sys
import os
import glob

def img_url(seed, w=400, h=200):
    photo_map = {
        'cover': '1611974789855-9c2a0a7236a3',
        'feat': '1555448248-2571daf6344b',
        'news1': '1611974789855-9c2a0a7236a3',
        'news2': '1470071459604-3b5ec3a7fe05',
        'news3': '1493225457124-a3eb161ffa5f',
        'news4': '1555448248-2571daf6344b',
    }
    for prefix, photo_id in photo_map.items():
        if seed.startswith(prefix):
            return f"https://images.unsplash.com/photo-{photo_id}?w={w}&h={h}&fit=crop"
    import hashlib
    h_val = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16) % 1000
    return f"https://images.unsplash.com/photo-{1500000000000 + h_val * 1000000}-placeholder?w={w}&h={h}&fit=crop&q=80"


def inject(html, d):
    """Inject daily content into HTML using actual class names."""

    # === UTILITY BAR: Dateline ===
    days = {'Monday': 'Monday', 'Tuesday': 'Tuesday', 'Wednesday': 'Wednesday',
            'Thursday': 'Thursday', 'Friday': 'Friday', 'Saturday': 'Saturday', 'Sunday': 'Sunday'}
    html = re.sub(
        r'(<span class="nyt-dateline-compact">)[^<]*(</span>)',
        lambda m: m.group(1) + d['header_date_line'].split('|')[0].strip().title() + m.group(2),
        html, count=1
    )

    # === DASHBOARD ===
    dash = d['dashboard']
    html = re.sub(r'(dash-value">)\d+\.\d+(<)', f'\\g<1>{dash["php_krw_rate"]}\\2', html, count=1)
    # Weather — match any temperature pattern
    html = re.sub(r'(<span class="en-content">)\d+°C[^<]*(</span>\s*</span>\s*</div>\s*<div class="dash-item">\s*<span class="dash-label">\s*<span class="en-content">Today)',
        f'\\g<1>{dash["weather_en"]}\\2', html, count=1, flags=re.DOTALL)
    html = re.sub(r'(<span class="kr-content">)\d+°C[^<]*(</span>)',
        f'\\g<1>{dash["weather_kr"]}\\2', html, count=1)
    html = re.sub(r'(dash-value">)2026\.\d{2}\.\d{2}(<)', f'\\g<1>{dash["date"]}\\2', html, count=1)
    # Embassy
    html = re.sub(r'(<span class="en-content">)Normal[^<]*(</span>\s*<span class="kr-content">)',
        f'\\g<1>{dash["embassy_en"]}\\2', html, count=1, flags=re.DOTALL)
    html = re.sub(r'(<span class="kr-content">)정상 운영(</span>)',
        f'\\g<1>{dash["embassy_kr"]}\\2', html, count=1)

    # === COVER STORY ===
    cover = d['cover_story']
    # main-title
    html = re.sub(
        r'(<h2 class="main-title">)\s*<span class="en-content">.*?</span>\s*<span class="kr-content">.*?</span>',
        f'\\1\n                <span class="en-content">{cover["headline_en"]}</span>\n                <span class="kr-content">{cover["headline_kr"]}</span>',
        html, count=1, flags=re.DOTALL)
    # sub-title
    html = re.sub(
        r'(<h3 class="sub-title">)\s*<span class="en-content">.*?</span>\s*<span class="kr-content">.*?</span>',
        f'\\1\n                <span class="en-content">{cover["subtitle_en"]}</span>\n                <span class="kr-content">{cover["subtitle_kr"]}</span>',
        html, count=1, flags=re.DOTALL)
    # Cover image
    cover_img = img_url(cover['image_seed'], 1200, 700)
    html = re.sub(r'(<div class="main-image-container">\s*<img src=")[^"]*(")',
        f'\\g<1>{cover_img}\\2', html, count=1, flags=re.DOTALL)
    # Cover image caption
    html = re.sub(r'(<div class="image-caption">)[^<]*(</div>)',
        f'\\g<1>{cover["image_caption"]}\\2', html, count=1)
    # Cover read time
    html = re.sub(r'(<span class="meta-time">\s*<span class="en-content">)\d+ min read',
        f'\\g<1>{cover["read_time_min"]} min read', html, count=1, flags=re.DOTALL)
    html = re.sub(r'(<span class="kr-content">)\d+분 읽기',
        f'\\g<1>{cover["read_time_min"]}분 읽기', html, count=1)
    # Cover body — en-content column
    body_en = "\n".join(f"                        <p>{p}</p>" for p in cover["body_en"])
    body_kr = "\n".join(f"                        <p>{p}</p>" for p in cover["body_kr"])
    html = re.sub(
        r'(<div class="column">\s*<div class="en-content">).*?(</div>\s*<div class="kr-content">)',
        f'\\1\n{body_en}\n                    \\2',
        html, count=1, flags=re.DOTALL)
    html = re.sub(
        r'(<div class="kr-content">).*?(</div>\s*</div>\s*</div>\s*</section>)',
        f'\\1\n{body_kr}\n                    \\2',
        html, count=1, flags=re.DOTALL)

    # === FEATURED NEWS ===
    feat = d['featured_news']
    feat_img = img_url(feat['image_seed'], 800, 450)
    # Image
    html = re.sub(r'(<div class="featured-news-image">\s*<img src=")[^"]*(")',
        f'\\g<1>{feat_img}\\2', html, count=1, flags=re.DOTALL)
    # Tag
    html = re.sub(r'(<div class="featured-news-image">.*?<span class="tag )[^"]*(">[^<]*</span>)',
        f'\\g<1>{feat["tag_class"]}\\2', html, count=1, flags=re.DOTALL)
    html = re.sub(r'(<span class="tag tag-[^"]*">)[^<]*(</span>\s*</div>\s*<div class="featured-news-body">)',
        f'\\g<1>{feat["tag"]}\\2', html, count=1, flags=re.DOTALL)
    # Featured headline
    html = re.sub(
        r'(<div class="featured-news-body">\s*<h3>\s*)<span class="en-content">.*?</span>\s*<span class="kr-content">.*?</span>',
        f'\\g<1><span class="en-content">{feat["headline_en"]}</span>\n                        <span class="kr-content">{feat["headline_kr"]}</span>',
        html, count=1, flags=re.DOTALL)
    # Featured lead
    html = re.sub(
        r'(<p class="featured-news-lead">\s*)<span class="en-content">.*?</span>\s*<span class="kr-content">.*?</span>',
        f'\\g<1><span class="en-content">{feat["lead_en"]}</span>\n                        <span class="kr-content">{feat["lead_kr"]}</span>',
        html, count=1, flags=re.DOTALL)
    # Featured desk
    html = re.sub(r'(<span class="meta-author">)[^<]*(Desk</span>)',
        f'\\g<1>{feat["desk"]}\\2', html, count=1)
    # Featured read time
    html = re.sub(
        r'(featured-news-body.*?<span class="en-content">)\d+ min read',
        f'\\g<1>{feat["read_time_min"]} min read',
        html, count=1, flags=re.DOTALL)

    # === NEWS GRID (4 cards) — full rebuild ===
    card_starts = [m.start() for m in re.finditer(r'<div class="news-card">', html)]
    for idx in range(len(card_starts) - 1, -1, -1):
        if idx >= len(d['news_grid']):
            continue
        item = d['news_grid'][idx]
        start = card_starts[idx]
        if idx + 1 < len(card_starts):
            end = card_starts[idx + 1]
        else:
            end = html.find('</div>', start + 400)
            while html.count('<div', start, end) > html.count('</div>', start, end):
                end = html.find('</div>', end + 1)
            end += 6

        new_card = f'''<div class="news-card">
                    <div class="news-thumb"><img src="{img_url(item['image_seed'], 400, 200)}" alt="{item['tag']}"></div>
                    <div class="news-card-body">
                        <span class="tag {item['tag_class']}">{item['tag']}</span>
                        <h3>
                            <span class="en-content">{item['headline_en']}</span>
                            <span class="kr-content">{item['headline_kr']}</span>
                        </h3>
                        <p>
                            <span class="en-content">{item['summary_en']}</span>
                            <span class="kr-content">{item['summary_kr']}</span>
                        </p>
                        <span class="news-read-time">
                            <span class="en-content">{item['read_time_min']} min read</span>
                            <span class="kr-content">{item['read_time_min']}분 읽기</span>
                        </span>
                        <button class="learn-btn" onclick="openAcademy('news_{idx+1}')"><span class="learn-icon">📚</span> LEARN</button>
                    </div>
                </div>
'''
        html = html[:start] + new_card + html[end:]
        card_starts = [m.start() for m in re.finditer(r'<div class="news-card">', html)]

    # === WORD OF THE DAY ===
    word = d['word_of_day']
    html = re.sub(r'(<span class="word-title">)[^<]*(</span>)', f'\\1{word["word"]}\\2', html, count=1)
    html = re.sub(r'(<span class="word-phonetic">)[^<]*(</span>)',
        f'\\1/{word["pronunciation"]}/ — {word["type"]}\\2', html, count=1)
    html = re.sub(r'(<p class="word-desc en-content">)[^<]*(</p>)', f'\\1{word["definition_en"]}\\2', html, count=1)
    html = re.sub(r'(<p class="word-desc kr-content">)[^<]*(</p>)', f'\\1{word["definition_kr"]}\\2', html, count=1)
    html = re.sub(r'(<p class="word-example en-content">)<em>"[^"]*"</em>',
        f'\\1<em>"{word["example_en"]}"</em>', html, count=1)
    html = re.sub(r'(<p class="word-example kr-content">)<em>"[^"]*"</em>',
        f'\\1<em>"{word["example_kr"]}"</em>', html, count=1)
    html = re.sub(r'(<span class="word-grade">)[^<]*(</span>)', f'\\1{word["grade"]}\\2', html, count=1)

    return html


def generate_academy_js(daily_file, academy_file):
    """Generate js/academy-data.js from daily + academy JSON."""
    with open(daily_file) as f:
        daily = json.load(f)
    with open(academy_file) as f:
        academy = json.load(f)

    js_data = {}
    article_map = {
        'cover': ('cover_story', daily['cover_story']),
        'featured': ('featured_news', daily['featured_news']),
    }
    for i in range(1, 5):
        key = f'news_{i}'
        if i - 1 < len(daily.get('news_grid', [])):
            article_map[key] = ('news_grid', daily['news_grid'][i - 1])

    for key, (src_key, article) in article_map.items():
        if key not in academy:
            continue
        entry = academy[key]
        js_data[key] = {
            'tag': article.get('tag', 'News'),
            'tagClass': article.get('tag_class', 'tag-economy'),
            'title_en': article.get('headline_en', ''),
            'title_kr': article.get('headline_kr', ''),
            'summary_en': article.get('subtitle_en', article.get('summary_en', article.get('lead_en', ''))),
            'summary_kr': article.get('subtitle_kr', article.get('summary_kr', article.get('lead_kr', ''))),
            'layers': entry.get('layers', []),
        }

    js_content = f'// Auto-generated — {daily["edition_date"]}\n'
    js_content += 'const academyData = ' + json.dumps(js_data, ensure_ascii=False, indent=2) + ';\n'
    js_content += 'const paulSuggestions = {};\n'
    for key in js_data:
        if key in academy and 'suggestions_en' in academy[key]:
            js_content += (
                f'paulSuggestions["{key}"] = {{ '
                f'en: {json.dumps(academy[key]["suggestions_en"])}, '
                f'kr: {json.dumps(academy[key]["suggestions_kr"], ensure_ascii=False)} }};\n'
            )

    with open('js/academy-data.js', 'w') as f:
        f.write(js_content)
    print(f"  Generated js/academy-data.js ({len(js_data)} articles)")


def update_archive(daily_file):
    """Update data/archive-index.json."""
    INDEX_FILE = 'data/archive-index.json'
    index = []
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE) as f:
            index = json.load(f)

    with open(daily_file) as f:
        d = json.load(f)

    date = d['edition_date']
    existing = {e['date'] for e in index}
    if date not in existing:
        vol = int(open('data/volume.txt').read().strip()) if os.path.exists('data/volume.txt') else 1
        index.append({
            'date': date,
            'vol': vol,
            'cover_en': d['cover_story']['headline_en'],
            'cover_kr': d['cover_story']['headline_kr'],
            'headlines_en': [d['featured_news']['headline_en']] + [n['headline_en'] for n in d['news_grid'][:4]],
            'headlines_kr': [d['featured_news']['headline_kr']] + [n['headline_kr'] for n in d['news_grid'][:4]],
            'tags': list(set([d['featured_news']['tag']] + [n['tag'] for n in d['news_grid']])),
        })
    index.sort(key=lambda x: x['date'], reverse=True)
    with open(INDEX_FILE, 'w') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"  Archive: {len(index)} editions")


def main():
    if len(sys.argv) < 2:
        # Auto-detect latest daily JSON
        files = sorted(glob.glob('data/daily-*.json'))
        if not files:
            print("ERROR: No daily JSON found. Pass path as argument.")
            sys.exit(1)
        daily_file = files[-1]
    else:
        daily_file = sys.argv[1]

    print(f"=== ICAN Herald Direct Injector ===")
    print(f"  Source: {daily_file}")

    with open(daily_file) as f:
        d = json.load(f)

    # 1. Inject into HTML
    with open('ican_news.html', 'r') as f:
        html = f.read()
    html = inject(html, d)
    with open('ican_news.html', 'w') as f:
        f.write(html)
    print(f"  Injected into ican_news.html")

    # 2. Copy to index.html
    with open('index.html', 'w') as f:
        f.write(html)
    print(f"  Copied to index.html")

    # 3. Update sw.js cache
    date = d['edition_date']
    if os.path.exists('sw.js'):
        with open('sw.js', 'r') as f:
            sw = f.read()
        sw = re.sub(r"const CACHE_NAME = .*", f"const CACHE_NAME = 'ican-heralds-{date}';", sw)
        with open('sw.js', 'w') as f:
            f.write(sw)
        print(f"  Updated sw.js cache: ican-heralds-{date}")

    # 4. Academy JS (if academy JSON exists)
    academy_file = f'data/academy-{date}.json'
    if os.path.exists(academy_file):
        generate_academy_js(daily_file, academy_file)

    # 5. Archive
    update_archive(daily_file)

    print(f"\n=== Done: {d['header_date_line']} ===")


if __name__ == '__main__':
    main()
