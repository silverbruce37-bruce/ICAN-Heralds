#!/bin/bash
# ═══════════════════════════════════════════════════
# ICAN Heralds — Full Update Pipeline
# ═══════════════════════════════════════════════════
# 텔레그램 브리핑 → daily JSON → academy JSON → HTML 주입 → 배포
#
# Usage:
#   ./scripts/update-herald.sh              # 최신 브리핑 자동 감지
#   ./scripts/update-herald.sh 2026-04-12   # 특정 날짜 지정
#
# Called by Claude Code when user says "신문기사 업뎃해줘"
# ═══════════════════════════════════════════════════

set -euo pipefail
cd "$(dirname "$0")/.."

DATE=${1:-$(TZ="Asia/Manila" date +%Y-%m-%d)}
BRIEFING_DIR="$HOME/.claude/projects/-Users-worker64/memory/briefings"

echo "═══════════════════════════════════════════"
echo " ICAN Heralds Update Pipeline"
echo " Date: $DATE"
echo "═══════════════════════════════════════════"

# ─── Step 1: Find latest briefing ──────────────────
echo ""
echo "[1/5] Finding briefing for $DATE..."

BRIEFING_FILES=$(ls "$BRIEFING_DIR"/${DATE}_*.md 2>/dev/null | sort -r)
if [ -z "$BRIEFING_FILES" ]; then
    echo "  ERROR: No briefing found for $DATE in $BRIEFING_DIR"
    echo "  Run the telegram briefing first, or specify a date."
    exit 1
fi

# Combine all briefings for the day
COMBINED=""
for f in $BRIEFING_FILES; do
    COMBINED="$COMBINED
$(cat "$f")"
    echo "  Found: $(basename "$f")"
done

# ─── Step 2: Generate daily JSON via Claude ────────
echo ""
echo "[2/5] Generating daily content JSON..."

DAILY_FILE="data/daily-${DATE}.json"

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

claude --model sonnet -p --dangerously-skip-permissions "
You are a bilingual (English/Korean) news editor for ICAN Heralds.

Based on these REAL briefing notes from today, generate a daily news edition JSON.

=== TODAY'S BRIEFING ===
$COMBINED
=== END BRIEFING ===

Return ONLY valid JSON (no markdown fences) with this EXACT structure:
{
  \"edition_date\": \"${DATE}\",
  \"header_date_line\": \"${HEADER_LINE}\",
  \"dashboard\": {
    \"php_krw_rate\": \"USE REAL RATE FROM BRIEFING or estimate\",
    \"weather_en\": \"USE REAL WEATHER FROM BRIEFING\",
    \"weather_kr\": \"한국어 날씨\",
    \"date\": \"${DATE_DOT}\",
    \"embassy_en\": \"Normal Operations\",
    \"embassy_kr\": \"정상 운영\"
  },
  \"cover_story\": {
    \"headline_en\": \"Most important story (max 80 chars)\",
    \"headline_kr\": \"가장 중요한 기사 한국어\",
    \"subtitle_en\": \"1-2 sentence subtitle\",
    \"subtitle_kr\": \"부제목\",
    \"body_en\": [\"Paragraph 1 (substantial)\", \"Paragraph 2\", \"Paragraph 3\"],
    \"body_kr\": [\"단락 1\", \"단락 2\", \"단락 3\"],
    \"image_seed\": \"cover-${DATE}\",
    \"image_caption\": \"Photo: description (date)\",
    \"author\": \"By ICAN Herald Editorial\",
    \"read_time_min\": 5
  },
  \"featured_news\": {
    \"tag\": \"Cooperation\",
    \"tag_class\": \"tag-diplomacy\",
    \"headline_en\": \"Second most important story\",
    \"headline_kr\": \"두 번째 중요 기사\",
    \"lead_en\": \"2-3 sentence lead\",
    \"lead_kr\": \"리드\",
    \"image_seed\": \"feat-${DATE}\",
    \"desk\": \"Diplomacy Desk\",
    \"read_time_min\": 4
  },
  \"news_grid\": [
    {\"tag\": \"Economy\", \"tag_class\": \"tag-economy\", \"headline_en\": \"...\", \"headline_kr\": \"...\", \"summary_en\": \"...\", \"summary_kr\": \"...\", \"image_seed\": \"news1-${DATE}\", \"read_time_min\": 2},
    {\"tag\": \"Safety\", \"tag_class\": \"tag-safety\", \"headline_en\": \"...\", \"headline_kr\": \"...\", \"summary_en\": \"...\", \"summary_kr\": \"...\", \"image_seed\": \"news2-${DATE}\", \"read_time_min\": 2},
    {\"tag\": \"Culture\", \"tag_class\": \"tag-culture\", \"headline_en\": \"...\", \"headline_kr\": \"...\", \"summary_en\": \"...\", \"summary_kr\": \"...\", \"image_seed\": \"news3-${DATE}\", \"read_time_min\": 2},
    {\"tag\": \"Security\", \"tag_class\": \"tag-security\", \"headline_en\": \"...\", \"headline_kr\": \"...\", \"summary_en\": \"...\", \"summary_kr\": \"...\", \"image_seed\": \"news4-${DATE}\", \"read_time_min\": 2}
  ],
  \"word_of_day\": {
    \"word\": \"English Word\",
    \"pronunciation\": \"phonetic\",
    \"type\": \"noun\",
    \"definition_en\": \"definition\",
    \"definition_kr\": \"정의\",
    \"example_en\": \"Example sentence.\",
    \"example_kr\": \"예문.\",
    \"grade\": \"A+\"
  }
}

RULES:
- USE REAL DATA from the briefing (exchange rates, weather, actual news stories)
- Cover story = biggest impact story for Korean community
- tag_class must be: tag-security, tag-economy, tag-culture, tag-diplomacy, or tag-safety
- 3 substantial paragraphs per language for cover body
- Word of the day connects to cover story theme
- Korean text must be natural, not machine-translated
- Return ONLY valid JSON
" > "$DAILY_FILE"

# Validate
python3 -c "import json; json.load(open('$DAILY_FILE')); print('  Daily JSON valid')" || {
    echo "  ERROR: Invalid daily JSON"
    exit 1
}

# ─── Step 3: Generate academy JSON via Claude ──────
echo ""
echo "[3/5] Generating Academy knowledge layers..."

ACADEMY_FILE="data/academy-${DATE}.json"

claude --model sonnet -p --dangerously-skip-permissions "
You are an educational content designer for ICAN Academy.

Based on this daily news JSON, generate background knowledge layers for each article.

$(cat "$DAILY_FILE")

Return ONLY valid JSON (no markdown fences) with this structure for EACH article key (cover, featured, news_1, news_2, news_3, news_4):
{
  \"cover\": {
    \"layers\": [
      {\"depth\": 1, \"title_en\": \"Foundation concept\", \"title_kr\": \"기초 개념\", \"sub_en\": \"Foundation\", \"sub_kr\": \"기초\", \"badge\": \"Beginner\",
       \"text_en\": \"Explanation with <span class=kw>key terms</span>. 3-5 sentences.\",
       \"text_kr\": \"<span class=kw>핵심 용어</span> 포함 설명.\",
       \"bilingual_en\": \"Key sentence EN\", \"bilingual_kr\": \"핵심 문장 KR\",
       \"vocab\": [{\"en\": \"term\", \"kr\": \"용어\"}, ...]},
      {\"depth\": 2, \"title_en\": \"Context\", \"title_kr\": \"맥락\", \"sub_en\": \"Context\", \"sub_kr\": \"맥락\", \"badge\": \"Intermediate\",
       \"text_en\": \"...\", \"text_kr\": \"...\", \"bilingual_en\": \"...\", \"bilingual_kr\": \"...\",
       \"vocab\": [...],
       \"quiz\": {\"q_en\": \"?\", \"q_kr\": \"?\", \"opts\": [{\"en\": \"Wrong\", \"kr\": \"오답\", \"correct\": false}, {\"en\": \"Right\", \"kr\": \"정답\", \"correct\": true}, {\"en\": \"Wrong\", \"kr\": \"오답\", \"correct\": false}]}},
      {\"depth\": 3, \"title_en\": \"Impact for Korean Community\", \"title_kr\": \"한인 사회 영향\", \"sub_en\": \"Application\", \"sub_kr\": \"적용\", \"badge\": \"Advanced\",
       \"text_en\": \"...\", \"text_kr\": \"...\", \"bilingual_en\": \"...\", \"bilingual_kr\": \"...\", \"vocab\": [...]}
    ],
    \"suggestions_en\": [\"Q1?\", \"Q2?\", \"Q3?\"],
    \"suggestions_kr\": [\"질문1?\", \"질문2?\", \"질문3?\"]
  },
  \"featured\": { ... same structure ... },
  \"news_1\": { ... }, \"news_2\": { ... }, \"news_3\": { ... }, \"news_4\": { ... }
}

RULES:
- Each article: 2-3 layers (L1 Foundation, L2 Context+quiz, L3 Real-world for Koreans in PH)
- Use <span class=kw>keyword</span> for 2-4 key terms per layer
- 3-5 vocab words per layer
- Quiz on L2 with 3 options (1 correct)
- Write for a smart 14-year-old
- Natural Korean, not machine-translated
- Return ONLY valid JSON
" > "$ACADEMY_FILE"

python3 -c "import json; json.load(open('$ACADEMY_FILE')); print('  Academy JSON valid')" || {
    echo "  WARNING: Academy JSON invalid, skipping"
}

# ─── Step 4: Inject into HTML ──────────────────────
echo ""
echo "[4/5] Injecting content..."

python3 scripts/inject-direct.py "$DAILY_FILE"

# ─── Step 5: Git commit & push ─────────────────────
echo ""
echo "[5/5] Deploying..."

COVER=$(python3 -c "import json; d=json.load(open('$DAILY_FILE')); print(d['cover_story']['headline_en'][:60])")

git add ican_news.html index.html sw.js data/ js/academy-data.js
if git diff --staged --quiet; then
    echo "  No changes to commit"
else
    git commit -m "$(cat <<EOF
Daily edition: ${DATE} (${VOLUME_DISPLAY}) — ${COVER}

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
    git push origin main
    echo "  Pushed to GitHub → Vercel auto-deploy"
fi

echo ""
echo "═══════════════════════════════════════════"
echo " Done! ${HEADER_LINE}"
echo " Preview: open ican_news.html"
echo "═══════════════════════════════════════════"
