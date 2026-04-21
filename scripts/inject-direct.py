#!/usr/bin/env python3
"""ICAN Heralds — Direct HTML builder (no SLOT markers needed).

Builds full ican_news.html from JSON data + HTML template structure.
"""

import json
import sys
import os
import glob
from datetime import datetime


def img_url(prompt, w=400, h=200, seed=None):
    """Content-matched image via Pollinations.ai (free text-to-image).

    Pass the article's headline/title as `prompt` — the image reflects it.
    `seed` keeps the same prompt stable across regenerations.
    """
    import urllib.parse
    import hashlib

    if not prompt or not str(prompt).strip():
        prompt = "Philippine city scenery professional"

    clean = str(prompt).strip()
    # Shorter style to prevent truncation of important keywords
    styled = f"Professional photo, high-end design: {clean}"
    encoded = urllib.parse.quote(styled[:200])

    seed_source = (str(seed) if seed is not None else clean) + "v3"
    seed_num = int(hashlib.md5(seed_source.encode()).hexdigest()[:8], 16) % 100000

    # Use model=turbo for fast, parallel loading (flux has strict IP limits)
    return (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={w}&height={h}&seed={seed_num}&model=turbo&nologo=true"
    )


def build_news_cards(news):
    cards = ""
    for i, item in enumerate(news[:4], 1):
        cards += f'''
                <div class="news-card">
                    <div class="news-thumb"><img src="{img_url(item.get('image_query') or item.get('headline_en', f'news {i}'), 280, 220, seed=item.get('image_seed'))}" alt="{item.get('tag', 'News')}" loading="lazy"></div>
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
        gallery_imgs = "\n".join(
            f'<img src="{img_url(gallery_aspects[i], 400, 300, seed=gallery_seeds[i] if i < len(gallery_seeds) else None)}" alt="Gallery {i+1}" loading="lazy">'
            for i in range(3)
        )

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
                    <img class="food-hero-img" src="{img_url(food.get('image_query') or f"{food.get('name_en','restaurant')} {cuisine} signature dish", 1600, 900, seed=food.get('hero_image_seed'))}" alt="{food.get('name_en','')}" loading="lazy">
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
                        <img src="{img_url(ev.get('image_query') or ev.get('title', f'event {i}'), 600, 400, seed=ev.get('image_seed'))}" alt="{ev.get('title','')}" loading="lazy">
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
                <span class="en-content">Herald\\'s Pick</span>
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
                    <img src="{img_url(tc.get('image_query') or f"{tc.get('name_en','destination')} philippines travel scenic", 800, 500, seed=tc.get('image_seed'))}" alt="{tc.get('name_en','')}" loading="lazy">
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


def build_html(daily, weekly):
    d = daily
    dash = d.get("dashboard", {})
    cover = d.get("cover_story", {})
    feat = d.get("featured_news", {})
    news = d.get("news_grid", [])
    word = d.get("word_of_day", {})
    date_str = d.get("edition_date", datetime.now().strftime("%Y-%m-%d"))
    date_dot = date_str.replace("-", ".")
    # Append suffix to bust CSS/JS cache for the new font update
    ver = date_str.replace("-", "") + "_v2"

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

    word_html = ""
    if word:
        word_html = f'''
        <section class="word-banner">
            <div class="word-inner">
                <div class="word-badge"><span class="en-content">WORD OF THE DAY</span><span class="kr-content">오늘의 단어</span></div>
                <h2 class="word-title">{word.get('word', '')}</h2>
                <div class="word-pronunciation">/{word.get('pronunciation', '')}/ — {word.get('type', 'noun')}</div>
                <p class="word-desc"><span class="en-content">{word.get('definition_en', '')}</span><span class="kr-content">{word.get('definition_kr', '')}</span></p>
                <p class="word-example"><span class="en-content"><em>"{word.get('example_en', '')}"</em></span><span class="kr-content"><em>"{word.get('example_kr', '')}"</em></span></p>
                <div class="word-grade">{word.get('grade', 'A+')}</div>
            </div>
        </section>'''

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ICAN HERALDS - Daily Edition</title>
    <link rel="manifest" href="manifest.json">
    <meta name="theme-color" content="#0a0a0a">
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
                <li><a href="#academy"><span class="en-content">Academy</span><span class="kr-content">아카데미</span></a></li>
                <li><a href="archive.html"><span class="en-content">Archive</span><span class="kr-content">지난 기사</span></a></li>
            </ul>
        </div>
    </nav>

    <div class="container">
        <section class="dashboard">
            <div class="dash-item">
                <span class="dash-label"><span class="en-content">PHP / KRW</span><span class="kr-content">페소 / 원</span></span>
                <span class="dash-value" id="dashRate">{dash.get('php_krw_rate', '24.62')}</span>
                <span class="dash-source"><span class="en-content">via Naver Finance</span><span class="kr-content">네이버 금융</span></span>
            </div>
            <div class="dash-item">
                <span class="dash-label"><span class="en-content">Manila Weather</span><span class="kr-content">마닐라 날씨</span></span>
                <span class="dash-value">
                    <span class="en-content">{dash.get('weather_en', '32°C Sunny')}</span>
                    <span class="kr-content">{dash.get('weather_kr', '32°C 맑음')}</span>
                </span>
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

        <section class="headline-section">
            <div class="headline-badge"><span class="en-content">COVER STORY</span><span class="kr-content">커버 스토리</span></div>
            <h2 class="main-title"><span class="en-content">{cover.get('headline_en', '')}</span><span class="kr-content">{cover.get('headline_kr', '')}</span></h2>
            <h3 class="sub-title"><span class="en-content">{cover.get('subtitle_en', '')}</span><span class="kr-content">{cover.get('subtitle_kr', '')}</span></h3>
            <div class="main-image-container">
                <img src="{img_url(cover.get('image_query') or cover.get('headline_en', 'cover story'), 1200, 800, seed=cover.get('image_seed'))}" alt="Cover Story" loading="lazy">
                <div class="image-caption">{cover.get('image_caption', '')}</div>
            </div>
            <div class="article-meta">
                <span class="meta-author">{cover.get('author', 'By ICAN Herald Editorial')}</span>
                <span class="meta-divider">·</span>
                <span class="meta-time"><span class="en-content">{cover.get('read_time_min', 5)} min read</span><span class="kr-content">{cover.get('read_time_min', 5)}분 읽기</span></span>
                <button class="learn-btn" onclick="openAcademy('cover')" style="margin-left:12px;margin-top:0;"><span class="learn-icon">📚</span> LEARN</button>
            </div>
            <div class="content-columns"><div class="column"><div class="en-content">{body_en}</div><div class="kr-content">{body_kr}</div></div></div>
        </section>

        <section id="news">
            <h2 class="section-title"><span class="en-content">Latest Korea-Philippines News</span><span class="kr-content">최신 한-필 주요 뉴스</span><span class="live-badge">LIVE</span></h2>
            <div class="featured-news">
                <div class="featured-news-image">
                    <img src="{img_url(feat.get('image_query') or feat.get('headline_en', 'featured news'), 900, 600, seed=feat.get('image_seed'))}" alt="{feat.get('tag', 'News')}" loading="lazy">
                    <span class="tag {feat.get('tag_class', 'tag-security')}">{feat.get('tag', 'News')}</span>
                </div>
                <div class="featured-news-body">
                    <h3><span class="en-content">{feat.get('headline_en', '')}</span><span class="kr-content">{feat.get('headline_kr', '')}</span></h3>
                    <p class="featured-news-lead"><span class="en-content">{feat.get('lead_en', '')}</span><span class="kr-content">{feat.get('lead_kr', '')}</span></p>
                    <div class="article-meta">
                        <span class="meta-author">{feat.get('desk', 'News Desk')}</span>
                        <span class="meta-divider">·</span>
                        <span class="meta-time"><span class="en-content">{feat.get('read_time_min', 3)} min read</span><span class="kr-content">{feat.get('read_time_min', 3)}분 읽기</span></span>
                        <span class="meta-divider">·</span>
                        <span class="meta-date">{date_dot}</span>
                        <button class="learn-btn" onclick="openAcademy('featured')" style="margin-left:8px;margin-top:0;"><span class="learn-icon">📚</span> LEARN</button>
                    </div>
                </div>
            </div>
            <div class="news-grid">{news_cards}
            </div>
        </section>

        {word_html}
        {food_html}
        {events_html}
        {picks_html}

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
                <div class="academy-topbar-right"><div class="academy-level-selector"><span class="academy-level-label">Level</span><button class="academy-level-dot active" data-level="1" onclick="setAcademyLevel(1)">1</button><button class="academy-level-dot" data-level="2" onclick="setAcademyLevel(2)">2</button><button class="academy-level-dot" data-level="3" onclick="setAcademyLevel(3)">3</button></div></div>
            </div>
            <div id="academyContent"></div>
        </div>
    </div>

    <script src="js/main.js?v={ver}"></script>
    <script src="js/academy-data.js?v={ver}"></script>
    <script src="js/academy.js?v={ver}"></script>
</body>
</html>'''


def main():
    daily_files = sorted(glob.glob("data/daily-*.json"))
    if not daily_files:
        print("ERROR: No daily JSON found", file=sys.stderr)
        sys.exit(1)

    daily_file = daily_files[-1]
    print(f"  Loading daily: {daily_file}")
    with open(daily_file, encoding="utf-8") as f:
        daily = json.load(f)

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
