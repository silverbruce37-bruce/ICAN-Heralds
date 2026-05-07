#!/bin/bash
# Pre-warm local image cache by downloading article image URLs from ican_news.html.
# The HTML may still reference remote Unsplash / Pollinations sources, but once
# cached they are rewritten on the next inject pass to use local files first.

set -uo pipefail
cd "$(dirname "$0")/.."

HTML="ican_news.html"
[ -f "$HTML" ] || { echo "ERROR: $HTML not found"; exit 1; }

mkdir -p images/cache

URLS=$(python3 - "$HTML" <<'PY'
import re
import sys
import hashlib
from pathlib import Path

html = Path(sys.argv[1]).read_text(encoding="utf-8")
items = []

def cache_path(url):
    key = hashlib.md5(url.encode("utf-8")).hexdigest()[:16]
    return f"images/cache/{key}.jpg"

for tag in re.findall(r'<img\b[^>]*>', html):
    src = re.search(r'(?:^|\s)src="([^"]+)"', tag)
    sec = re.search(r'data-secondary-src="([^"]+)"', tag)
    fb = re.search(r'data-fallback-src="([^"]+)"', tag)
    cache = re.search(r'data-cache-path="([^"]+)"', tag)
    for m in (src, sec, fb):
        if not m:
            continue
        url = m.group(1)
        if not url.startswith("http"):
            continue
        items.append((url, cache.group(1) if cache and m is src else cache_path(url)))

for url, path in sorted(set(items)):
    print(f"{url}\t{path}")
PY
)
if [ -z "${URLS//[[:space:]]/}" ]; then
  TOTAL=0
else
  TOTAL=$(printf '%s\n' "$URLS" | sed '/^$/d' | wc -l | tr -d ' ')
fi
echo "Pre-warming $TOTAL unique image URLs in parallel (max 180s each)..."

if [ "$TOTAL" -eq 0 ]; then
  echo "Done: 0 ok, 0 failed"
  exit 0
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT
FAIL_FILE="$TMPDIR/failures"

warm_one() {
  local url="$1" path="$2" idx="$3"
  local status
  local attempt=1
  while [ "$attempt" -le 4 ]; do
    mkdir -p "$(dirname "$path")"
    status=$(curl -L -s "$url" -o "$path.tmp" -w "%{http_code}:%{size_download}:%{time_total}" --max-time 180)
    local code=${status%%:*}
    local rest=${status#*:}
    local size=${rest%%:*}
    local time=${rest#*:}
    if [ "$code" = "200" ] && [ "$size" -gt 1000 ]; then
      mv "$path.tmp" "$path"
      echo "ok $idx ${size}B ${time}s" >> "$TMPDIR/results"
      return 0
    fi
    if [ "$code" = "429" ] && [ "$attempt" -lt 4 ]; then
      rm -f "$path.tmp"
      sleep $((attempt * 8))
      attempt=$((attempt + 1))
      continue
    fi
    rm -f "$path.tmp"
    printf '%s\t%s\t%s\n' "$url" "$path" "$idx" >> "$FAIL_FILE"
    return 1
  done
}

i=0
MAX_JOBS=4
while IFS=$'\t' read -r url path; do
    i=$((i+1))
    if [ -f "$path" ]; then
      echo "skip $i cached $path" >> "$TMPDIR/results"
      continue
    fi
    warm_one "$url" "$path" "$i" &
    while [ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$MAX_JOBS" ]; do
      sleep 1
    done
done <<< "$URLS"
wait

if [ -s "$FAIL_FILE" ]; then
  echo "Retrying failed image URLs sequentially..."
  while IFS=$'\t' read -r url path idx; do
    [ -n "$url" ] || continue
    [ -f "$path" ] && continue
    warm_one "$url" "$path" "$idx" || true
    sleep 3
  done < "$FAIL_FILE"
fi

if [ -s "$FAIL_FILE" ]; then
  while IFS=$'\t' read -r url path idx; do
    [ -n "$url" ] || continue
    if [ -f "$path" ] && [ "$(stat -f%z "$path" 2>/dev/null || stat -c%s "$path" 2>/dev/null || echo 0)" -gt 1000 ]; then
      continue
    fi
    echo "fail $idx HTTP=retry-exhausted size=0" >> "$TMPDIR/results"
  done < "$FAIL_FILE"
fi

ok=$(grep -c '^ok ' "$TMPDIR/results" 2>/dev/null || echo 0)
fail=$(grep -c '^fail ' "$TMPDIR/results" 2>/dev/null || echo 0)
cat "$TMPDIR/results" | sort -k2 -n
echo "Done: $ok ok, $fail failed"
[ "$fail" -eq 0 ] || exit 1
