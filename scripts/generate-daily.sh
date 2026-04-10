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

# ─── Claude CLI call with retry ─────────────────────
call_gemini() {
    local prompt="$1"
    local result=""
    local max_retries=3

    # Write prompt to temp file for safe handling
    local prompt_file
    prompt_file=$(mktemp)
    echo "$prompt" > "$prompt_file"

    for attempt in $(seq 1 $max_retries); do
        # Build request JSON via Python (handles escaping)
        local request_file
        request_file=$(mktemp)
        python3 -c "
import json
with open('$prompt_file') as f:
    prompt_text = f.read()
req = {
    'contents': [{'parts': [{'text': prompt_text}]}],
    'generationConfig': {
        'temperature': 0.7,
        'responseMimeType': 'application/json'
    }
}
with open('$request_file', 'w') as f:
    json.dump(req, f)
"

        # Call Gemini API (free tier)
        local response_file
        response_file=$(mktemp)
        local http_code
        http_code=$(curl -s -w "%{http_code}" -o "$response_file" \
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key=${GEMINI_API_KEY}" \
            -H "content-type: application/json" \
            -d @"$request_file")

        if [ "$http_code" = "200" ]; then
            result=$(python3 -c "
import json
with open('$response_file') as f:
    resp = json.load(f)
text = resp['candidates'][0]['content']['parts'][0]['text']
# Strip markdown fences if present
text = text.strip()
if text.startswith('\`\`\`json'):
    text = text[7:]
if text.startswith('\`\`\`'):
    text = text[3:]
if text.endswith('\`\`\`'):
    text = text[:-3]
print(text.strip())
")
            rm -f "$request_file" "$response_file"
            if [ -n "$result" ]; then
                break
            fi
        else
            echo "  Attempt $attempt: HTTP $http_code" >&2
            cat "$response_file" >&2
            echo "" >&2
            rm -f "$request_file" "$response_file"
        fi

        sleep 60
    done

    rm -f "$prompt_file"

    if [ -z "$result" ]; then
        echo "ERROR: Gemini API failed after $max_retries attempts" >&2
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
    \"php_krw_rate\": \"24.XX\",
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

DAILY_JSON=$(call_gemini "$DAILY_PROMPT" 6000) || {
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

if [ ! -f "$WEEKLY_FILE" ]; then
    echo "[2/4] Generating weekly content (new week: $CURRENT_WEEK)..."

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

    WEEKLY_JSON=$(call_gemini "$WEEKLY_PROMPT" 8000) || {
        echo "  WARNING: Failed to generate weekly content, using existing"
    }

    if [ -n "${WEEKLY_JSON:-}" ]; then
        echo "$WEEKLY_JSON" > "$WEEKLY_FILE"
        echo "  Weekly content saved to $WEEKLY_FILE"
    fi
else
    echo "[2/4] Using existing weekly content: $WEEKLY_FILE"
fi

# ─── Step 3: Inject Content ─────────────────────────
echo "[3/4] Injecting content into HTML..."
python3 scripts/inject-content.py

# ─── Step 4: Post-processing ────────────────────────
echo "[4/4] Post-processing..."

# Copy to index.html
cp ican_news.html index.html
echo "  Copied ican_news.html → index.html"

# Update service worker cache name
if [ -f sw.js ]; then
    sed -i.bak "s/const CACHE_NAME = .*/const CACHE_NAME = 'ican-heralds-${DATE}';/" sw.js
    rm -f sw.js.bak
    echo "  Updated sw.js cache: ican-heralds-${DATE}"
fi

# Cleanup old JSON files (keep 7 daily, 4 weekly)
ls -t data/daily-*.json 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null || true
ls -t data/weekly-*.json 2>/dev/null | tail -n +5 | xargs rm -f 2>/dev/null || true

echo ""
echo "=== Done! Edition: $DATE | $VOLUME_DISPLAY ==="
echo "Preview: open ican_news.html"
