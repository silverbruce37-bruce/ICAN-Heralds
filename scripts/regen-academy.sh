#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  regen-academy.sh — Manual academy data recovery
# ──────────────────────────────────────────────────────────────
#  When: GitHub Actions daily workflow alerted that academy
#        generation failed (typically Gemini free-tier quota).
#  What: Regenerates ONLY academy data for today's edition using
#        local Claude CLI, rebuilds HTML, commits, pushes.
#  Daily 기사 본문은 건드리지 않음 — 학습 콘텐츠만 재생성.
#
#  Usage:
#      cd ~/Desktop/ICAN-Heralds && bash scripts/regen-academy.sh
# ──────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

DATE=$(TZ='Asia/Manila' date +%Y-%m-%d)
echo "📚 Academy regeneration for ${DATE}"
echo ""

echo "→ git pull --rebase..."
git pull --rebase

DAILY_FILE="data/daily-${DATE}.json"
if [ ! -f "$DAILY_FILE" ]; then
    echo "❌ ${DAILY_FILE} not found."
    echo "   오늘 Herald 발행이 아직 안 됐습니다 (PHT 08~09시 이후 재시도)."
    exit 1
fi

# ─── Build academy prompt (identical structure to generate-daily.sh) ───
ACADEMY_PROMPT="You are an educational content designer for ICAN Academy, part of ICAN Heralds.
Given today's news articles, generate background knowledge layers for bilingual (Korean/English) learners.

Today's articles (from daily JSON):
$(cat "$DAILY_FILE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"COVER: {d['cover_story']['headline_en']}\")
print(f\"  {d['cover_story']['subtitle_en']}\")
print(f\"FEATURED: {d['featured_news']['headline_en']}\")
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
        \"text_en\": \"Explanation with <span class=kw>key terms</span> highlighted. 3-5 sentences.\",
        \"text_kr\": \"<span class=kw>핵심 용어</span>가 강조된 설명. 3-5문장.\",
        \"bilingual_en\": \"One key sentence in English\",
        \"bilingual_kr\": \"핵심 문장 한국어\",
        \"vocab\": [{\"en\": \"term\", \"kr\": \"용어\"}]
      },
      {
        \"depth\": 2, \"title_en\": \"Context & Causes\", \"title_kr\": \"맥락과 원인\",
        \"sub_en\": \"Context\", \"sub_kr\": \"맥락\", \"badge\": \"Intermediate\",
        \"text_en\": \"...\", \"text_kr\": \"...\",
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
        \"depth\": 3, \"title_en\": \"Real-world Impact for Korean Community\", \"title_kr\": \"한인 커뮤니티에 대한 실제 영향\",
        \"sub_en\": \"Application\", \"sub_kr\": \"실생활 적용\", \"badge\": \"Advanced\",
        \"text_en\": \"...\", \"text_kr\": \"...\",
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
- Layer 1 = Foundation / Layer 2 = Context (with 3-option quiz) / Layer 3 = Impact for Korean community in PH
- Use <span class=kw>keyword</span> to highlight 2-4 key terms per layer
- Each layer: 3-5 vocab (en/kr pairs), standalone bilingual summary
- suggestions = 3 follow-up questions
- Write for smart 14-year-old, natural Korean (not machine-translated)
- Return ONLY valid JSON"

# ─── Call Claude CLI (local, no quota) ───
echo "→ Calling Claude CLI locally (sonnet)..."
PROMPT_FILE=$(mktemp)
echo "$ACADEMY_PROMPT" > "$PROMPT_FILE"

ACADEMY_JSON=$(claude --model sonnet -p --dangerously-skip-permissions "$(cat "$PROMPT_FILE")" 2>/dev/null | python3 -c "
import sys
text = sys.stdin.read().strip()
if text.startswith('\`\`\`json'): text = text[7:]
if text.startswith('\`\`\`'): text = text[3:]
if text.endswith('\`\`\`'): text = text[:-3]
print(text.strip())
")
rm -f "$PROMPT_FILE"

if [ -z "$ACADEMY_JSON" ]; then
    echo "❌ Claude CLI returned empty. 'claude' 명령이 작동하는지 확인하세요."
    exit 1
fi

echo "$ACADEMY_JSON" > "data/academy-${DATE}.json"
echo "→ Saved data/academy-${DATE}.json"

# ─── Inject into js/academy-data.js ───
export DATE
python3 <<'PYEOF'
import json, re, os

DATE = os.environ['DATE']
with open(f"data/academy-{DATE}.json") as f:
    raw = f.read()
raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', raw)
if not raw.strip().startswith('{'):
    start = raw.find('{'); end = raw.rfind('}')
    if start >= 0 and end > start:
        raw = raw[start:end+1]
academy = json.loads(raw)

with open(f"data/daily-{DATE}.json") as f:
    daily = json.load(f)

article_map = {
    'cover': daily['cover_story'],
    'featured': daily['featured_news'],
}
for i in range(1, 5):
    if i-1 < len(daily.get('news_grid', [])):
        article_map[f'news_{i}'] = daily['news_grid'][i-1]

js_data = {}
for key, article in article_map.items():
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

js_content = f'// Auto-generated by regen-academy.sh — {DATE}\n'
js_content += 'var academyData = ' + json.dumps(js_data, ensure_ascii=False, indent=2) + ';\n'
js_content += 'var paulSuggestions = {};\n'
for key in js_data:
    if key in academy and 'suggestions_en' in academy[key]:
        js_content += f'paulSuggestions[\"{key}\"] = {{ en: {json.dumps(academy[key]["suggestions_en"])}, kr: {json.dumps(academy[key]["suggestions_kr"], ensure_ascii=False)} }};\n'

with open('js/academy-data.js', 'w') as f:
    f.write(js_content)
print("→ Rebuilt js/academy-data.js")
PYEOF

echo "→ Rebuilding HTML with new academy data..."
python3 scripts/inject-direct.py
cp ican_news.html index.html
if [ -f sw.js ]; then
    sed -i.bak "s/const CACHE_NAME = .*/const CACHE_NAME = 'ican-heralds-${DATE}-academy';/" sw.js
    rm -f sw.js.bak
fi

# ─── Commit & push ───
git add ican_news.html index.html sw.js js/academy-data.js "data/academy-${DATE}.json"
if git diff --staged --quiet; then
    echo "✓ No changes to commit (already up to date)."
    exit 0
fi

git commit -m "Regenerate academy for ${DATE} (manual recovery via local Claude CLI)"
git push

echo ""
echo "✅ Academy regenerated and deployed."
echo "   Verify: https://ican-heralds.vercel.app/ (Cmd+Shift+R for cache bust)"
