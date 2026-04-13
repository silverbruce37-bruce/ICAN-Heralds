#!/bin/bash
# ICAN Heralds — Daily Edition Generator (v2)
# Generates daily news via Claude API, injects into HTML template.
# Usage: ./scripts/generate-daily.sh
# Scheduled via GitHub Actions at 8 AM PHT (00:00 UTC).

set -euo pipefail
cd "$(dirname "$0")/.."

# ─── Date & Volume ──────────────────────────────────
DATE=$(TZ="Asia/Manila" date +%Y-%m-%d)
DAY_OF_WEEK=$(TZ="Asia/Manila" date +%A | tr '[:lower:]' '[:upper:]')
DATE_DISPLAY=$(TZ="Asia/Manila" date +"%B %-d, %Y" | tr '[:lower:]' '[:upper:]')
DATE_DOT=$(TZ="Asia/Manila" date +%Y.%m.%d)
CURRENT_WEEK=$(TZ="Asia/Manila" date +%Y-W%V)

VOLUME_FILE="data/volume.txt"
mkdir -p data

if [ -f "$VOLUME_FILE" ]; then
    VOLUME=$(cat "$VOLUME_FILE")
else
    VOLUME=2
fi
VOLUME=$((VOLUME + 1))
echo "$VOLUME" > "$VOLUME_FILE"
VOLUME_DISPLAY=$(printf "VOL. %02d" "$VOLUME")

HEADER_LINE="${DAY_OF_WEEK}, ${DATE_DISPLAY} | PHILIPPINES | ${VOLUME_DISPLAY}"

echo "=== ICAN Heralds Daily Generator v2 ==="
echo "Date: $DATE | $VOLUME_DISPLAY | Week: $CURRENT_WEEK"

# ─── Fetch PHP/KRW Exchange Rate from Naver ─────────
echo "[0/5] Fetching PHP/KRW rate from Naver Finance..."
PHP_KRW_RATE=$(curl -sL "https://finance.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_PHPKRW" \
    -H "User-Agent: Mozilla/5.0" 2>/dev/null | python3 -c "
import sys, re
data = sys.stdin.buffer.read()
try:
    html = data.decode('euc-kr', errors='replace')
except:
    html = data.decode('utf-8', errors='replace')
idx = html.find('no_today')
if idx > 0:
    snippet = html[idx:idx+500]
    digits = re.findall(r'class=\"no\d\">(\d)</span>|class=\"jum\">(\.)</span>', snippet)
    rate = ''.join(d[0] or d[1] for d in digits)
    if rate:
        print(rate)
    else:
        print('24.00')
else:
    print('24.00')
" 2>/dev/null)

echo "  Naver rate: 1 PHP = ${PHP_KRW_RATE} KRW"

# ─── Claude CLI call with retry ─────────────────────
call_claude() {
    local prompt="$1"
    local result=""
    local max_retries=3

    local prompt_file
    prompt_file=$(mktemp)
    echo "$prompt" > "$prompt_file"

    for attempt in $(seq 1 $max_retries); do
        result=$(/Users/worker64/.local/bin/claude \
            --model haiku \
            -p \
            --dangerously-skip-permissions \
            "$(cat "$prompt_file")" 2>/dev/null)

        # Strip markdown fences if present
        result=$(echo "$result" | python3 -c "
import sys
text = sys.stdin.read().strip()
if text.startswith('\`\`\`json'):
    text = text[7:]
if text.startswith('\`\`\`'):
    text = text[3:]
if text.endswith('\`\`\`'):
    text = text[:-3]
print(text.strip())
")

        if [ -n "$result" ]; then
            break
        else
            echo "  Attempt $attempt: Claude CLI returned empty" >&2
        fi

        sleep 10
    done

    rm -f "$prompt_file"

    if [ -z "$result" ]; then
        echo "ERROR: Claude CLI failed after $max_retries attempts" >&2
        return 1
    fi

    echo "$result"
}

validate_daily_json() {
    echo "$1" | python3 -c "
import sys, json
data = json.load(sys.stdin)
required = ['dashboard', 'cover_story', 'featured_news', 'news_grid', 'word_of_day']
for key in required:
    assert key in data, f'Missing key: {key}'
assert len(data['news_grid']) >= 4, 'Need at least 4 news cards'
print('VALID')
"
}

# ─── Step 1: Generate Daily Content ─────────────────
echo "[1/4] Generating daily content..."

DAILY_PROMPT="You are a bilingual (English/Korean) news editor for ICAN Heralds, a premium daily news app for the Korean community in the Philippines.

Today is ${DAY_OF_WEEK}, ${DATE_DISPLAY}. Generate today's news edition.

Return ONLY valid JSON (no markdown fences) with this exact structure:

{
  \"edition_date\": \"${DATE}\",
  \"header_date_line\": \"${HEADER_LINE}\",
  \"dashboard\": {
    \"php_krw_rate\": \"${PHP_KRW_RATE}\",
    \"weather_en\": \"32°C Sunny\",
    \"weather_kr\": \"32°C 맑음\",
    \"date\": \"${DATE_DOT}\",
    \"embassy_en\": \"Normal\",
    \"embassy_kr\": \"정상 운영\"
  },
  \"cover_story\": {
    \"headline_en\": \"Main headline in English (max 80 chars)\",
    \"headline_kr\": \"메인 헤드라인 한국어\",
    \"subtitle_en\": \"Subtitle in English (1-2 sentences)\",
    \"subtitle_kr\": \"부제목 한국어\",
    \"body_en\": [\"Paragraph 1\", \"Paragraph 2\", \"Paragraph 3\"],
    \"body_kr\": [\"단락 1\", \"단락 2\", \"단락 3\"],
    \"image_seed\": \"cover-${DATE}\",
    \"image_caption\": \"Photo: Description of the image (date)\",
    \"author\": \"By ICAN Herald Editorial\",
    \"read_time_min\": 5
  },
  \"featured_news\": {
    \"tag\": \"Security\",
    \"tag_class\": \"tag-security\",
    \"headline_en\": \"Featured headline EN\",
    \"headline_kr\": \"피처드 헤드라인 KR\",
    \"lead_en\": \"2-3 sentence lead paragraph EN\",
    \"lead_kr\": \"리드 단락 KR\",
    \"image_seed\": \"feat-${DATE}\",
    \"desk\": \"Security Desk\",
    \"read_time_min\": 3
  },
  \"news_grid\": [
    {
      \"tag\": \"Economy\", \"tag_class\": \"tag-economy\",
      \"headline_en\": \"...\", \"headline_kr\": \"...\",
      \"summary_en\": \"1-2 sentence summary\", \"summary_kr\": \"...\",
      \"image_seed\": \"news1-${DATE}\", \"read_time_min\": 2
    },
    {
      \"tag\": \"Culture\", \"tag_class\": \"tag-culture\",
      \"headline_en\": \"...\", \"headline_kr\": \"...\",
      \"summary_en\": \"...\", \"summary_kr\": \"...\",
      \"image_seed\": \"news2-${DATE}\", \"read_time_min\": 2
    },
    {
      \"tag\": \"Cooperation\", \"tag_class\": \"tag-diplomacy\",
      \"headline_en\": \"...\", \"headline_kr\": \"...\",
      \"summary_en\": \"...\", \"summary_kr\": \"...\",
      \"image_seed\": \"news3-${DATE}\", \"read_time_min\": 3
    },
    {
      \"tag\": \"Safety\", \"tag_class\": \"tag-safety\",
      \"headline_en\": \"...\", \"headline_kr\": \"...\",
      \"summary_en\": \"...\", \"summary_kr\": \"...\",
      \"image_seed\": \"news4-${DATE}\", \"read_time_min\": 2
    }
  ],
  \"word_of_day\": {
    \"word\": \"English Word\",
    \"pronunciation\": \"phonetic\",
    \"type\": \"noun/verb/adj\",
    \"definition_en\": \"Clear definition in English\",
    \"definition_kr\": \"한국어 정의\",
    \"example_en\": \"Example sentence using the word.\",
    \"example_kr\": \"단어를 사용한 예문.\",
    \"grade\": \"A+\"
  }
}

IMPORTANT RULES:
- tag_class must be one of: tag-security, tag-economy, tag-culture, tag-diplomacy, tag-safety
- Focus on: Korea-Philippines relations, Korean community safety, ASEAN economy, K-culture, K-food events
- Make it realistic and relevant to today's date
- Cover story should have 3 substantial paragraphs per language
- The word_of_day should connect thematically to the cover story
- Return ONLY valid JSON, no explanation"

DAILY_JSON=$(call_claude "$DAILY_PROMPT" 6000) || {
    echo "ERROR: Failed to generate daily content"
    exit 1
}

# Validate
if ! validate_daily_json "$DAILY_JSON"; then
    echo "ERROR: Invalid daily JSON structure"
    exit 1
fi

echo "$DAILY_JSON" > "data/daily-${DATE}.json"
echo "  Daily content saved to data/daily-${DATE}.json"

# ─── Step 2: Weekly Content (if needed) ─────────────
WEEKLY_FILE="data/weekly-${CURRENT_WEEK}.json"

# Force weekly refresh on Mondays
DAY_OF_WEEK_NUM=$(TZ="Asia/Manila" date +%u)
if [ "$DAY_OF_WEEK_NUM" = "1" ] && [ -f "data/.weekly-refresh-${CURRENT_WEEK}" ]; then
    rm -f "$WEEKLY_FILE"
    echo "  Monday refresh: cleared weekly cache for regeneration"
fi

if [ ! -f "$WEEKLY_FILE" ]; then
    echo "[2/5] Generating weekly content (new week: $CURRENT_WEEK)..."

    WEEKLY_PROMPT="You are a bilingual food/travel/culture editor for ICAN Heralds.
Generate weekly editorial content as JSON. Return ONLY valid JSON (no markdown fences):

{
  \"week\": \"${CURRENT_WEEK}\",
  \"food_feature\": {
    \"badge_en\": \"EDITOR'S CHOICE\", \"badge_kr\": \"에디터 추천\",
    \"name_en\": \"Restaurant Name\", \"name_kr\": \"레스토랑 이름\",
    \"cuisine_tags\": [{\"en\": \"Cuisine Type\", \"kr\": \"요리 종류\"}, {\"en\": \"Style\", \"kr\": \"스타일\"}],
    \"rating\": 4.8, \"stars\": \"★★★★★\",
    \"lead_en\": \"3-4 sentence atmospheric review that makes you want to go\",
    \"lead_kr\": \"가고 싶게 만드는 3-4문장 리뷰\",
    \"quote_en\": \"A memorable quote from the owner or chef\",
    \"quote_kr\": \"주인 또는 셰프의 인상적인 말\",
    \"location\": \"Full address\",
    \"price_range\": \"₱XXX–XXX\",
    \"hours\": \"Opening hours\",
    \"hours_closed_en\": \"Closed Mondays\", \"hours_closed_kr\": \"월요일 휴무\",
    \"language_en\": \"Languages spoken\", \"language_kr\": \"사용 가능 언어\",
    \"must_try\": [
      {\"en\": \"Dish name EN\", \"kr\": \"메뉴명 KR\", \"price\": \"₱XXX\"},
      {\"en\": \"Dish 2\", \"kr\": \"메뉴 2\", \"price\": \"₱XXX\"},
      {\"en\": \"Dish 3\", \"kr\": \"메뉴 3\", \"price\": \"₱XXX\"}
    ],
    \"tip_en\": \"Insider tip for visitors\",
    \"tip_kr\": \"방문자를 위한 꿀팁\",
    \"hero_image_seed\": \"food-w${CURRENT_WEEK}\",
    \"gallery_seeds\": [\"food-g1-w${CURRENT_WEEK}\", \"food-g2-w${CURRENT_WEEK}\", \"food-g3-w${CURRENT_WEEK}\"]
  },
  \"travel_cards\": [
    {
      \"image_seed\": \"travel1-w${CURRENT_WEEK}\",
      \"badge_en\": \"SECRET SPOT\", \"badge_kr\": \"숨은 명소\",
      \"tags\": [{\"en\": \"Nature\", \"kr\": \"자연\"}, {\"en\": \"Activity\", \"kr\": \"활동\"}],
      \"name_en\": \"Destination Name\", \"name_kr\": \"여행지 이름\",
      \"stars\": \"★★★★☆\", \"rating\": 4.5,
      \"lead_en\": \"3-4 sentence atmospheric description\",
      \"lead_kr\": \"3-4문장 분위기 있는 묘사\",
      \"location\": \"Location info\",
      \"cost\": \"Entrance/cost info\",
      \"tip_en\": \"Insider tip\", \"tip_kr\": \"꿀팁\"
    },
    {
      \"image_seed\": \"travel2-w${CURRENT_WEEK}\",
      \"badge_en\": \"HERITAGE\", \"badge_kr\": \"유산 탐방\",
      \"tags\": [{\"en\": \"Culture\", \"kr\": \"문화\"}, {\"en\": \"Walking\", \"kr\": \"도보\"}],
      \"name_en\": \"Destination 2\", \"name_kr\": \"여행지 2\",
      \"stars\": \"★★★★★\", \"rating\": 4.7,
      \"lead_en\": \"Description\", \"lead_kr\": \"설명\",
      \"location\": \"Location\",
      \"cost\": \"Cost info\",
      \"tip_en\": \"Tip\", \"tip_kr\": \"팁\"
    }
  ],
  \"events\": [
    {\"date_badge\": \"APR 18\", \"image_seed\": \"event1-w${CURRENT_WEEK}\", \"title\": \"Event Name\", \"desc_en\": \"Description\", \"desc_kr\": \"설명\", \"location_en\": \"Venue EN\", \"location_kr\": \"장소 KR\", \"price_en\": \"₱X,XXX\", \"price_kr\": \"₱X,XXX\"},
    {\"date_badge\": \"MAY 05\", \"image_seed\": \"event2-w${CURRENT_WEEK}\", \"title\": \"Event 2\", \"desc_en\": \"...\", \"desc_kr\": \"...\", \"location_en\": \"...\", \"location_kr\": \"...\", \"price_en\": \"FREE Entry\", \"price_kr\": \"입장 무료\"},
    {\"date_badge\": \"JUN 12\", \"image_seed\": \"event3-w${CURRENT_WEEK}\", \"title\": \"Event 3\", \"desc_en\": \"...\", \"desc_kr\": \"...\", \"location_en\": \"...\", \"location_kr\": \"...\", \"price_en\": \"FREE\", \"price_kr\": \"무료\"},
    {\"date_badge\": \"JUL 20\", \"image_seed\": \"event4-w${CURRENT_WEEK}\", \"title\": \"Event 4\", \"desc_en\": \"...\", \"desc_kr\": \"...\", \"location_en\": \"...\", \"location_kr\": \"...\", \"price_en\": \"₱X,XXX\", \"price_kr\": \"₱X,XXX\"}
  ],
  \"picks\": {
    \"date\": \"${DATE_DOT}\",
    \"title_en\": \"Column title that connects to the food feature\",
    \"title_kr\": \"맛집 피처와 연결되는 칼럼 제목\",
    \"body_en\": [\"Paragraph 1 — personal, genuine, connecting food to meaning\", \"Paragraph 2\", \"Paragraph 3\"],
    \"body_kr\": [\"단락 1 — 개인적이고, 진정성 있고, 음식을 의미와 연결\", \"단락 2\", \"단락 3\"],
    \"connect_label_en\": \"This story connects: \",
    \"connect_label_kr\": \"이 이야기가 연결하는 것: \"
  }
}

Focus on Metro Manila (Makati, BGC, Ortigas, Quezon City). Make food reviews atmospheric and genuine — like a real food blogger who actually ate there. Events should be realistic upcoming cultural/K-pop/food events. Return ONLY valid JSON."

    WEEKLY_JSON=$(call_claude "$WEEKLY_PROMPT" 8000) || {
        echo "  WARNING: Failed to generate weekly content, using existing"
    }

    if [ -n "${WEEKLY_JSON:-}" ]; then
        echo "$WEEKLY_JSON" > "$WEEKLY_FILE"
        echo "  Weekly content saved to $WEEKLY_FILE"
    fi
else
    echo "[2/5] Using existing weekly content: $WEEKLY_FILE"
fi

# ─── Step 2.5: Academy Knowledge Layers ───────────────
echo "[2.5/5] Generating ICAN Academy knowledge layers..."

ACADEMY_PROMPT="You are an educational content designer for ICAN Academy, part of ICAN Heralds.
Given today's news articles, generate background knowledge layers for bilingual (Korean/English) learners.

Today's articles (from daily JSON):
$(cat "data/daily-${DATE}.json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
# Cover story
print(f\"COVER: {d['cover_story']['headline_en']}\")
print(f\"  {d['cover_story']['subtitle_en']}\")
# Featured
print(f\"FEATURED: {d['featured_news']['headline_en']}\")
# News grid
for i, n in enumerate(d['news_grid'], 1):
    print(f\"NEWS_{i}: [{n['tag']}] {n['headline_en']}\")
    print(f\"  {n['summary_en']}\")
")

For EACH article (cover, featured, news_1 through news_4), generate knowledge layers.
Return ONLY valid JSON (no markdown fences):

{
  \"cover\": {
    \"layers\": [
      {
        \"depth\": 1,
        \"title_en\": \"Foundation concept title\",
        \"title_kr\": \"기초 개념 제목\",
        \"sub_en\": \"Foundation\", \"sub_kr\": \"기초 개념\", \"badge\": \"Beginner\",
        \"text_en\": \"Explanation with <span class=kw>key terms</span> highlighted. 3-5 sentences, clear and educational.\",
        \"text_kr\": \"<span class=kw>핵심 용어</span>가 강조된 설명. 3-5문장, 명확하고 교육적.\",
        \"bilingual_en\": \"One key sentence in English\",
        \"bilingual_kr\": \"핵심 문장 한국어\",
        \"vocab\": [{\"en\": \"term\", \"kr\": \"용어\"}]
      },
      {
        \"depth\": 2,
        \"title_en\": \"Context & Causes\",
        \"title_kr\": \"맥락과 원인\",
        \"sub_en\": \"Context\", \"sub_kr\": \"맥락\", \"badge\": \"Intermediate\",
        \"text_en\": \"Deeper context...\",
        \"text_kr\": \"더 깊은 맥락...\",
        \"bilingual_en\": \"...\", \"bilingual_kr\": \"...\",
        \"vocab\": [{\"en\": \"term\", \"kr\": \"용어\"}],
        \"quiz\": {
          \"q_en\": \"Question?\", \"q_kr\": \"질문?\",
          \"opts\": [
            {\"en\": \"Wrong answer\", \"kr\": \"오답\", \"correct\": false},
            {\"en\": \"Right answer\", \"kr\": \"정답\", \"correct\": true},
            {\"en\": \"Wrong answer\", \"kr\": \"오답\", \"correct\": false}
          ]
        }
      },
      {
        \"depth\": 3,
        \"title_en\": \"Real-world Impact for Korean Community\",
        \"title_kr\": \"한인 커뮤니티에 대한 실제 영향\",
        \"sub_en\": \"Application\", \"sub_kr\": \"실생활 적용\", \"badge\": \"Advanced\",
        \"text_en\": \"Practical implications...\",
        \"text_kr\": \"실질적 시사점...\",
        \"bilingual_en\": \"...\", \"bilingual_kr\": \"...\",
        \"vocab\": [{\"en\": \"term\", \"kr\": \"용어\"}]
      }
    ],
    \"suggestions_en\": [\"Question 1?\", \"Question 2?\", \"Question 3?\"],
    \"suggestions_kr\": [\"질문 1?\", \"질문 2?\", \"질문 3?\"]
  },
  \"featured\": { ... same structure ... },
  \"news_1\": { ... }, \"news_2\": { ... }, \"news_3\": { ... }, \"news_4\": { ... }
}

RULES:
- Each article MUST have 2-3 layers (depth 1-3)
- Layer 1 = Foundation (explain the basic concept simply, for a teenager)
- Layer 2 = Context (why it matters, causes, add a quiz with 3 options)
- Layer 3 = Real-world impact (specifically for Koreans in the Philippines)
- Use <span class=kw>keyword</span> to highlight 2-4 key terms per layer
- Each layer needs 3-5 vocab words with EN/KR pairs
- Bilingual sentences should be standalone — make sense without the layer text
- suggestions = 3 follow-up questions students might ask Paul-Sam
- Write at a level a smart 14-year-old can understand
- Make Korean text natural (not machine-translated)
- Return ONLY valid JSON"

ACADEMY_JSON=$(call_claude "$ACADEMY_PROMPT" 12000) || {
    echo "  WARNING: Failed to generate academy content"
}

if [ -n "${ACADEMY_JSON:-}" ]; then
    echo "$ACADEMY_JSON" > "data/academy-${DATE}.json"
    echo "  Academy content saved to data/academy-${DATE}.json"

    # Inject academy data into JS
    python3 -c "
import json

with open('data/academy-${DATE}.json') as f:
    academy = json.load(f)

with open('data/daily-${DATE}.json') as f:
    daily = json.load(f)

# Build the JS academy data object
js_data = {}
article_map = {
    'cover': ('cover_story', daily['cover_story']),
    'featured': ('featured_news', daily['featured_news']),
}
for i in range(1, 5):
    key = f'news_{i}'
    if i-1 < len(daily.get('news_grid', [])):
        article_map[key] = ('news_grid', daily['news_grid'][i-1])

for key, (src_key, article) in article_map.items():
    if key not in academy:
        continue
    entry = academy[key]
    js_entry = {
        'tag': article.get('tag', 'News'),
        'tagClass': article.get('tag_class', 'tag-economy'),
        'title_en': article.get('headline_en', ''),
        'title_kr': article.get('headline_kr', ''),
        'summary_en': article.get('subtitle_en', article.get('summary_en', article.get('lead_en', ''))),
        'summary_kr': article.get('subtitle_kr', article.get('summary_kr', article.get('lead_kr', ''))),
        'layers': entry.get('layers', []),
    }
    js_data[key] = js_entry

# Write as JS module
js_content = '// Auto-generated by generate-daily.sh — ' + '${DATE}' + '\n'
js_content += 'var academyData = ' + json.dumps(js_data, ensure_ascii=False, indent=2) + ';\n'
js_content += 'var paulSuggestions = {};\n'
for key in js_data:
    if key in academy and 'suggestions_en' in academy[key]:
        js_content += f'paulSuggestions[\"{key}\"] = {{ en: {json.dumps(academy[key][\"suggestions_en\"])}, kr: {json.dumps(academy[key][\"suggestions_kr\"], ensure_ascii=False)} }};\n'

with open('js/academy-data.js', 'w') as f:
    f.write(js_content)

print('  Generated js/academy-data.js')
"
else
    echo "  Using existing academy data (hardcoded fallback)"
fi

# ─── Step 3: Inject Content ─────────────────────────
echo "[3/5] Injecting content into HTML..."
python3 scripts/inject-content.py

# ─── Step 4: Post-processing ────────────────────────
echo "[4/5] Post-processing..."

# Copy to index.html
cp ican_news.html index.html
echo "  Copied ican_news.html → index.html"

# Update service worker cache name
if [ -f sw.js ]; then
    sed -i.bak "s/const CACHE_NAME = .*/const CACHE_NAME = 'ican-heralds-${DATE}';/" sw.js
    rm -f sw.js.bak
    echo "  Updated sw.js cache: ican-heralds-${DATE}"
fi

# Keep all daily JSON for archive (only clean weekly/academy caches)
ls -t data/weekly-*.json 2>/dev/null | tail -n +5 | xargs rm -f 2>/dev/null || true
ls -t data/academy-*.json 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null || true

# Update archive index
python3 -c "
import json, glob, os

INDEX_FILE = 'data/archive-index.json'

# Load existing index
index = []
if os.path.exists(INDEX_FILE):
    with open(INDEX_FILE) as f:
        index = json.load(f)

existing_dates = {e['date'] for e in index}

# Scan all daily JSON files
for path in sorted(glob.glob('data/daily-*.json')):
    date = path.replace('data/daily-', '').replace('.json', '')
    if date in existing_dates:
        continue
    try:
        with open(path) as f:
            d = json.load(f)
        entry = {
            'date': date,
            'vol': int(open('data/volume.txt').read().strip()) if os.path.exists('data/volume.txt') else 1,
            'cover_en': d.get('cover_story', {}).get('headline_en', ''),
            'cover_kr': d.get('cover_story', {}).get('headline_kr', ''),
            'headlines_en': [
                d.get('featured_news', {}).get('headline_en', '')
            ] + [n.get('headline_en', '') for n in d.get('news_grid', [])[:4]],
            'headlines_kr': [
                d.get('featured_news', {}).get('headline_kr', '')
            ] + [n.get('headline_kr', '') for n in d.get('news_grid', [])[:4]],
            'tags': list(set(
                [d.get('featured_news', {}).get('tag', '')] +
                [n.get('tag', '') for n in d.get('news_grid', [])]
            ))
        }
        index.append(entry)
        print(f'  Added to archive: {date}')
    except Exception as e:
        print(f'  WARNING: Could not index {path}: {e}')

# Sort newest first and save
index.sort(key=lambda x: x['date'], reverse=True)
with open(INDEX_FILE, 'w') as f:
    json.dump(index, f, ensure_ascii=False, indent=2)
print(f'  Archive index: {len(index)} editions')
"

# ─── Step 5: Weekly content refresh check ─────────────
echo "[5/5] Checking weekly content schedule..."
DAY_NUM=$(TZ="Asia/Manila" date +%u)  # 1=Monday
if [ "$DAY_NUM" = "1" ]; then
    echo "  Monday detected — forcing weekly content regeneration"
    rm -f "$WEEKLY_FILE"
    # Re-run weekly generation would happen on next execution
    # For now, just flag it
    echo "REFRESH" > "data/.weekly-refresh-${CURRENT_WEEK}"
fi

echo ""
echo "=== Done! Edition: $DATE | $VOLUME_DISPLAY ==="
echo "Preview: open ican_news.html"
