#!/usr/bin/env python3
"""Merge the Academy reply groups into data/academy-<date>.json.

generate-daily.sh asks the model for the layers in two groups and saves each raw
reply in data/academy-<date>-part<N>.json. This script merges them into
data/academy-<date>.json, then reports which article is still missing a layer
before the edition is built.

Usage:
    python3 scripts/academy-merge.py --date 2026-11-27
"""
import argparse
import glob
import json
import os
import re
import sys

REQUIRED_DEPTHS = [1, 2, 3, 4]
ARTICLE_KEYS = ["cover", "featured", "news_1", "news_2", "news_3", "news_4"]


def parse_reply(path):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", raw)
    if not raw.strip().startswith("{"):
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start:end + 1]
    return json.loads(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()

    parts = sorted(glob.glob(f"data/academy-{args.date}-part*.json"))
    if not parts:
        print(f"ERROR: no data/academy-{args.date}-part*.json replies to merge", file=sys.stderr)
        return 1

    merged = {}
    for path in parts:
        try:
            data = parse_reply(path)
        except Exception as exc:
            print(f"  WARNING: {os.path.basename(path)} unreadable ({exc}) — skipped", file=sys.stderr)
            continue
        for key, value in data.items():
            if not isinstance(value, dict) or not isinstance(value.get("layers"), list):
                continue
            merged[key] = value
        print(f"  merged {os.path.basename(path)} ({len(data)} articles)")

    if not merged:
        print("ERROR: every academy reply was unreadable", file=sys.stderr)
        return 1

    for key in merged:
        layers = merged[key].get("layers") or []
        merged[key]["layers"] = sorted(layers, key=lambda l: int(l.get("depth", 0) or 0))

    target = f"data/academy-{args.date}.json"
    with open(target, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        f.write("\n")

    short = []
    for key in ARTICLE_KEYS:
        if key not in merged:
            short.append(f"{key}: missing article")
            continue
        have = {int(l.get("depth", 0) or 0) for l in merged[key]["layers"]}
        missing = [d for d in REQUIRED_DEPTHS if d not in have]
        if missing:
            short.append(f"{key}: no L{', L'.join(str(m) for m in missing)}")
    print(f"  wrote {target} ({len(merged)} articles)")
    if short:
        print("  WARNING: " + "; ".join(short), file=sys.stderr)
        return 2
    print("  Layers OK: every article has L1-L4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
