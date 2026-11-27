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
if [ -f "data/daily-${DATE}.json" ]; then
    # Re-publishing a day that already exists (workflow_dispatch force=true):
    # keep the same volume number instead of incrementing again.
    echo "  Re-publishing ${DATE} — keeping VOL. $(printf '%02d' "$VOLUME")"
else
    VOLUME=$((VOLUME + 1))
    echo "$VOLUME" > "$VOLUME_FILE"
fi
VOLUME_DISPLAY=$(printf "VOL. %02d" "$VOLUME")

HEADER_LINE="${DAY_OF_WEEK}, ${DATE_DISPLAY} | PHILIPPINES | ${VOLUME_DISPLAY}"

echo "=== ICAN Heralds Daily Generator v2 ==="
echo "Date: $DATE | $VOLUME_DISPLAY | Week: $CURRENT_WEEK"

# ─── [0] Live market data (real numbers, never invented) ───────
echo "[0/5] Fetching live PHP/KRW rate..."
PHP_KRW_RATE=$(python3 scripts/fetch-live-data.py --rate-only 2>/dev/null || true)
if [ -z "${PHP_KRW_RATE:-}" ]; then
    PHP_KRW_RATE="unknown"
    echo "  WARNING: live rate unavailable — the post-generation enrichment step will retry with all providers"
else
    echo "  Live rate: 1 PHP = ${PHP_KRW_RATE} KRW"
fi

# ─── [0.5] Real headlines from RSS (grounding for the AI) ──────
echo "[0.5/5] Fetching today's real headlines from RSS..."
NEWS_DIGEST=$(timeout 90 python3 scripts/fetch-news.py --date "$DATE" 2>/dev/null || true)
if [ -z "${NEWS_DIGEST:-}" ] || [ "${NEWS_DIGEST}" = "(no headlines available)" ]; then
    NEWS_DIGEST="(no headlines could be fetched today — keep today's edition general and explicitly avoid specific statistics, names, quotes and URLs)"
    echo "  WARNING: RSS fetch failed; the edition will run without news grounding"
else
    echo "  Headlines fetched: $(printf '%s\n' "$NEWS_DIGEST" | wc -l | tr -d ' ') lines"
fi
FETCH_STAMP=$(TZ="Asia/Manila" date +"%Y-%m-%d %H:%M")

# ─── Anthropic API call with retry ──────────────────
# Works both locally (claude CLI) and on GitHub Actions (API direct)
call_claude() {
    local prompt="$1"
    local result=""
    local max_retries=3
    # 호출부가 요청한 출력 토큰 한도($2)를 쓰되, 하한은 8192로 둔다.
    local max_tokens="${2:-8192}"
    [ "$max_tokens" -lt 8192 ] 2>/dev/null && max_tokens=8192
    OPENROUTER_MODEL="${OPENROUTER_MODEL:-google/gemma-4-26b-a4b-it}"

    _parse_openai_json() {
        python3 -c "
import sys, json, re
try:
    resp = json.load(sys.stdin)
    choice = resp['choices'][0]
    text = (choice.get('message') or {}).get('content') or ''
    if not text.strip():
        print('Empty content (finish_reason=' + str(choice.get('finish_reason')) + ')', file=sys.stderr)
        raise SystemExit(1)
    if text.startswith('\`\`\`json'): text = text[7:]
    if text.startswith('\`\`\`'): text = text[3:]
    if text.endswith('\`\`\`'): text = text[:-3]
    text = text.strip()
    if not text.startswith('{'):
        s = text.find('{'); e = text.rfind('}')
        if s >= 0 and e > s: text = text[s:e+1]
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    json.loads(text)
    print(text)
except Exception as e:
    print(f'Parse error: {e}', file=sys.stderr)
"
    }

    for attempt in $(seq 1 $max_retries); do
        local prompt_file
        prompt_file=$(mktemp)
        echo "$prompt" > "$prompt_file"
        result=""

        # ── Engine 1: Gemini ────────────────────────────────────────────────
        if [ -n "${GEMINI_API_KEY:-}" ]; then
            local gemini_payload
            gemini_payload=$(mktemp)
            python3 -c "
import json
prompt = open('$prompt_file').read()
payload = {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'maxOutputTokens': $max_tokens, 'temperature': 0.7}}
json.dump(payload, open('$gemini_payload', 'w'), ensure_ascii=False)
"
            local raw_resp http_code body
            raw_resp=$(curl -s -w "\n%{http_code}" \
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key=${GEMINI_API_KEY}" \
                -H "content-type: application/json" \
                -d @"$gemini_payload" 2>&1)
            http_code=$(echo "$raw_resp" | tail -1)
            body=$(echo "$raw_resp" | sed '$d')
            rm -f "$gemini_payload"

            if [ "$http_code" = "200" ]; then
                result=$(echo "$body" | python3 -c "
import sys, json, re
try:
    resp = json.load(sys.stdin)
    parts = resp['candidates'][0]['content']['parts']
    text = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
    if text.startswith('\`\`\`json'): text = text[7:]
    if text.startswith('\`\`\`'): text = text[3:]
    if text.endswith('\`\`\`'): text = text[:-3]
    text = text.strip()
    if not text.startswith('{'):
        s = text.find('{'); e = text.rfind('}')
        if s >= 0 and e > s: text = text[s:e+1]
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    json.loads(text)
    print(text)
except Exception as e:
    print(f'Gemini parse error: {e}', file=sys.stderr)
")
                [ -n "$result" ] && echo "  [Engine] Gemini OK (gemini-3.5-flash-lite)" >&2
            else
                echo "  Gemini HTTP $http_code → 다음 엔진" >&2
                echo "  Gemini error: $(echo "$body" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("error",{}).get("message","") or str(d)[:300])' 2>/dev/null)" >&2
            fi
        fi

        # ── Engine 2: OpenAI (gpt-6-luna) ───────────────────────────────────
        if [ -z "$result" ] && [ -n "${OPENAI_API_KEY:-}" ]; then
            local oai_payload
            oai_payload=$(mktemp)
            python3 -c "
import json
prompt = open('$prompt_file').read()
payload = {'model': 'gpt-6-luna', 'max_completion_tokens': $max_tokens, 'reasoning_effort': 'low', 'messages': [{'role': 'user', 'content': prompt}]}
json.dump(payload, open('$oai_payload', 'w'), ensure_ascii=False)
"
            local raw_resp http_code body
            raw_resp=$(curl -s -w "\n%{http_code}" \
                "https://api.openai.com/v1/chat/completions" \
                -H "Authorization: Bearer ${OPENAI_API_KEY}" \
                -H "Content-Type: application/json" \
                -d @"$oai_payload" 2>&1)
            http_code=$(echo "$raw_resp" | tail -1)
            body=$(echo "$raw_resp" | sed '$d')
            rm -f "$oai_payload"

            if [ "$http_code" = "200" ]; then
                result=$(echo "$body" | _parse_openai_json)
                [ -n "$result" ] && echo "  [Engine] OpenAI OK (gpt-6-luna)" >&2
            else
                echo "  OpenAI HTTP $http_code → Anthropic 폴백" >&2
                echo "  OpenAI error: $(echo "$body" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("error",{}).get("message",""))' 2>/dev/null)" >&2
            fi
        fi

        # ── Engine 2b: OpenRouter (OPENROUTER_API_KEY 있을 때만) ─────────────
        if [ -z "$result" ] && [ -n "${OPENROUTER_API_KEY:-}" ]; then
            local or_payload
            or_payload=$(mktemp)
            python3 -c "
import json
prompt = open('$prompt_file').read()
payload = {'model': '$OPENROUTER_MODEL', 'max_tokens': $max_tokens, 'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0.7}
json.dump(payload, open('$or_payload', 'w'), ensure_ascii=False)
"
            local raw_resp http_code body
            raw_resp=$(curl -s -w "\n%{http_code}" \
                "https://openrouter.ai/api/v1/chat/completions" \
                -H "Authorization: Bearer ${OPENROUTER_API_KEY}" \
                -H "Content-Type: application/json" \
                -H "HTTP-Referer: https://ican-heralds.vercel.app" \
                -H "X-Title: ICAN Heralds" \
                -d @"$or_payload" 2>&1)
            http_code=$(echo "$raw_resp" | tail -1)
            body=$(echo "$raw_resp" | sed '$d')
            rm -f "$or_payload"

            if [ "$http_code" = "200" ]; then
                result=$(echo "$body" | _parse_openai_json)
                [ -n "$result" ] && echo "  [Engine] OpenRouter OK ($OPENROUTER_MODEL)" >&2
            else
                echo "  OpenRouter HTTP $http_code → Anthropic 폴백" >&2
                echo "  OpenRouter error: $(echo "$body" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("error",{}).get("message","") or str(d)[:300])' 2>/dev/null)" >&2
            fi
        fi

        # ── Engine 3: Anthropic Claude ──────────────────────────────────────
        if [ -z "$result" ] && [ -n "${ANTHROPIC_API_KEY:-}" ]; then
            local anthropic_payload
            anthropic_payload=$(mktemp)
            python3 -c "
import json
prompt = open('$prompt_file').read()
payload = {'model': 'claude-haiku-4-5-20251001', 'max_tokens': $max_tokens, 'messages': [{'role': 'user', 'content': prompt}]}
json.dump(payload, open('$anthropic_payload', 'w'), ensure_ascii=False)
"
            local raw_resp http_code body
            raw_resp=$(curl -s -w "\n%{http_code}" https://api.anthropic.com/v1/messages \
                -H "x-api-key: ${ANTHROPIC_API_KEY}" \
                -H "anthropic-version: 2023-06-01" \
                -H "content-type: application/json" \
                -d @"$anthropic_payload" 2>&1)
            http_code=$(echo "$raw_resp" | tail -1)
            body=$(echo "$raw_resp" | sed '$d')
            rm -f "$anthropic_payload"

            if [ "$http_code" = "200" ]; then
                result=$(echo "$body" | python3 -c "
import sys, json, re
try:
    resp = json.load(sys.stdin)
    text = resp.get('content', [{}])[0].get('text', '')
    if text.startswith('\`\`\`json'): text = text[7:]
    if text.startswith('\`\`\`'): text = text[3:]
    if text.endswith('\`\`\`'): text = text[:-3]
    text = text.strip()
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    json.loads(text)
    print(text)
except Exception as e:
    print(f'Anthropic parse error: {e}', file=sys.stderr)
")
                [ -n "$result" ] && echo "  [Engine] Anthropic OK" >&2
            else
                echo "  Anthropic HTTP $http_code" >&2
                echo "  Anthropic error: $(echo "$body" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("error",{}).get("message","") or str(d)[:200])' 2>/dev/null)" >&2
            fi
        fi

        # ── Engine 4: Local Claude CLI ──────────────────────────────────────
        if [ -z "$result" ] && command -v claude &>/dev/null; then
            result=$(claude --model haiku -p --dangerously-skip-permissions "$(cat "$prompt_file")" 2>/dev/null | python3 -c "
import sys, re, json
text = sys.stdin.read().strip()
if text.startswith('\`\`\`json'): text = text[7:]
if text.startswith('\`\`\`'): text = text[3:]
if text.endswith('\`\`\`'): text = text[:-3]
text = text.strip()
text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
try:
    json.loads(text)
    print(text)
except Exception as e:
    print(f'CLI parse error: {e}', file=sys.stderr)
" 2>/dev/null || true)
            [ -n "$result" ] && echo "  [Engine] Claude CLI OK" >&2
        fi

        rm -f "$prompt_file"

        if [ -n "$result" ]; then
            break
        else
            echo "  Attempt $attempt: 모든 엔진 실패 — 10초 후 재시도" >&2
            sleep 10
        fi
    done

    if [ -z "$result" ]; then
        echo "ERROR: 모든 AI 엔진 실패 (Gemini/OpenAI/OpenRouter/Anthropic/CLI)" >&2
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

# Dashboard sanity check — runs only AFTER fetch-live-data.py has overwritten the
# numbers. It warns instead of failing: a provider outage must not block the edition.
validate_dashboard() {
    python3 -c "
import json, re, sys
data = json.load(open(sys.argv[1], encoding='utf-8'))
dash = data.get('dashboard', {})
rate = str(dash.get('php_krw_rate', ''))
if not re.match(r'^[0-9]{1,3}[.][0-9]{2}$', rate):
    print('  WARNING: php_krw_rate is not numeric: %r' % rate, file=sys.stderr)
for key in ('weather_kr', 'weather_en'):
    if 'C' not in str(dash.get(key, '')).replace(chr(176), 'C'):
        print('  WARNING: %s has no temperature: %r' % (key, dash.get(key)), file=sys.stderr)
print('  Dashboard: %s PHP/KRW | %s' % (rate, dash.get('weather_kr', '')))
" "$1"
}

# ─── Step 1: Generate Daily Content ─────────────────
echo "[1/4] Generating daily content..."

DAILY_PROMPT="You are a bilingual (English/Korean) news editor for ICAN Heralds, a premium daily news app for the Korean community in the Philippines.

Today is ${DAY_OF_WEEK}, ${DATE_DISPLAY}. Generate today's news edition for ${DATE}.

=== REAL HEADLINES FETCHED TODAY (${FETCH_STAMP} PHT) ===
These lines were fetched minutes ago from GMA News, Philstar, Rappler and Google News. They are your ONLY source of news facts today.

${NEWS_DIGEST}
=== END OF HEADLINES ===

GROUNDING RULES (these override every other instruction):
1. Every article you write must be built on one of the headlines above. Put that outlet's name in 'source_name'.
2. Copy the URL exactly into 'source_url' when the line shows one. When the line says '(headline only, no direct link)', set 'source_url' to an empty string.
3. Never invent statistics, percentages, prices, dates, people, quotes or URLs. If the headlines give no number, write no number.
4. If the headlines carry little Korea-Philippines news, choose the closest real Philippine story and explain what it means for Korean residents. Never invent an event.
5. Write like a careful newspaper editor: plain, specific, calm. No hype, no filler, no generic essays.
6. The dashboard numbers are already correct — copy '${PHP_KRW_RATE}' into php_krw_rate and leave the weather fields as written; they are replaced by live data afterwards anyway.

Return ONLY valid JSON (no markdown fences) with this exact structure:

{
  \"edition_date\": \"${DATE}\",
  \"header_date_line\": \"${HEADER_LINE}\",
  \"dashboard\": {
    \"php_krw_rate\": \"${PHP_KRW_RATE}\",
    \"weather_en\": \"29°C Cloudy\",
    \"weather_kr\": \"29°C 흐림\",
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
    \"source_name\": \"Outlet name exactly as listed above\",
    \"source_url\": \"https URL copied from the list, or empty string\",
    \"image_seed\": \"cover-${DATE}\",
    \"image_query\": \"3-8 word English phrase for AI image gen\",
    \"image_caption\": \"Photo: Description of the image (source, date)\",
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
    \"source_name\": \"Outlet name\",
    \"source_url\": \"URL or empty string\",
    \"image_seed\": \"feat-${DATE}\",
    \"image_query\": \"3-8 word English phrase for AI image gen matching the featured story\",
    \"desk\": \"Security Desk\",
    \"read_time_min\": 3
  },
  \"news_grid\": [
    {
      \"tag\": \"Economy\", \"tag_class\": \"tag-economy\",
      \"headline_en\": \"...\", \"headline_kr\": \"...\",
      \"summary_en\": \"1-2 sentence summary\", \"summary_kr\": \"...\",
      \"source_name\": \"Outlet name\", \"source_url\": \"URL or empty string\",
      \"image_seed\": \"news1-${DATE}\", \"image_query\": \"3-6 word English AI image prompt\", \"read_time_min\": 2
    },
    {
      \"tag\": \"Culture\", \"tag_class\": \"tag-culture\",
      \"headline_en\": \"...\", \"headline_kr\": \"...\",
      \"summary_en\": \"...\", \"summary_kr\": \"...\",
      \"source_name\": \"Outlet name\", \"source_url\": \"URL or empty string\",
      \"image_seed\": \"news2-${DATE}\", \"image_query\": \"3-6 word English AI image prompt\", \"read_time_min\": 2
    },
    {
      \"tag\": \"Cooperation\", \"tag_class\": \"tag-diplomacy\",
      \"headline_en\": \"...\", \"headline_kr\": \"...\",
      \"summary_en\": \"...\", \"summary_kr\": \"...\",
      \"source_name\": \"Outlet name\", \"source_url\": \"URL or empty string\",
      \"image_seed\": \"news3-${DATE}\", \"image_query\": \"3-6 word English AI image prompt\", \"read_time_min\": 3
    },
    {
      \"tag\": \"Safety\", \"tag_class\": \"tag-safety\",
      \"headline_en\": \"...\", \"headline_kr\": \"...\",
      \"summary_en\": \"...\", \"summary_kr\": \"...\",
      \"source_name\": \"Outlet name\", \"source_url\": \"URL or empty string\",
      \"image_seed\": \"news4-${DATE}\", \"image_query\": \"3-6 word English AI image prompt\", \"read_time_min\": 2
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
  },
  \"practice\": {
    \"det_question_en\": \"One Duolingo English Test style 1-minute essay question (agree/disagree or preference), tied to today's cover story and word of the day\",
    \"det_question_kr\": \"같은 질문의 한국어 버전\",
    \"det_structure_en\": \"How to answer in 60 seconds (4 short moves)\",
    \"det_structure_kr\": \"60초 답변 구조 (네 단계)\",
    \"det_link_en\": \"One sentence telling the learner which part of today's edition to use as evidence\",
    \"det_link_kr\": \"오늘 기사에서 근거로 쓸 부분 안내\"
  },
  \"knowledge_layer\": {
    \"tok_question_en\": \"An IB Theory of Knowledge knowledge question grounded in today's cover story (open-ended, starts with How / To what extent / What role does / Why)\",
    \"tok_question_kr\": \"같은 지식 질문의 한국어 버전\",
    \"aok_en\": \"Two Areas of Knowledge that fit best, e.g. 'Human Sciences · Natural Sciences'\",
    \"aok_kr\": \"지식 영역 한국어\",
    \"wok_en\": \"Two Ways of Knowing that fit best, e.g. 'Reason · Emotion'\",
    \"wok_kr\": \"인식 방법 한국어\",
    \"claim_en\": \"A knowledge claim a careful reader could defend from today's story\",
    \"claim_kr\": \"같은 지식 주장의 한국어\",
    \"counterclaim_en\": \"A serious counterclaim that complicates the first\",
    \"counterclaim_kr\": \"첫 주장을 흔드는 반대 주장의 한국어\",
    \"teded_keyword\": \"2-3 English words to search on TED-Ed (concrete concept from today's story)\",
    \"teded_why_en\": \"One sentence: what to look for in a TED-Ed lesson on this keyword\",
    \"teded_why_kr\": \"같은 안내의 한국어\",
    \"think_task_en\": \"A TED-Ed Think style critical-thinking task tied to today's story\",
    \"think_task_kr\": \"같은 과제의 한국어\",
    \"dig_deeper_en\": \"A TED-Ed Dig Deeper style research task (find a primary source)\",
    \"dig_deeper_kr\": \"같은 과제의 한국어\",
    \"essay_task_en\": \"TOK essay extension task (about 150 words) with AOK and WOK named\",
    \"essay_task_kr\": \"같은 과제의 한국어\",
    \"complex_dilemma\": {
      \"title_en\": \"Conundrum · Complex Problem-Solving\",
      \"title_kr\": \"Conundrum · 복합 난제 해결 과제\",
      \"scenario_en\": \"A realistic multi-stakeholder scenario (4-6 sentences) built from today's cover story: name the groups involved, what each one needs, and why those needs cannot all be met at once. Use only facts from the story — no invented statistics, names or quotes.\",
      \"scenario_kr\": \"오늘 커버 스토리에 근거한 복합 상황 설명 (4-6문장). 관련 집단, 각 집단이 원하는 것, 그것이 동시에 충족될 수 없는 이유를 담은 한국어.\",
      \"constraints\": [
        {\"en\": \"First competing constraint: one group's need that directly conflicts with another's\", \"kr\": \"첫 번째 상충 조건의 한국어\"},
        {\"en\": \"Second competing constraint: a limit such as time, budget, capacity or public trust\", \"kr\": \"두 번째 상충 조건의 한국어\"},
        {\"en\": \"Third competing constraint: the cost that falls on a third group if the other two are satisfied\", \"kr\": \"세 번째 상충 조건의 한국어\"}
      ],
      \"question_en\": \"An open-ended problem-solving question: design a concrete plan, weigh the trade-offs, and state what you would sacrifice and what you would protect first. It must not be answerable with yes or no.\",
      \"question_kr\": \"같은 과제 질문의 한국어 (해결안을 설계하고, 상충하는 가치 사이에서 무엇을 먼저 포기하고 무엇을 지킬지 근거와 함께 쓰게 하는 질문)\",
      \"evaluation_lens\": [
        {\"en\": \"Feasibility — can the plan actually be carried out with the people, money and time available?\", \"kr\": \"실현 가능성 — 가용한 사람·예산·시간으로 실제 실행할 수 있는가\"},
        {\"en\": \"Unintended consequences — who bears the cost of this choice, and what could go wrong?\", \"kr\": \"의도하지 않은 결과 — 이 선택의 비용은 누가 부담하며 무엇이 잘못될 수 있는가\"},
        {\"en\": \"Evidence and accountability — how would we know it worked, and who answers if it fails?\", \"kr\": \"근거와 책임 — 성과를 어떻게 확인하며 실패하면 누가 책임지는가\"}
      ]
    }
  }
}

IMPORTANT RULES:
- tag_class must be one of: tag-security, tag-economy, tag-culture, tag-diplomacy, tag-safety
- Focus on what the real headlines say: Korea-Philippines relations, Korean community life and safety in Metro Manila, Philippine economy, ASEAN, K-culture, Korean food events.
- Cover story body: 3 substantial paragraphs per language, each tied to a real headline.
- The word_of_day must appear meaningfully in the cover story.
- practice.det_question must be answerable from today's story in one minute; it must be a real DET-style prompt, not a TOK question.
- knowledge_layer.tok_question must be a genuine TOK knowledge question about knowledge itself (how we know), not a current-events question.
- knowledge_layer.complex_dilemma must be a dilemma, not a quiz. Build it only from facts in today's cover story, with two or three named stakeholder groups whose needs genuinely conflict, three competing constraints, one open-ended design question, and three evaluation criteria.
- The dilemma question must force a choice under scarcity and ask the learner to justify what they sacrifice and what they safeguard first. A single correct answer or a simple yes/no answer means the question has failed.
- knowledge_layer.complex_dilemma is shown to learners as a Conundrum card; keep its title exactly “Conundrum · Complex Problem-Solving” / “Conundrum · 복합 난제 해결 과제”.
- The dilemma scenario must never invent numbers, people, organisations or quotes. If the story gives no figure, the scenario names no figure.
- aok values must come from: Mathematics, Natural Sciences, Human Sciences, History, The Arts, Ethics. wok values from: Language, Sense perception, Emotion, Reason, Imagination, Faith, Intuition, Memory.
- teded_keyword: a searchable concept, never a fabricated lesson title or URL.
- Every Korean line must read like natural Korean written for learners, not machine translation.
- image_query: 3-8 concrete English nouns/actions describing the photo that would illustrate the article.
- Return ONLY valid JSON, no explanation"

DAILY_JSON=$(call_claude "$DAILY_PROMPT" 9000) || {
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

# ─── Step 1.5: Overwrite AI numbers with live data ─────
# The dashboard (FX rate + weather) and any source_url are re-checked here, so a
# hallucinated or stale number can never reach the published page.
echo "[1.5/5] Injecting live rate, weather and source checks..."
NEWS_CONTEXT="data/news-context-${DATE}.json"
if [ -f "$NEWS_CONTEXT" ]; then
    python3 scripts/fetch-live-data.py --json "data/daily-${DATE}.json" --news "$NEWS_CONTEXT" \
        || echo "  WARNING: live data enrichment failed — dashboard keeps the generated values"
else
    python3 scripts/fetch-live-data.py --json "data/daily-${DATE}.json" \
        || echo "  WARNING: live data enrichment failed — dashboard keeps the generated values"
fi
if ! validate_daily_json "$(cat "data/daily-${DATE}.json")"; then
    echo "ERROR: Daily JSON broken after live enrichment"
    exit 1
fi
validate_dashboard "data/daily-${DATE}.json" || true

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
    \"image_query\": \"3-8 words describing the signature dish and restaurant style, e.g. 'korean BBQ grilled galbi restaurant interior warm lighting'\",
    \"gallery_seeds\": [\"food-g1-w${CURRENT_WEEK}\", \"food-g2-w${CURRENT_WEEK}\", \"food-g3-w${CURRENT_WEEK}\"]
  },
  \"travel_cards\": [
    {
      \"image_seed\": \"travel1-w${CURRENT_WEEK}\",
      \"image_query\": \"3-8 words describing the destination visually, e.g. 'hidden blue lagoon cliff jumping tropical philippines'\",
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
      \"image_query\": \"3-8 words describing the destination visually\",
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
    {
      \"date_badge\": \"APR 18\",
      \"day_of_week_en\": \"Friday\", \"day_of_week_kr\": \"금요일\",
      \"image_seed\": \"event1-w${CURRENT_WEEK}\",
      \"image_query\": \"3-8 words describing the event visually, e.g. 'korean music concert stage lights crowd'\",
      \"title\": \"Event Name\",
      \"desc_en\": \"2-3 sentence vivid description\",
      \"desc_kr\": \"생생한 2-3문장 설명\",
      \"venue_en\": \"Exact venue name (e.g. Republiq Club & Lounge)\",
      \"venue_kr\": \"정확한 장소명\",
      \"address_en\": \"Full street address (e.g. 3/F Resorts World Manila, Newport Blvd, Pasay City)\",
      \"address_kr\": \"전체 도로명 주소\",
      \"time_en\": \"Doors 7:00 PM · Show 8:00 PM\",
      \"time_kr\": \"입장 오후 7시 · 공연 오후 8시\",
      \"price_en\": \"₱500 advance / ₱700 at door\",
      \"price_kr\": \"사전 ₱500 / 현장 ₱700\",
      \"contact\": \"@instagram_handle or phone number or booking URL\",
      \"note_en\": \"Any special note (e.g. Bring valid ID, Korean menu available)\",
      \"note_kr\": \"특별 참고사항\"
    },
    { \"date_badge\": \"MAY 05\", \"day_of_week_en\": \"Monday\", \"day_of_week_kr\": \"월요일\", \"image_seed\": \"event2-w${CURRENT_WEEK}\", \"image_query\": \"visual description\", \"title\": \"...\", \"desc_en\": \"...\", \"desc_kr\": \"...\", \"venue_en\": \"...\", \"venue_kr\": \"...\", \"address_en\": \"...\", \"address_kr\": \"...\", \"time_en\": \"...\", \"time_kr\": \"...\", \"price_en\": \"FREE\", \"price_kr\": \"무료\", \"contact\": \"...\", \"note_en\": \"...\", \"note_kr\": \"...\" },
    { \"date_badge\": \"JUN 12\", \"day_of_week_en\": \"Thursday\", \"day_of_week_kr\": \"목요일\", \"image_seed\": \"event3-w${CURRENT_WEEK}\", \"image_query\": \"visual description\", \"title\": \"...\", \"desc_en\": \"...\", \"desc_kr\": \"...\", \"venue_en\": \"...\", \"venue_kr\": \"...\", \"address_en\": \"...\", \"address_kr\": \"...\", \"time_en\": \"...\", \"time_kr\": \"...\", \"price_en\": \"...\", \"price_kr\": \"...\", \"contact\": \"...\", \"note_en\": \"...\", \"note_kr\": \"...\" },
    { \"date_badge\": \"JUL 20\", \"day_of_week_en\": \"Sunday\", \"day_of_week_kr\": \"일요일\", \"image_seed\": \"event4-w${CURRENT_WEEK}\", \"image_query\": \"visual description\", \"title\": \"...\", \"desc_en\": \"...\", \"desc_kr\": \"...\", \"venue_en\": \"...\", \"venue_kr\": \"...\", \"address_en\": \"...\", \"address_kr\": \"...\", \"time_en\": \"...\", \"time_kr\": \"...\", \"price_en\": \"...\", \"price_kr\": \"...\", \"contact\": \"...\", \"note_en\": \"...\", \"note_kr\": \"...\" }
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

Focus on Metro Manila (Makati, BGC, Ortigas, Quezon City). Make food reviews atmospheric and genuine — like a real food blogger who actually ate there.

EVENTS MUST include actionable details so readers can actually go:
- venue_en/kr: Exact venue name (not just area)
- address_en/kr: Full street address with building, floor, street, city
- time_en/kr: Door time and event time
- contact: Instagram handle, phone, or booking URL
- note_en/kr: Practical tips (ID required, parking info, Korean menu available, etc.)

Return ONLY valid JSON."

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
# 기사마다 L1 기초 · L2 맥락 · L3 실전 · L4 토론 네 레이어를 만든다.
# 여섯 기사를 한 번에 요청하면 출력이 잘려 JSON이 깨지고 L4가 통째로 빠지므로,
# 세 기사씩 두 번 불러 합친다(scripts/academy-merge.py).
echo "[2.5/5] Generating ICAN Academy knowledge layers (L1-L4)..."

rm -f "data/academy-${DATE}-part"*.json
ACADEMY_GROUPS=("cover,featured,news_1" "news_2,news_3,news_4")
ACADEMY_OK=0

for ACADEMY_GROUP in "${ACADEMY_GROUPS[@]}"; do
    ACADEMY_PART_NUM=$((ACADEMY_OK + 1))
    ACADEMY_PART_FILE="data/academy-${DATE}-part${ACADEMY_PART_NUM}.json"
    ACADEMY_PROMPT=$(python3 scripts/academy-prompt.py --date "$DATE" --keys "$ACADEMY_GROUP" 2>/dev/null) || ACADEMY_PROMPT=""
    if [ -z "$ACADEMY_PROMPT" ]; then
        echo "  WARNING: could not build the academy prompt for ${ACADEMY_GROUP}"
        continue
    fi
    ACADEMY_JSON=$(call_claude "$ACADEMY_PROMPT" 14000) || true
    if [ -n "${ACADEMY_JSON:-}" ]; then
        echo "$ACADEMY_JSON" > "$ACADEMY_PART_FILE"
        ACADEMY_OK=$((ACADEMY_OK + 1))
        echo "  academy part ${ACADEMY_PART_NUM} saved (${ACADEMY_GROUP})"
    else
        echo "  WARNING: academy generation failed for ${ACADEMY_GROUP}"
    fi
done

if [ "$ACADEMY_OK" -lt 2 ] && [ -s "data/academy-${DATE}.json" ]; then
    echo "  WARNING: only ${ACADEMY_OK}/2 academy groups generated — keeping the existing data/academy-${DATE}.json"
elif [ "$ACADEMY_OK" -gt 0 ]; then
    python3 scripts/academy-merge.py --date "$DATE" || echo "  WARNING: academy merge reported incomplete layers"
    python3 scripts/sync-academy.py --date "$DATE" || echo "  WARNING: academy sync reported incomplete layers"
else
    echo "  WARNING: Academy generation failed"
fi

# ─── Step 2.7: Article images (photoreal editorial photos) ────────────
# One matched photograph per main article → images/editions/<date>/ + data/image-manifest-<date>.json
# inject-direct.py then links the local file. Every provider is optional: if the whole
# step fails the edition still builds with keyword photos.
echo "[2.7/5] Building article images..."
if [ -f scripts/article-images.py ]; then
    python3 -c "import PIL" 2>/dev/null || pip install --quiet --disable-pip-version-check Pillow >/dev/null 2>&1 || true
    if timeout 600 python3 scripts/article-images.py --date "$DATE" 2>&1 | sed 's/^/  /'; then
        echo "  Article images ready"
    else
        echo "  WARNING: image pipeline failed — keyword-photo fallback stays in place"
    fi
else
    echo "  scripts/article-images.py missing — skipped"
fi

# ─── Step 3: Inject Content ─────────────────────────
echo "[3/5] Building HTML from data..."
python3 scripts/inject-direct.py

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

# Stage this edition's article images + manifest so the workflow's commit step picks
# them up (that step's own `git add` list has no images/, and .github/workflows cannot
# be edited from this connection — so staging happens here, before the commit).
if [ -d "images/editions/${DATE}" ]; then
    git add "images/editions/${DATE}" "data/image-manifest-${DATE}.json" 2>/dev/null || true
    IMG_COUNT=$(find "images/editions/${DATE}" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
    echo "Staged article images: ${IMG_COUNT} files (images/editions/${DATE})"
fi

echo ""
echo "=== Done! Edition: $DATE | $VOLUME_DISPLAY ==="
echo "Preview: open ican_news.html"
