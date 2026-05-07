#!/bin/bash
# ═══════════════════════════════════════════════════
# ICAN Heralds — Full Update Pipeline (Gemini Edition)
# ═══════════════════════════════════════════════════
# 텔레그램 브리핑 → daily JSON → academy JSON → HTML 주입 → 배포
#
# Usage:
#   ./scripts/update-herald.sh              # 최신 브리핑 자동 감지
#   ./scripts/update-herald.sh 2026-04-12   # 특정 날짜 지정
# ═══════════════════════════════════════════════════

set -euo pipefail
cd "$(dirname "$0")/.."

DATE=${1:-$(TZ="Asia/Manila" date +%Y-%m-%d)}
BRIEFING_DIR="${BRIEFING_DIR:-}"

echo "═══════════════════════════════════════════"
echo " ICAN Heralds Update Pipeline (Gemini)"
echo " Date: $DATE"
echo "═══════════════════════════════════════════"

# Ensure API Key is available
if [ -z "${GEMINI_API_KEY:-}" ]; then
    # Try to load from sibling muni-siki/.env
    ENV_PATH="$(dirname "$0")/../../muni-siki/.env"
    if [ -f "$ENV_PATH" ]; then
        export GEMINI_API_KEY=$(grep '^GEMINI_API_KEY=' "$ENV_PATH" | cut -d= -f2-)
    fi
fi

if [ -z "${GEMINI_API_KEY:-}" ]; then
    echo "ERROR: GEMINI_API_KEY not set"
    exit 1
fi

call_gemini() {
    local prompt="$1"
    local payload_file=$(mktemp)
    
    python3 -c "
import json, sys
prompt = \"\"\"$prompt\"\"\"
payload = {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'maxOutputTokens': 8192, 'temperature': 0.7}}
print(json.dumps(payload))
" > "$payload_file"

    local response=$(curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key=${GEMINI_API_KEY}" \
        -H "Content-Type: application/json" \
        -d @"$payload_file")
    
    rm -f "$payload_file"
    
    echo "$response" | python3 -c '
import sys, json, re
try:
    resp = json.load(sys.stdin)
    if "candidates" not in resp:
        print(f"Error: No candidates in response: {resp}", file=sys.stderr)
        sys.exit(1)
    text = resp["candidates"][0]["content"]["parts"][0]["text"]
    # Remove markdown code blocks if present
    text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    text = text.strip()
    
    # Try to find JSON object if there is surrounding text
    if not text.startswith("{"):
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            text = match.group(1)
    
    json.loads(text)
    print(text)
except Exception as e:
    print(f"Gemini parse error: {e}", file=sys.stderr)
    sys.exit(1)
'
}

# ─── Step 1: Find latest briefing ──────────────────
echo ""
echo "[1/5] Finding briefing for $DATE..."

if [ -z "$BRIEFING_DIR" ]; then
    for candidate in \
        "$HOME/.claude/projects/-Users-worker64/memory/briefings" \
        "$PWD/data/briefings" \
        "$HOME/Documents/Documents - W1 - Mac Studio(64gb)/ICAN-Heralds/data/briefings"
    do
        if [ -d "$candidate" ]; then
            BRIEFING_DIR="$candidate"
            if compgen -G "$candidate/${DATE}_*.md" > /dev/null || [ -f "$candidate/${DATE}.md" ]; then
                break
            fi
        fi
    done
fi

BRIEFING_FILES=$(find "$BRIEFING_DIR" -maxdepth 1 \( -name "${DATE}_*.md" -o -name "${DATE}.md" \) -print 2>/dev/null | sort -r)
if [ -z "$BRIEFING_FILES" ]; then
    echo "  ERROR: No briefing found for $DATE in $BRIEFING_DIR"
    echo "  Run the telegram briefing first, or specify a date."
    exit 1
fi

COMBINED=""
for f in $BRIEFING_FILES; do
    COMBINED="$COMBINED
$(cat "$f")"
    echo "  Found: $(basename "$f")"
done

# ─── Step 2: Generate daily JSON ───────────────────
echo ""
echo "[2/5] Generating daily content JSON..."

DAILY_FILE="data/daily-${DATE}.json"
EDITORIAL_CACHE_DIR="$HOME/ican-editorial-auto/data/heralds-cache"

# Volume
VOLUME_FILE="data/volume.txt"
if [ -f "$VOLUME_FILE" ]; then
    VOLUME=$(cat "$VOLUME_FILE")
else
    VOLUME=3
fi
VOLUME=$((VOLUME + 1))
echo "$VOLUME" > "$VOLUME_FILE"
VOLUME_DISPLAY=$(printf "VOL. %02d" "$VOLUME")

DAY_OF_WEEK=$(TZ="Asia/Manila" date -j -f "%Y-%m-%d" "$DATE" +%A 2>/dev/null || TZ="Asia/Manila" date +%A)
DAY_UPPER=$(echo "$DAY_OF_WEEK" | tr '[:lower:]' '[:upper:]')
DATE_DISPLAY=$(TZ="Asia/Manila" date -j -f "%Y-%m-%d" "$DATE" "+%B %-d, %Y" 2>/dev/null | tr '[:lower:]' '[:upper:]' || TZ="Asia/Manila" date "+%B %-d, %Y" | tr '[:lower:]' '[:upper:]')
DATE_DOT=$(echo "$DATE" | tr '-' '.')
HEADER_LINE="${DAY_UPPER}, ${DATE_DISPLAY} | PHILIPPINES | ${VOLUME_DISPLAY}"

DAILY_PROMPT="You are a bilingual (English/Korean) news editor for ICAN Heralds.
Based on these REAL briefing notes from today, generate a daily news edition JSON.

=== TODAY'S BRIEFING ===
$COMBINED
=== END BRIEFING ===

Return ONLY valid JSON (no markdown fences) with this EXACT structure:
{
  \"edition_date\": \"${DATE}\",
  \"header_date_line\": \"${HEADER_LINE}\",
  \"dashboard\": {
    \"php_krw_rate\": \"REAL RATE FROM BRIEFING\",
    \"weather_en\": \"REAL WEATHER FROM BRIEFING\",
    \"weather_kr\": \"한국어 날씨\",
    \"date\": \"${DATE_DOT}\",
    \"embassy_en\": \"Normal Operations\",
    \"embassy_kr\": \"정상 운영\"
  },
  \"cover_story\": {
    \"headline_en\": \"...\", \"headline_kr\": \"...\",
    \"subtitle_en\": \"...\", \"subtitle_kr\": \"...\",
    \"body_en\": [\"Paragraph 1\", \"Paragraph 2\", \"Paragraph 3\"],
    \"body_kr\": [\"단락 1\", \"단락 2\", \"단락 3\"],
    \"image_seed\": \"cover-${DATE}\",
    \"image_query\": \"Visual description for AI image generation\",
    \"image_caption\": \"Photo: description (date)\",
    \"author\": \"By ICAN Herald Editorial\",
    \"read_time_min\": 5
  },
  \"featured_news\": {
    \"tag\": \"Cooperation\", \"tag_class\": \"tag-diplomacy\",
    \"headline_en\": \"...\", \"headline_kr\": \"...\",
    \"lead_en\": \"...\", \"lead_kr\": \"...\",
    \"image_seed\": \"feat-${DATE}\", \"image_query\": \"...\",
    \"desk\": \"Diplomacy Desk\", \"read_time_min\": 4
  },
  \"news_grid\": [
    {\"tag\": \"Economy\", \"tag_class\": \"tag-economy\", \"headline_en\": \"...\", \"headline_kr\": \"...\", \"summary_en\": \"...\", \"summary_kr\": \"...\", \"image_seed\": \"news1-${DATE}\", \"image_query\": \"...\", \"read_time_min\": 2},
    {\"tag\": \"Safety\", \"tag_class\": \"tag-safety\", \"headline_en\": \"...\", \"headline_kr\": \"...\", \"summary_en\": \"...\", \"summary_kr\": \"...\", \"image_seed\": \"news2-${DATE}\", \"image_query\": \"...\", \"read_time_min\": 2},
    {\"tag\": \"Culture\", \"tag_class\": \"tag-culture\", \"headline_en\": \"...\", \"headline_kr\": \"...\", \"summary_en\": \"...\", \"summary_kr\": \"...\", \"image_seed\": \"news3-${DATE}\", \"image_query\": \"...\", \"read_time_min\": 2},
    {\"tag\": \"Security\", \"tag_class\": \"tag-security\", \"headline_en\": \"...\", \"headline_kr\": \"...\", \"summary_en\": \"...\", \"summary_kr\": \"...\", \"image_seed\": \"news4-${DATE}\", \"image_query\": \"...\", \"read_time_min\": 2}
  ],
  \"word_of_day\": {
    \"word\": \"...\", \"pronunciation\": \"...\", \"type\": \"...\", \"definition_en\": \"...\", \"definition_kr\": \"...\", \"example_en\": \"...\", \"example_kr\": \"...\", \"grade\": \"A+\"
  }
}
"

call_gemini "$DAILY_PROMPT" > "$DAILY_FILE"
echo "  Daily JSON generated: $DAILY_FILE"

# Validate
python3 -c "import json; json.load(open('$DAILY_FILE')); print('  Daily JSON valid')" || {
    echo "  ERROR: Invalid daily JSON"
    exit 1
}

mkdir -p "$EDITORIAL_CACHE_DIR"
cp "$DAILY_FILE" "$EDITORIAL_CACHE_DIR/"
echo "  Mirrored daily JSON to $EDITORIAL_CACHE_DIR"

# ─── Step 3: Generate academy JSON ─────────────────
echo ""
echo "[3/5] Generating Academy knowledge layers..."

ACADEMY_FILE="data/academy-${DATE}.json"
ACADEMY_PROMPT="You are an educational content designer for ICAN Academy.
Based on this daily news JSON, generate background knowledge layers for each article.

$(cat "$DAILY_FILE")

Return ONLY valid JSON with 3 layers per article (cover, featured, news_1-4).
"

call_gemini "$ACADEMY_PROMPT" > "$ACADEMY_FILE"
echo "  Academy JSON generated: $ACADEMY_FILE"

# ─── Step 4: Inject into HTML ──────────────────────
echo ""
echo "[4/5] Injecting content..."
python3 scripts/inject-direct.py "$DAILY_FILE"

# ─── Step 4b: Prewarm image ladder ────────────────
echo ""
echo "[4b/5] Prewarming image ladder..."
if ! bash scripts/prewarm-images.sh; then
    echo "  WARNING: Some image URLs did not prewarm cleanly."
    echo "  Primary/secondary/fallback chain will still protect the live page."
fi

echo ""
echo "[4c/5] Rebuilding HTML with local cache-first image paths..."
python3 scripts/inject-direct.py "$DAILY_FILE"

# ─── Step 5: Git commit & push ─────────────────────
echo ""
echo "[5/5] Deploying..."

COVER=$(python3 -c "import json; d=json.load(open('$DAILY_FILE')); print(d['cover_story']['headline_en'][:60])")

git add ican_news.html index.html sw.js data/ js/academy-data.js images/cache
if git diff --staged --quiet; then
    echo "  No changes to commit"
else
    git commit -m "Daily edition: ${DATE} (${VOLUME_DISPLAY}) — ${COVER}"
    git push origin main
    echo "  Pushed to GitHub → Vercel auto-deploy"
fi

echo ""
echo "═══════════════════════════════════════════"
echo " Done! ${HEADER_LINE}"
echo " Preview: open ican_news.html"
echo "═══════════════════════════════════════════"
