#!/usr/bin/env python3
"""ICAN Heralds — Slot-based content injector.

Reads daily/weekly JSON data and injects content into ican_news.html
using <!--SLOT:name-->...<!--/SLOT:name--> markers.
"""

import json
import sys
import os
import glob
from datetime import datetime

HTML_FILE = "ican_news.html"


def inject(html, slot_name, value):
    """Replace content between SLOT markers. Returns modified HTML."""
    open_tag = f"<!--SLOT:{slot_name}-->"
    close_tag = f"<!--/SLOT:{slot_name}-->"
    try:
        start = html.index(open_tag) + len(open_tag)
        end = html.index(close_tag)
        return html[:start] + str(value) + html[end:]
    except ValueError:
        print(f"  WARNING: Slot '{slot_name}' not found in HTML", file=sys.stderr)
        return html


def img_url(seed, w=400, h=200):
    """Generate deterministic picsum.photos URL from seed."""
    return f"https://picsum.photos/seed/{seed}/{w}/{h}"


def load_latest_weekly():
    """Load the most recent weekly JSON file."""
    files = sorted(glob.glob("data/weekly-*.json"))
    if not files:
        return None
    with open(files[-1]) as f:
        return json.load(f)


def inject_daily(html, data):
    """Inject daily content: header, dashboard, cover, news, word."""
    d = data

    # Header
    html = inject(html, "header_date_line", d.get("header_date_line", ""))

    # Dashboard
    dash = d.get("dashboard", {})
    html = inject(html, "dash_rate", dash.get("php_krw_rate", "24.15"))
    html = inject(html, "dash_weather_en", dash.get("weather_en", "32°C Sunny"))
    html = inject(html, "dash_weather_kr", dash.get("weather_kr", "32°C 맑음"))
    html = inject(html, "dash_date", dash.get("date", datetime.now().strftime("%Y.%m.%d")))
    html = inject(html, "dash_embassy_en", dash.get("embassy_en", "Normal"))
    html = inject(html, "dash_embassy_kr", dash.get("embassy_kr", "정상 운영"))

    # Cover Story
    cover = d.get("cover_story", {})
    html = inject(html, "cover_headline_en", cover.get("headline_en", ""))
    html = inject(html, "cover_headline_kr", cover.get("headline_kr", ""))
    html = inject(html, "cover_subtitle_en", cover.get("subtitle_en", ""))
    html = inject(html, "cover_subtitle_kr", cover.get("subtitle_kr", ""))

    body_en = "\n".join(f"<p>{p}</p>" if not p.startswith("<p>") else p
                        for p in cover.get("body_en", []))
    body_kr = "\n".join(f"<p>{p}</p>" if not p.startswith("<p>") else p
                        for p in cover.get("body_kr", []))
    html = inject(html, "cover_body_en", body_en)
    html = inject(html, "cover_body_kr", body_kr)

    seed = cover.get("image_seed", "cover-default")
    html = inject(html, "cover_image_url", img_url(seed, 1200, 700))
    html = inject(html, "cover_image_caption", cover.get("image_caption", ""))
    html = inject(html, "cover_read_time_en", f'{cover.get("read_time_min", 5)} min read')
    html = inject(html, "cover_read_time_kr", f'{cover.get("read_time_min", 5)}분 읽기')

    # Featured News
    feat = d.get("featured_news", {})
    html = inject(html, "featured_image_url", img_url(feat.get("image_seed", "feat-default"), 800, 450))
    html = inject(html, "featured_tag_class", feat.get("tag_class", "tag-security"))
    html = inject(html, "featured_tag", feat.get("tag", "News"))
    html = inject(html, "featured_headline_en", feat.get("headline_en", ""))
    html = inject(html, "featured_headline_kr", feat.get("headline_kr", ""))
    html = inject(html, "featured_lead_en", feat.get("lead_en", ""))
    html = inject(html, "featured_lead_kr", feat.get("lead_kr", ""))
    html = inject(html, "featured_desk", feat.get("desk", "News Desk"))
    html = inject(html, "featured_read_time_en", f'{feat.get("read_time_min", 3)} min read')
    html = inject(html, "featured_read_time_kr", f'{feat.get("read_time_min", 3)}분 읽기')
    html = inject(html, "featured_date", d.get("edition_date", "").replace("-", "."))

    # News Grid (4 cards)
    for i, item in enumerate(d.get("news_grid", [])[:4], start=1):
        html = inject(html, f"news_{i}_image_url", img_url(item.get("image_seed", f"news{i}"), 400, 200))
        html = inject(html, f"news_{i}_tag_class", item.get("tag_class", "tag-economy"))
        html = inject(html, f"news_{i}_tag", item.get("tag", "News"))
        html = inject(html, f"news_{i}_headline_en", item.get("headline_en", ""))
        html = inject(html, f"news_{i}_headline_kr", item.get("headline_kr", ""))
        html = inject(html, f"news_{i}_summary_en", item.get("summary_en", ""))
        html = inject(html, f"news_{i}_summary_kr", item.get("summary_kr", ""))
        html = inject(html, f"news_{i}_read_time_en", f'{item.get("read_time_min", 2)} min read')
        html = inject(html, f"news_{i}_read_time_kr", f'{item.get("read_time_min", 2)}분 읽기')

    # Word of the Day
    word = d.get("word_of_day", {})
    html = inject(html, "word_title", word.get("word", ""))
    html = inject(html, "word_pronunciation", f'/{word.get("pronunciation", "")}/ — {word.get("type", "noun")}')
    html = inject(html, "word_desc_en", word.get("definition_en", ""))
    html = inject(html, "word_desc_kr", word.get("definition_kr", ""))
    html = inject(html, "word_example_en", f'<em>"{word.get("example_en", "")}"</em>')
    html = inject(html, "word_example_kr", f'<em>"{word.get("example_kr", "")}"</em>')
    html = inject(html, "word_grade", word.get("grade", "A+"))

    return html


def inject_weekly(html, data):
    """Inject weekly content: food, travel, events, picks."""
    if not data:
        print("  No weekly data, skipping weekly slots.")
        return html

    # Food Feature
    food = data.get("food_feature", {})
    if food:
        html = inject(html, "food_badge_en", food.get("badge_en", "EDITOR'S CHOICE"))
        html = inject(html, "food_badge_kr", food.get("badge_kr", "에디터 추천"))
        html = inject(html, "food_hero_url", img_url(food.get("hero_image_seed", "food-hero"), 800, 500))
        gallery = food.get("gallery_seeds", ["food-g1", "food-g2", "food-g3"])
        for j, seed in enumerate(gallery[:3], start=1):
            html = inject(html, f"food_gallery_{j}_url", img_url(seed, 200, 200))
        html = inject(html, "food_name_en", food.get("name_en", ""))
        html = inject(html, "food_name_kr", food.get("name_kr", ""))
        html = inject(html, "food_stars", food.get("stars", "★★★★★"))
        html = inject(html, "food_score", str(food.get("rating", 4.8)))
        html = inject(html, "food_lead_en", food.get("lead_en", ""))
        html = inject(html, "food_lead_kr", food.get("lead_kr", ""))
        html = inject(html, "food_quote_en", food.get("quote_en", ""))
        html = inject(html, "food_quote_kr", food.get("quote_kr", ""))
        html = inject(html, "food_location", food.get("location", ""))
        html = inject(html, "food_price", food.get("price_range", ""))
        html = inject(html, "food_hours", food.get("hours", ""))
        html = inject(html, "food_hours_note_en", food.get("hours_closed_en", ""))
        html = inject(html, "food_hours_note_kr", food.get("hours_closed_kr", ""))
        html = inject(html, "food_lang_en", food.get("language_en", ""))
        html = inject(html, "food_lang_kr", food.get("language_kr", ""))
        # Must-try items
        must_try = food.get("must_try", [])
        must_try_html = ""
        for item in must_try:
            must_try_html += f'''<li>
                                <span class="en-content">{item["en"]} — {item.get("price","")}</span>
                                <span class="kr-content">{item["kr"]} — {item.get("price","")}</span>
                            </li>\n'''
        html = inject(html, "food_must_try_items", must_try_html)
        html = inject(html, "food_tip_en", food.get("tip_en", ""))
        html = inject(html, "food_tip_kr", food.get("tip_kr", ""))
        # Tags
        tags_html = ""
        for tag in food.get("cuisine_tags", []):
            tags_html += f'''<span class="food-type-tag">
                            <span class="en-content">{tag["en"]}</span>
                            <span class="kr-content">{tag["kr"]}</span>
                        </span>\n'''
        html = inject(html, "food_tags", tags_html)

    # Travel Cards
    for i, tc in enumerate(data.get("travel_cards", [])[:2], start=1):
        html = inject(html, f"travel_{i}_image_url", img_url(tc.get("image_seed", f"travel{i}"), 600, 400))
        html = inject(html, f"travel_{i}_badge_en", tc.get("badge_en", ""))
        html = inject(html, f"travel_{i}_badge_kr", tc.get("badge_kr", ""))
        html = inject(html, f"travel_{i}_name_en", tc.get("name_en", ""))
        html = inject(html, f"travel_{i}_name_kr", tc.get("name_kr", ""))
        html = inject(html, f"travel_{i}_stars", tc.get("stars", "★★★★☆"))
        html = inject(html, f"travel_{i}_score", str(tc.get("rating", 4.5)))
        html = inject(html, f"travel_{i}_lead_en", tc.get("lead_en", ""))
        html = inject(html, f"travel_{i}_lead_kr", tc.get("lead_kr", ""))
        html = inject(html, f"travel_{i}_location", tc.get("location", ""))
        html = inject(html, f"travel_{i}_cost", tc.get("cost", ""))
        html = inject(html, f"travel_{i}_tip_en", tc.get("tip_en", ""))
        html = inject(html, f"travel_{i}_tip_kr", tc.get("tip_kr", ""))
        tags_html = ""
        for tag in tc.get("tags", []):
            tags_html += f'''<span class="food-type-tag">
                            <span class="en-content">{tag["en"]}</span>
                            <span class="kr-content">{tag["kr"]}</span>
                        </span>\n'''
        html = inject(html, f"travel_{i}_tags", tags_html)

    # Events
    for i, ev in enumerate(data.get("events", [])[:4], start=1):
        html = inject(html, f"event_{i}_date_badge", ev.get("date_badge", ""))
        html = inject(html, f"event_{i}_image_url", img_url(ev.get("image_seed", f"event{i}"), 600, 400))
        html = inject(html, f"event_{i}_title", ev.get("title", ""))
        html = inject(html, f"event_{i}_desc_en", ev.get("desc_en", ""))
        html = inject(html, f"event_{i}_desc_kr", ev.get("desc_kr", ""))
        html = inject(html, f"event_{i}_location_en", ev.get("location_en", ""))
        html = inject(html, f"event_{i}_location_kr", ev.get("location_kr", ""))
        html = inject(html, f"event_{i}_price_en", ev.get("price_en", ""))
        html = inject(html, f"event_{i}_price_kr", ev.get("price_kr", ""))

    # Herald's Pick
    picks = data.get("picks", {})
    if picks:
        html = inject(html, "picks_date", picks.get("date", ""))
        html = inject(html, "picks_title_en", picks.get("title_en", ""))
        html = inject(html, "picks_title_kr", picks.get("title_kr", ""))
        body_en = "\n".join(f"<p><span class=\"en-content\">{p}</span><span class=\"kr-content\">{kr}</span></p>"
                            for p, kr in zip(picks.get("body_en", []), picks.get("body_kr", [])))
        html = inject(html, "picks_body", body_en)
        html = inject(html, "picks_connect_en", picks.get("connect_label_en", ""))
        html = inject(html, "picks_connect_kr", picks.get("connect_label_kr", ""))

    return html


def main():
    # Load HTML template
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Load daily JSON
    daily_files = sorted(glob.glob("data/daily-*.json"))
    if not daily_files:
        print("ERROR: No daily JSON found in data/", file=sys.stderr)
        sys.exit(1)

    daily_file = daily_files[-1]
    print(f"  Loading daily: {daily_file}")
    with open(daily_file, encoding="utf-8") as f:
        daily_data = json.load(f)

    # Load weekly JSON
    weekly_data = load_latest_weekly()
    if weekly_data:
        print(f"  Loading weekly: {sorted(glob.glob('data/weekly-*.json'))[-1]}")

    # Inject
    html = inject_daily(html, daily_data)
    html = inject_weekly(html, weekly_data)

    # Write
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Injected content into {HTML_FILE}")


if __name__ == "__main__":
    main()
