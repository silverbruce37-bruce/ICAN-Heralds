#!/bin/bash
# ICAN Heralds — Daily Edition Generator
# Generates today's news edition using AI, then commits & pushes.
# Usage: ./scripts/generate-daily.sh
# Scheduled via crontab or GitHub Actions at 7 AM PHT.

set -euo pipefail
cd "$(dirname "$0")/.."

DATE=$(date +%Y-%m-%d)
DAY_OF_WEEK=$(date +%A | tr '[:lower:]' '[:upper:]')
DATE_DISPLAY=$(date +"%A, %B %-d, %Y" | tr '[:lower:]' '[:upper:]')
DATE_DOT=$(date +%Y.%m.%d)

echo "=== ICAN Heralds Daily Generator ==="
echo "Date: $DATE"

# Step 1: Generate news content via Claude
echo "[1/3] Generating news content..."

NEWS_JSON=$(claude --print --model sonnet --max-tokens 4000 <<'PROMPT'
You are a bilingual (English/Korean) news editor for ICAN Heralds, a daily news app for the Korean community in the Philippines.

Generate today's news edition as JSON with this exact structure:
{
  "headline_en": "Main headline in English (max 80 chars)",
  "headline_kr": "메인 헤드라인 한국어",
  "subtitle_en": "Subtitle in English (1 sentence)",
  "subtitle_kr": "부제목 한국어",
  "main_article_en": "Main article body in English (2-3 sentences)",
  "main_article_kr": "메인 기사 본문 한국어",
  "image_prompt": "A cinematic, editorial-style photograph prompt for the main story (1 sentence, professional newspaper quality)",
  "weather": "##°C Sunny/Cloudy/Rainy",
  "weather_kr": "##°C 맑음/흐림/비",
  "word_of_day": "English vocabulary word",
  "word_of_day_desc_en": "Definition in English",
  "word_of_day_desc_kr": "한국어 정의",
  "news": [
    {
      "tag": "Category",
      "title_en": "News title EN",
      "title_kr": "뉴스 제목 KR",
      "desc_en": "1 sentence EN",
      "desc_kr": "1문장 KR"
    }
  ]
}

Focus on: Korea-Philippines relations, Korean community safety, cultural events, ASEAN economy, K-pop/K-food in PH.
Include 6 news cards. Make it relevant and realistic for today's date.
Return ONLY valid JSON, no markdown.
PROMPT
)

if [ -z "$NEWS_JSON" ]; then
  echo "ERROR: Failed to generate news content"
  exit 1
fi

echo "$NEWS_JSON" > /tmp/ican-heralds-daily.json
echo "  News content saved."

# Step 2: Generate main article image via Nano Banana Pro
echo "[2/3] Generating main article image..."

IMAGE_PROMPT=$(echo "$NEWS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['image_prompt'])" 2>/dev/null || echo "")

if [ -n "$IMAGE_PROMPT" ] && command -v uv &> /dev/null; then
  NANO_SCRIPT="$HOME/.gemini/extensions/buildatscale-gemini-skills/skills/nano-banana-pro/scripts/image.py"
  if [ -f "$NANO_SCRIPT" ]; then
    uv run "$NANO_SCRIPT" --prompt "$IMAGE_PROMPT" --output images/main_article.png 2>/dev/null || echo "  Image generation skipped (Nano Banana Pro unavailable)"
  else
    echo "  Image generation skipped (script not found)"
  fi
else
  echo "  Image generation skipped"
fi

# Step 3: Update HTML with new content
echo "[3/3] Updating HTML..."

python3 <<PYEOF
import json, re, sys
from datetime import datetime

with open('/tmp/ican-heralds-daily.json') as f:
    data = json.load(f)

with open('ican_news.html', 'r') as f:
    html = f.read()

# Update date
html = re.sub(
    r'<div class="date">.*?</div>',
    f'<div class="date">${DAY_OF_WEEK}, ${DATE_DISPLAY} | PHILIPPINES | VOL. 01</div>',
    html
)

# Update dashboard date
html = re.sub(
    r'(<span class="dash-value">)\d{4}\.\d{2}\.\d{2}(</span>)',
    f'\\g<1>${DATE_DOT}\\2',
    html
)

# Update weather
weather_en = data.get('weather', '32°C Sunny')
weather_kr = data.get('weather_kr', '32°C 맑음')
html = re.sub(
    r'(<span class="dash-value">\s*<span class="en-content">)\d+°C\s+\w+(</span>\s*<span class="kr-content">)\d+°C\s+\S+(</span>)',
    f'\\g<1>{weather_en}\\2{weather_kr}\\3',
    html
)

# Update headline
html = re.sub(
    r'(<h2 class="main-title">\s*<span class="en-content">).*?(</span>\s*<span class="kr-content">).*?(</span>)',
    lambda m: f'{m.group(1)}{data["headline_en"]}{m.group(2)}{data["headline_kr"]}{m.group(3)}',
    html, flags=re.DOTALL
)

# Update subtitle
html = re.sub(
    r'(<h3 class="sub-title">\s*<span class="en-content">).*?(</span>\s*<span class="kr-content">).*?(</span>)',
    lambda m: f'{m.group(1)}{data["subtitle_en"]}{m.group(2)}{data["subtitle_kr"]}{m.group(3)}',
    html, flags=re.DOTALL
)

# Update main article
html = re.sub(
    r'(<div class="en-content">\s*)(.*?)(\s*</div>\s*<div class="kr-content">\s*)(.*?)(\s*</div>\s*</div>\s*</div>\s*</section>\s*<h2 id="news")',
    lambda m: f'{m.group(1)}{data["main_article_en"]}{m.group(3)}{data["main_article_kr"]}{m.group(5)}',
    html, flags=re.DOTALL
)

# Update word of the day
html = re.sub(
    r'(<h2 class="word-title">).*?(</h2>)',
    f'\\g<1>{data["word_of_day"]}\\2',
    html
)

html = re.sub(
    r'(<p class="word-desc">\s*<span class="en-content">).*?(</span>\s*<span class="kr-content">).*?(</span>)',
    lambda m: f'{m.group(1)}{data["word_of_day_desc_en"]}{m.group(2)}{data["word_of_day_desc_kr"]}{m.group(3)}',
    html, flags=re.DOTALL
)

# Update news cards
news_items = data.get('news', [])
tags = ['Security', 'Economy', 'Culture', 'Diplomacy', 'Cooperation', 'Safety']
for i, item in enumerate(news_items[:6]):
    tag = item.get('tag', tags[i] if i < len(tags) else 'News')
    # Build replacement for each news card by index
    pattern = rf'(<!-- News {i+1} -->.*?<span class="tag">).*?(</span>.*?<h3>\s*<span class="en-content">).*?(</span>\s*<span class="kr-content">).*?(</span>.*?<p>\s*<span class="en-content">).*?(</span>\s*<span class="kr-content">).*?(</span>\s*</p>\s*</div>)'
    replacement = f'\\g<1>{tag}\\2{item["title_en"]}\\3{item["title_kr"]}\\4{item["desc_en"]}\\5{item["desc_kr"]}\\6'
    html = re.sub(pattern, replacement, html, flags=re.DOTALL)

with open('ican_news.html', 'w') as f:
    f.write(html)

print('  HTML updated successfully.')
PYEOF

echo "=== Done! ==="
echo "Preview: open ican_news.html"
