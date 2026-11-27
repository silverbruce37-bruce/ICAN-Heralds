#!/usr/bin/env python3
"""Print the ICAN Academy knowledge-layer prompt for one group of articles.

generate-daily.sh calls this twice (cover+featured+news_1, news_2..news_4) so a
single reply never has to carry all six articles' four layers at once — the
truncated reply used to be the reason whole editions shipped without L4.

Usage:
    python3 scripts/academy-prompt.py --date 2026-11-27 --keys cover,featured,news_1
"""
import argparse
import json
from string import Template

TEMPLATE = Template("""You are an educational content designer for ICAN Academy, part of ICAN Heralds.
Given today's news articles, generate background knowledge layers for bilingual (Korean/English) smart 14-year-old learners.

Today's articles (from daily JSON):
$articles

Generate knowledge layers for EACH article listed above. Use exactly these article keys: $keys
Return ONLY valid JSON (no markdown fences):

{
  "$first_key": {
    "layers": [
      {
        "depth": 1, "title_en": "Foundation title", "title_kr": "기초 개념 제목",
        "sub_en": "Foundation", "sub_kr": "기초 개념", "badge": "Beginner",
        "text_en": "Simple explanation (3-5 sentences). Use <span class=kw>key terms</span>.",
        "text_kr": "<span class=kw>핵심 용어</span>가 포함된 쉬운 설명 (3-5문장).",
        "bilingual_en": "Aha-moment sentence in English",
        "bilingual_kr": "핵심 요약 한국어",
        "speaking_en": "One short speaking task tied to this exact layer.",
        "speaking_kr": "이 레이어에 딱 맞는 짧은 말하기 과제.",
        "writing_en": "One short writing task tied to this exact layer.",
        "writing_kr": "이 레이어에 딱 맞는 짧은 쓰기 과제.",
        "vocab": [{"en": "term", "kr": "용어"}]
      },
      {
        "depth": 2, "title_en": "Context & Why it matters", "title_kr": "맥락과 중요성",
        "sub_en": "Context", "sub_kr": "맥락", "badge": "Intermediate",
        "text_en": "Deeper context...", "text_kr": "더 깊은 맥락...",
        "bilingual_en": "...", "bilingual_kr": "...",
        "speaking_en": "Layer-specific speaking task.", "speaking_kr": "레이어 맞춤 말하기 과제.",
        "writing_en": "Layer-specific writing task.", "writing_kr": "레이어 맞춤 쓰기 과제.",
        "vocab": [{"en": "term", "kr": "용어"}],
        "quiz": {
          "q_en": "Question?", "q_kr": "질문?",
          "opts": [
            {"en": "Wrong", "kr": "오답", "correct": false},
            {"en": "Correct", "kr": "정답", "correct": true},
            {"en": "Wrong", "kr": "오답", "correct": false}
          ]
        }
      },
      {
        "depth": 3, "title_en": "Impact for Koreans in PH", "title_kr": "필리핀 한인 사회 영향",
        "sub_en": "Application", "sub_kr": "실생활 적용", "badge": "Advanced",
        "text_en": "Practical implications...", "text_kr": "실질적 시사점...",
        "bilingual_en": "...", "bilingual_kr": "...",
        "speaking_en": "Layer-specific speaking task.", "speaking_kr": "레이어 맞춤 말하기 과제.",
        "writing_en": "Layer-specific writing task.", "writing_kr": "레이어 맞춤 쓰기 과제.",
        "vocab": [{"en": "term", "kr": "용어"}]
      },
      {
        "depth": 4, "title_en": "Debate & Insight", "title_kr": "토론과 통찰",
        "sub_en": "Insight", "sub_kr": "심화", "badge": "Expert",
        "text_en": "Higher-level perspective connected to the article.", "text_kr": "기사와 연결된 심화 관점 설명.",
        "bilingual_en": "...", "bilingual_kr": "...",
        "speaking_en": "State your position aloud.", "speaking_kr": "자신의 입장을 말해보세요.",
        "writing_en": "Write a short opinion paragraph.", "writing_kr": "짧은 의견 단락을 써보세요.",
        "debate_en": "A discussion prompt tied to this specific article.",
        "debate_kr": "이 기사에 맞춘 토론 질문.",
        "vocab": [{"en": "term", "kr": "용어"}]
      }
    ],
    "suggestions_en": ["Q1?", "Q2?", "Q3?"],
    "suggestions_kr": ["질문1?", "질문2?", "질문3?"],
    "tok": {
      "question_en": "IB TOK knowledge question about how we know, drawn from THIS article",
      "question_kr": "같은 지식 질문의 한국어",
      "aok_en": "One or two Areas of Knowledge (Mathematics, Natural Sciences, Human Sciences, History, The Arts, Ethics)",
      "aok_kr": "지식 영역 한국어",
      "wok_en": "One or two Ways of Knowing (Language, Sense perception, Emotion, Reason, Imagination, Faith, Intuition, Memory)",
      "wok_kr": "인식 방법 한국어",
      "task_en": "A short critical-thinking task: test one claim in this article against a counter-example",
      "task_kr": "같은 과제의 한국어"
    }
  }
}

RULES:
- EVERY article MUST have exactly four layers: depth 1, 2, 3 and 4. An article with three layers is a failed answer, because the site's Level 4 button then has nothing to open.
- Layer 3 MUST focus on the Korean community living in the Philippines.
- Layer 4 MUST be an article-specific debate/insight layer that includes 'debate_en' and 'debate_kr'.
- Layer 2 SHOULD include a short 'quiz' with exactly one correct option.
- Every article MUST include a 'tok' object: one genuine TOK knowledge question about how we come to know something in this story, with AOK and WOK values chosen from the official lists, and a short critical-thinking task. Never repeat the same tok question across articles in this edition.
- Every layer MUST include 'speaking_en/kr' and 'writing_en/kr', and they must be specific to that article layer.
- Korean 'speaking_kr' and 'writing_kr' MUST read like workbook prompts for learners. Prefer endings such as '-해 봅시다', '-정리해 봅시다', '-써 봅시다' over explanatory prose.
- Use natural Korean (not AI-translated style).
- Write for a smart 14-year-old.
- Return ONLY valid JSON. Do not repeat the article headlines outside the layers.""")

ARTICLE_KEYS = ["cover", "featured", "news_1", "news_2", "news_3", "news_4"]


def describe(daily, key):
    if key == "cover":
        art = daily.get("cover_story", {})
        return f"COVER: {art.get('headline_en', '')}\n  {art.get('subtitle_en', '')}"
    if key == "featured":
        art = daily.get("featured_news", {})
        return f"FEATURED: {art.get('headline_en', '')}\n  {art.get('lead_en', '')}"
    idx = int(key.split("_")[1]) - 1
    news = daily.get("news_grid", [])
    if idx < len(news):
        art = news[idx]
        return (f"NEWS_{idx + 1}: [{art.get('tag', 'News')}] {art.get('headline_en', '')}\n"
                f"  {art.get('summary_en', '')}")
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--keys", required=True)
    args = ap.parse_args()

    keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    with open(f"data/daily-{args.date}.json", encoding="utf-8") as f:
        daily = json.load(f)

    articles = "\n".join(describe(daily, k) for k in keys if k in ARTICLE_KEYS)
    print(TEMPLATE.substitute(
        articles=articles,
        keys=", ".join(keys),
        first_key=keys[0],
    ))


if __name__ == "__main__":
    main()
