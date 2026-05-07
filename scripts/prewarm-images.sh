#!/bin/bash
# Pre-warm Pollinations.ai image cache by requesting each URL from ican_news.html.
# Pollinations has slow cold starts (~30-60s) but caches results for 1 year.
# Running this after generation ensures users never hit cold generation.

set -uo pipefail
cd "$(dirname "$0")/.."

HTML="ican_news.html"
[ -f "$HTML" ] || { echo "ERROR: $HTML not found"; exit 1; }

URLS=$(python3 - "$HTML" <<'PY'
import re
import sys
from pathlib import Path

html = Path(sys.argv[1]).read_text(encoding="utf-8")
urls = []
for tag in re.findall(r'<img\b[^>]*>', html):
    m = re.search(r'(?:^|\s)src="(https://image\.pollinations\.ai/prompt/[^"]+)"', tag)
    if m:
        urls.append(m.group(1))

for url in sorted(set(urls)):
    print(url)
PY
)
if [ -z "${URLS//[[:space:]]/}" ]; then
  TOTAL=0
else
  TOTAL=$(printf '%s\n' "$URLS" | sed '/^$/d' | wc -l | tr -d ' ')
fi
echo "Pre-warming $TOTAL unique Pollinations URLs in parallel (max 180s each)..."

if [ "$TOTAL" -eq 0 ]; then
  echo "Done: 0 ok, 0 failed"
  exit 0
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

warm_one() {
  local url="$1" idx="$2"
  local status
  local attempt=1
  while [ "$attempt" -le 3 ]; do
    status=$(curl -s "$url" -o /dev/null -w "%{http_code}:%{size_download}:%{time_total}" --max-time 180)
    local code=${status%%:*}
    local rest=${status#*:}
    local size=${rest%%:*}
    local time=${rest#*:}
    if [ "$code" = "200" ] && [ "$size" -gt 1000 ]; then
      echo "ok $idx ${size}B ${time}s" >> "$TMPDIR/results"
      return 0
    fi
    if [ "$code" = "429" ] && [ "$attempt" -lt 3 ]; then
      sleep $((attempt * 5))
      attempt=$((attempt + 1))
      continue
    fi
    echo "fail $idx HTTP=$code size=$size" >> "$TMPDIR/results"
    return 1
  done
}

i=0
MAX_JOBS=4
while IFS= read -r url; do
    i=$((i+1))
    warm_one "$url" "$i" &
    while [ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$MAX_JOBS" ]; do
      sleep 1
    done
done <<< "$URLS"
wait

ok=$(grep -c '^ok ' "$TMPDIR/results" 2>/dev/null || echo 0)
fail=$(grep -c '^fail ' "$TMPDIR/results" 2>/dev/null || echo 0)
cat "$TMPDIR/results" | sort -k2 -n
echo "Done: $ok ok, $fail failed"
[ "$fail" -eq 0 ] || exit 1
