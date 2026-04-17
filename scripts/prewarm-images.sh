#!/bin/bash
# Pre-warm Pollinations.ai image cache by requesting each URL from ican_news.html.
# Pollinations has slow cold starts (~30-60s) but caches results for 1 year.
# Running this after generation ensures users never hit cold generation.

set -uo pipefail
cd "$(dirname "$0")/.."

HTML="ican_news.html"
[ -f "$HTML" ] || { echo "ERROR: $HTML not found"; exit 1; }

URLS=$(grep -oE 'https://image\.pollinations\.ai/prompt/[^"]+' "$HTML" | sort -u)
TOTAL=$(echo "$URLS" | wc -l | tr -d ' ')
echo "Pre-warming $TOTAL unique Pollinations URLs in parallel (max 180s each)..."

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

warm_one() {
  local url="$1" idx="$2"
  local status
  status=$(curl -s "$url" -o /dev/null -w "%{http_code}:%{size_download}:%{time_total}" --max-time 180)
  local code=${status%%:*}
  local rest=${status#*:}
  local size=${rest%%:*}
  local time=${rest#*:}
  if [ "$code" = "200" ] && [ "$size" -gt 1000 ]; then
    echo "ok $idx ${size}B ${time}s" >> "$TMPDIR/results"
  else
    echo "fail $idx HTTP=$code size=$size" >> "$TMPDIR/results"
  fi
}

i=0
while IFS= read -r url; do
  i=$((i+1))
  warm_one "$url" "$i" &
done <<< "$URLS"
wait

ok=$(grep -c '^ok ' "$TMPDIR/results" 2>/dev/null || echo 0)
fail=$(grep -c '^fail ' "$TMPDIR/results" 2>/dev/null || echo 0)
cat "$TMPDIR/results" | sort -k2 -n
echo "Done: $ok ok, $fail failed"
[ "$fail" -eq 0 ] || exit 1
