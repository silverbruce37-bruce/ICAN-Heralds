#!/usr/bin/env python3
"""ICAN Heralds — live data enrichment for the daily edition.

Runs AFTER the AI has produced data/daily-<date>.json and BEFORE the HTML build,
so the dashboard can never show invented numbers.

  1. PHP -> KRW exchange rate  (open.er-api.com -> frankfurter -> Naver Finance)
  2. Pasig / Metro Manila weather (Open-Meteo -> MET Norway, WMO/symbol codes
     mapped to Korean + English labels)
  3. Source guard: keeps cover_story/featured_news/news_grid `source_url` only
     when the URL was actually returned by the RSS fetcher (no fake links)
  4. Learning layer guard: fills any missing DET / TED-Ed / TOK fields with a
     deterministic fallback so the practice sections always render.
  5. Dilemma guard: keeps knowledge_layer.complex_dilemma complete (story-
     grounded scenario, competing constraints, open question, evaluation lens)
     so the STEP 03 complex problem-solving challenge always renders.

Usage:
    python3 scripts/fetch-live-data.py --json data/daily-2026-11-26.json \
        [--news data/news-context-2026-11-26.json] [--dry-run]

Exit code is always 0 when the JSON stays valid: a network failure must never
kill the daily publication. What failed is reported on stderr.
"""

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

PHT = timezone(timedelta(hours=8))
PASIG_LAT = 14.5764
PASIG_LON = 121.0851
USER_AGENT = "ICAN-Heralds/2.0 (+https://ican-heralds.vercel.app)"
TIMEOUT = 12

# ── Weather code → label maps ────────────────────────────────────────────────
WMO_LABELS = {
    0: ("Clear", "맑음"),
    1: ("Mainly Clear", "대체로 맑음"),
    2: ("Partly Cloudy", "구름 조금"),
    3: ("Cloudy", "흐림"),
    45: ("Fog", "안개"),
    48: ("Freezing Fog", "서리 안개"),
    51: ("Light Drizzle", "약한 이슬비"),
    53: ("Drizzle", "이슬비"),
    55: ("Heavy Drizzle", "강한 이슬비"),
    56: ("Freezing Drizzle", "어는 이슬비"),
    57: ("Heavy Freezing Drizzle", "강한 어는 이슬비"),
    61: ("Light Rain", "약한 비"),
    63: ("Rain", "비"),
    65: ("Heavy Rain", "강한 비"),
    66: ("Freezing Rain", "어는 비"),
    67: ("Heavy Freezing Rain", "강한 어는 비"),
    71: ("Light Snow", "약한 눈"),
    73: ("Snow", "눈"),
    75: ("Heavy Snow", "강한 눈"),
    77: ("Snow Grains", "싸락눈"),
    80: ("Light Showers", "약한 소나기"),
    81: ("Showers", "소나기"),
    82: ("Heavy Showers", "강한 소나기"),
    85: ("Snow Showers", "눈 소나기"),
    86: ("Heavy Snow Showers", "강한 눈 소나기"),
    95: ("Thunderstorm", "천둥번개"),
    96: ("Thunderstorm with Hail", "우박 동반 천둥번개"),
    99: ("Severe Thunderstorm with Hail", "강한 우박 동반 천둥번개"),
}

METNO_LABELS = {
    "clearsky": ("Clear", "맑음"),
    "fair": ("Mainly Clear", "대체로 맑음"),
    "partlycloudy": ("Partly Cloudy", "구름 조금"),
    "cloudy": ("Cloudy", "흐림"),
    "fog": ("Fog", "안개"),
    "lightrain": ("Light Rain", "약한 비"),
    "lightrainshowers": ("Light Showers", "약한 소나기"),
    "rain": ("Rain", "비"),
    "rainshowers": ("Showers", "소나기"),
    "heavyrain": ("Heavy Rain", "강한 비"),
    "heavyrainshowers": ("Heavy Showers", "강한 소나기"),
    "lightsleet": ("Light Sleet", "약한 진눈깨비"),
    "sleet": ("Sleet", "진눈깨비"),
    "heavysleet": ("Heavy Sleet", "강한 진눈깨비"),
    "lightsnow": ("Light Snow", "약한 눈"),
    "snow": ("Snow", "눈"),
    "heavysnow": ("Heavy Snow", "강한 눈"),
    "rainandthunder": ("Rain and Thunder", "비와 천둥번개"),
    "rainshowersandthunder": ("Showers and Thunder", "소나기와 천둥번개"),
    "sleetandthunder": ("Sleet and Thunder", "진눈깨비와 천둥번개"),
    "snowandthunder": ("Snow and Thunder", "눈과 천둥번개"),
}


def log(msg):
    print(msg, file=sys.stderr)


def _get(url, timeout=TIMEOUT, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get_json(url, timeout=TIMEOUT):
    return json.loads(_get(url, timeout=timeout).decode("utf-8", "replace"))


# ── 1. Exchange rate ────────────────────────────────────────────────────────
def _fx_open_er_api():
    data = _get_json("https://open.er-api.com/v6/latest/PHP")
    if data.get("result") != "success":
        raise ValueError("open.er-api result=%s" % data.get("result"))
    rate = data["rates"]["KRW"]
    return float(rate), "exchangerate-api.com"


def _fx_frankfurter():
    data = _get_json("https://api.frankfurter.dev/v1/latest?base=PHP&symbols=KRW")
    rate = data["rates"]["KRW"]
    return float(rate), "frankfurter.dev (ECB)"


def _fx_naver():
    raw = _get(
        "https://finance.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_PHPKRW",
        headers={"Referer": "https://finance.naver.com/"},
    )
    html = raw.decode("euc-kr", "replace")
    idx = html.find("no_today")
    if idx < 0:
        raise ValueError("naver: no_today block not found")
    snippet = html[idx:idx + 800]
    digits = re.findall(r'class="no(\d)">(\d)</span>|class="jum">(\.)</span>', snippet)
    value = "".join((d[1] or d[2]) for d in digits)
    if not value or not re.match(r"^\d+(\.\d+)?$", value):
        raise ValueError("naver: could not parse rate")
    return float(value), "Naver Finance"


def fetch_rate():
    for name, fn in (
        ("open.er-api", _fx_open_er_api),
        ("frankfurter", _fx_frankfurter),
        ("naver", _fx_naver),
    ):
        try:
            value, source = fn()
            if 10.0 <= value <= 60.0:  # sanity band for PHP/KRW
                return round(value, 2), source
            log("  [rate] %s returned implausible %.2f — next provider" % (name, value))
        except Exception as exc:  # noqa: BLE001 - provider chain
            log("  [rate] %s failed: %s" % (name, exc))
    return None, None


# ── 2. Weather ──────────────────────────────────────────────────────────────
def _metno_code(symbol):
    base = str(symbol or "").split("_")[0].lower()
    if base in METNO_LABELS:
        return METNO_LABELS[base]
    if "thunder" in base:
        return ("Thunderstorm", "천둥번개")
    if "snow" in base:
        return ("Snow", "눈")
    if "sleet" in base:
        return ("Sleet", "진눈깨비")
    if "rain" in base:
        return ("Rain", "비")
    return ("Cloudy", "흐림")


def _weather_open_meteo():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=%.4f&longitude=%.4f"
        "&current=temperature_2m,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&timezone=Asia%%2FManila" % (PASIG_LAT, PASIG_LON)
    )
    data = _get_json(url, timeout=10)
    current = data["current"]
    temp = float(current["temperature_2m"])
    code = int(current["weather_code"])
    label_en, label_kr = WMO_LABELS.get(code, ("Cloudy", "흐림"))
    daily = data.get("daily") or {}
    return {
        "temp": temp,
        "label_en": label_en,
        "label_kr": label_kr,
        "code": "wmo:%d" % code,
        "source": "Open-Meteo",
        "tmax": (daily.get("temperature_2m_max") or [None])[0],
        "tmin": (daily.get("temperature_2m_min") or [None])[0],
        "pop": (daily.get("precipitation_probability_max") or [None])[0],
    }


def _weather_metno():
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=%.4f&lon=%.4f" % (
        PASIG_LAT,
        PASIG_LON,
    )
    data = _get_json(url, timeout=12)
    series = data["properties"]["timeseries"]
    now = datetime.now(timezone.utc)
    best = None
    for entry in series[:8]:
        stamp = entry.get("time")
        if not stamp:
            continue
        try:
            t = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if best is None or abs((t - now).total_seconds()) < abs((best[0] - now).total_seconds()):
            best = (t, entry)
    if best is None:
        raise ValueError("met.no: empty timeseries")
    entry = best[1]
    details = entry["data"]["instant"]["details"]
    temp = float(details["air_temperature"])
    summary = entry["data"].get("next_1_hours", {}).get("summary", {}).get("symbol_code")
    label_en, label_kr = _metno_code(summary)
    # daily-ish high/low from the next 24 hours of entries
    temps = []
    for entry2 in series[:24]:
        try:
            temps.append(float(entry2["data"]["instant"]["details"]["air_temperature"]))
        except (KeyError, TypeError, ValueError):
            continue
    return {
        "temp": temp,
        "label_en": label_en,
        "label_kr": label_kr,
        "code": "metno:%s" % (summary or ""),
        "source": "MET Norway",
        "tmax": round(max(temps), 1) if temps else None,
        "tmin": round(min(temps), 1) if temps else None,
        "pop": None,
    }


def fetch_weather():
    for name, fn in (("open-meteo", _weather_open_meteo), ("met.no", _weather_metno)):
        try:
            data = fn()
            if -10.0 <= data["temp"] <= 55.0:
                return data
            log("  [weather] %s returned implausible %.1f°C — next provider" % (name, data["temp"]))
        except Exception as exc:  # noqa: BLE001 - provider chain
            log("  [weather] %s failed: %s" % (name, exc))
    return None


# ── 3. Dashboard application ────────────────────────────────────────────────
def apply_dashboard(daily, rate, rate_source, weather):
    dash = daily.setdefault("dashboard", {})
    changed = []

    if rate is not None:
        dash["php_krw_rate"] = "%.2f" % rate
        dash["rate_source_en"] = "via %s" % rate_source
        dash["rate_source_kr"] = "%s 기준" % rate_source
        changed.append("rate=%s" % dash["php_krw_rate"])
    else:
        log("  [rate] all providers failed — keeping existing value %r" % dash.get("php_krw_rate"))

    if weather is not None:
        temp = int(round(weather["temp"]))
        dash["weather_en"] = "%d°C %s" % (temp, weather["label_en"])
        dash["weather_kr"] = "%d°C %s" % (temp, weather["label_kr"])
        dash["weather_code"] = weather["code"]
        dash["weather_source"] = weather["source"]
        if weather.get("tmax") is not None and weather.get("tmin") is not None:
            dash["weather_range_en"] = "High %d° / Low %d°" % (
                int(round(weather["tmax"])),
                int(round(weather["tmin"])),
            )
            dash["weather_range_kr"] = "최고 %d° / 최저 %d°" % (
                int(round(weather["tmax"])),
                int(round(weather["tmin"])),
            )
        if weather.get("pop") is not None:
            dash["weather_pop"] = int(round(weather["pop"]))
        changed.append("weather=%s" % dash["weather_kr"])
    else:
        log("  [weather] all providers failed — keeping existing value %r" % dash.get("weather_kr"))

    date_str = daily.get("edition_date") or datetime.now(PHT).strftime("%Y-%m-%d")
    dash["date"] = date_str.replace("-", ".")
    dash["date_iso"] = date_str
    dash["updated_at_pht"] = datetime.now(PHT).strftime("%Y-%m-%d %H:%M PHT")
    return changed


# ── 4. Source guard ─────────────────────────────────────────────────────────
def allowed_urls_from_news(path):
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        log("  [sources] could not read %s: %s" % (path, exc))
        return set()
    urls = set()
    for item in payload.get("items", []):
        link = (item.get("link") or "").strip()
        if link.startswith("http") and "news.google.com" not in link:
            urls.add(link)
    return urls


def _clean_source(container, allowed):
    """Drop a source_url/source_name pair the RSS fetcher did not actually return."""
    url = (container.get("source_url") or "").strip()
    name = (container.get("source_name") or "").strip()
    if not url:
        container.pop("source_url", None)
        if name:
            container.pop("source_name", None)
        return
    if not allowed:
        container.pop("source_url", None)
        container.pop("source_name", None)
        log("  [sources] no RSS list — dropped %s" % url[:80])
        return
    if url not in allowed:
        container.pop("source_url", None)
        container.pop("source_name", None)
        log("  [sources] dropped unverified URL: %s" % url[:100])


def apply_source_guard(daily, allowed):
    count = 0
    for key in ("cover_story", "featured_news"):
        if isinstance(daily.get(key), dict):
            _clean_source(daily[key], allowed)
            if daily[key].get("source_url"):
                count += 1
    for item in daily.get("news_grid", []) or []:
        if isinstance(item, dict):
            _clean_source(item, allowed)
            if item.get("source_url"):
                count += 1
    return count


# ── 5. Learning layer guard (DET / TED-Ed / TOK) ────────────────────────────
TOK_QUESTIONS = [
    {
        "en": "How do we know whether what we read about {topic} is reliable, and who decides?",
        "kr": "{topic}에 대해 우리가 읽은 것이 신뢰할 만한지 어떻게 알 수 있으며, 그것을 누가 결정하는가?",
    },
    {
        "en": "To what extent does language shape the way a community understands {topic}?",
        "kr": "언어는 공동체가 {topic}을(를) 이해하는 방식을 어느 정도까지 형성하는가?",
    },
    {
        "en": "What role does emotion play in how people respond to {topic}, and should it play that role?",
        "kr": "사람들이 {topic}에 반응할 때 감정은 어떤 역할을 하며, 그 역할은 정당한가?",
    },
    {
        "en": "How might two Areas of Knowledge explain the same claim about {topic} differently?",
        "kr": "서로 다른 두 지식 영역은 {topic}에 대한 같은 주장을 어떻게 다르게 설명할 수 있는가?",
    },
    {
        "en": "When is authority a reliable source of knowledge about {topic}?",
        "kr": "{topic}에 관한 지식의 원천으로서 권위는 언제 신뢰할 수 있는가?",
    },
]

DET_QUESTIONS = [
    {
        "en": "Some people say that being prepared matters more than being optimistic. Do you agree or disagree?",
        "kr": "준비된 사람이 되는 것이 낙관적인 태도를 갖는 것보다 중요하다고 말하는 사람들이 있습니다. 동의하십니까?",
    },
    {
        "en": "Some people believe that communities are strongest when information is shared openly. Do you agree or disagree?",
        "kr": "정보가 공개적으로 공유될 때 공동체가 가장 강해진다고 믿는 사람들이 있습니다. 동의하십니까?",
    },
    {
        "en": "Some people think it is better to rely on official sources than on personal experience. Do you agree or disagree?",
        "kr": "개인적 경험보다 공식 자료에 의존하는 편이 낫다고 생각하는 사람들이 있습니다. 동의하십니까?",
    },
    {
        "en": "Some people say that learning a language changes the way you think. Do you agree or disagree?",
        "kr": "언어를 배우면 사고방식이 달라진다고 말하는 사람들이 있습니다. 동의하십니까?",
    },
]


def _hash_index(text, size):
    total = sum(ord(ch) for ch in str(text))
    return total % max(size, 1)


def _topic_phrase(daily):
    cover = daily.get("cover_story", {}) or {}
    word = (daily.get("word_of_day", {}) or {}).get("word", "").strip()
    headline = (cover.get("headline_en") or "").strip()
    if word and headline:
        return "%s in today's story" % word.lower() if len(word) < 24 else headline
    return headline or word or "today's news"


# ── 5b. Complex problem-solving dilemma ─────────────────────────────────────
# The daily prompt asks the AI for knowledge_layer.complex_dilemma. When the
# model omits it (or returns a half-built object), this builds a story-grounded
# dilemma from today's cover story so STEP 03 always carries the challenge.
DILEMMA_CONSTRAINTS = [
    {
        "en": "Time and certainty — a decision is expected before all the evidence is in.",
        "kr": "시간과 확실성 — 모든 근거가 확인되기 전에 결정을 내려야 합니다.",
    },
    {
        "en": "Cost and fairness — every option spends money, staff or attention that another group also needs.",
        "kr": "비용과 공정성 — 어떤 선택이든 다른 집단도 필요로 하는 돈, 인력, 관심을 쓰게 됩니다.",
    },
    {
        "en": "Trust and accountability — the people affected judge the decision by how openly it is explained and reviewed.",
        "kr": "신뢰와 책임 — 영향을 받는 사람들은 결정이 얼마나 투명하게 설명되고 점검되는지로 판단합니다.",
    },
]

DILEMMA_LENS = [
    {
        "en": "Feasibility — can the plan actually be carried out with the people, money and time available?",
        "kr": "실현 가능성 — 가용한 사람·예산·시간으로 실제 실행할 수 있는가",
    },
    {
        "en": "Unintended consequences — who bears the cost of this choice, and what could go wrong?",
        "kr": "의도하지 않은 결과 — 이 선택의 비용은 누가 부담하며 무엇이 잘못될 수 있는가",
    },
    {
        "en": "Evidence and accountability — how would we know it worked, and who answers if it fails?",
        "kr": "근거와 책임 — 성과를 어떻게 확인하며 실패하면 누가 책임지는가",
    },
]


def _bilingual(value):
    """Read a string or an {en, kr} object as a bilingual pair."""
    if isinstance(value, dict):
        en = str(value.get("en") or value.get("text_en") or "").strip()
        kr = str(value.get("kr") or value.get("text_kr") or "").strip()
        return en, (kr or en)
    text = str(value or "").strip()
    return text, text


def _same_dimension(left, right):
    """True when two criteria open with the same keyword (Feasibility, Trust …)."""
    def head(item):
        text = str(item.get("en") or "").lower()
        for dash in (" — ", " - ", " – ", ":"):
            text = text.split(dash)[0]
        return text.strip()
    a, b = head(left), head(right)
    return bool(a) and bool(b) and (a == b or a.startswith(b) or b.startswith(a))


def _bilingual_list(value, defaults, minimum=2):
    """Normalise a list of strings or {en, kr} objects and pad short lists."""
    out = []
    for item in value if isinstance(value, list) else []:
        en, kr = _bilingual(item)
        if en or kr:
            out.append({"en": en or kr, "kr": kr or en})
    if not out:
        return [dict(default) for default in defaults[:3]]
    for default in defaults:
        if len(out) >= minimum:
            break
        if not any(_same_dimension(default, existing) for existing in out):
            out.append(dict(default))
    return out


def ensure_complex_dilemma(layer, daily, topic_en, topic_kr):
    """Guarantee a complete, story-grounded complex_dilemma object."""
    cover = daily.get("cover_story", {}) or {}
    headline_en = (cover.get("headline_en") or "").strip() or "today's story"
    headline_kr = (cover.get("headline_kr") or "").strip() or topic_kr
    subtitle_en = (cover.get("subtitle_en") or "").strip()
    subtitle_kr = (cover.get("subtitle_kr") or "").strip()

    scenario_default_en = (
        "%s. %s In this challenge you are the person who has to act while the evidence is still "
        "incomplete. Readers, institutions and the people closest to the story all want something "
        "different from it: some want a clear public answer now, some want proof first, and some "
        "want to be protected from the cost of either choice. The story does not settle which of "
        "those demands should win, and no option satisfies all three at once."
        % (headline_en, subtitle_en)
    ).replace("  ", " ").strip()
    scenario_default_kr = (
        "%s. %s 이 과제에서 당신은 근거가 아직 충분하지 않은 상태에서 결정을 내려야 하는 사람입니다. "
        "독자와 기관, 그리고 사안에 가장 가까운 사람들은 서로 다른 것을 원합니다. 어떤 이는 지금 분명한 공적 답을 "
        "원하고, 어떤 이는 먼저 검증된 근거를 원하며, 또 어떤 이는 어느 쪽을 택하든 그 비용에서 보호받기를 "
        "원합니다. 기사는 이 요구들 가운데 무엇이 우선인지 결론내리지 않으며, 세 가지를 동시에 만족시키는 선택지는 "
        "없습니다."
        % (headline_kr, subtitle_kr or "")
    ).replace("  ", " ").strip()

    question_default_en = (
        "Design a six-month plan for the people responsible for this issue. Decide which option you "
        "would act on first, which you would delay, and what you would refuse to give up even if it "
        "made everything else slower. Then justify the trade-off you accepted and explain how the "
        "groups who lose something in your plan would be told and heard."
    )
    question_default_kr = (
        "이 사안을 책임진 사람들을 위한 6개월 계획을 설계해 봅시다. 어느 선택을 가장 먼저 실행하고, 무엇을 "
        "미루며, 나머지가 느려지더라도 포기하지 않을 것은 무엇인지 정해 보세요. 이어서 받아들인 상충 관계를 "
        "근거와 함께 설명하고, 계획에서 손해를 보는 집단에게 어떻게 알리고 의견을 들을지 밝혀 봅시다."
    )

    cd = layer.get("complex_dilemma")
    if not isinstance(cd, dict):
        cd = {}
        filled_now = True
    else:
        filled_now = False

    changed = []
    defaults = {
        "title_en": ("Conundrum · Complex Problem-Solving", "Conundrum · 복합 난제 해결 과제"),
        "scenario_en": (scenario_default_en, scenario_default_kr),
        "question_en": (question_default_en, question_default_kr),
    }
    for key, (default_en, default_kr) in defaults.items():
        en, kr = _bilingual(cd.get(key))
        kr_key = key.replace("_en", "_kr")
        kr_value, _ = _bilingual(cd.get(kr_key))
        if not en:
            cd[key] = default_en
            changed.append(key)
            en = default_en
        if not kr_value:
            cd[kr_key] = default_kr
            changed.append(kr_key)

    cd["constraints"] = _bilingual_list(cd.get("constraints"), DILEMMA_CONSTRAINTS, 2)
    cd["evaluation_lens"] = _bilingual_list(cd.get("evaluation_lens"), DILEMMA_LENS, 2)

    layer["complex_dilemma"] = cd
    if filled_now or changed:
        return ["complex_dilemma"]
    return []


def ensure_learning(daily):
    """Fill any missing practice / knowledge fields so the sections always render."""
    date_str = daily.get("edition_date", "")
    word = (daily.get("word_of_day", {}) or {}).get("word", "").strip()
    cover = daily.get("cover_story", {}) or {}
    topic_en = _topic_phrase(daily)
    topic_kr = (cover.get("headline_kr") or "").strip() or word or "오늘의 이슈"
    if len(topic_kr) > 60:
        topic_kr = topic_kr[:58].rstrip() + "…"
    filled = []

    practice = daily.setdefault("practice", {})
    det = DET_QUESTIONS[_hash_index(date_str + word, len(DET_QUESTIONS))]
    if not practice.get("det_question_en"):
        practice["det_question_en"] = det["en"]
        filled.append("det_question_en")
    if not practice.get("det_question_kr"):
        practice["det_question_kr"] = det["kr"]
        filled.append("det_question_kr")
    if not practice.get("det_structure_en"):
        practice["det_structure_en"] = (
            "60 seconds, four moves: 1) Take a position in one sentence. "
            "2) Give one reason. 3) Add one concrete example. 4) Close with a short conclusion."
        )
    if not practice.get("det_structure_kr"):
        practice["det_structure_kr"] = (
            "60초, 네 단계: 1) 한 문장으로 입장 밝히기 2) 이유 한 가지 3) 구체적 예시 한 가지 4) 짧게 마무리."
        )
    if not practice.get("det_link_en"):
        practice["det_link_en"] = "Use today's word and the cover story as your evidence."
    if not practice.get("det_link_kr"):
        practice["det_link_kr"] = "오늘의 단어와 커버 스토리를 근거로 활용해 보세요."

    layer = daily.setdefault("knowledge_layer", {})
    kq = TOK_QUESTIONS[_hash_index(date_str + (cover.get("headline_en") or ""), len(TOK_QUESTIONS))]
    if not layer.get("tok_question_en"):
        layer["tok_question_en"] = kq["en"].format(topic=topic_en)
        filled.append("tok_question_en")
    if not layer.get("tok_question_kr"):
        layer["tok_question_kr"] = kq["kr"].format(topic=topic_kr)
        filled.append("tok_question_kr")
    if not layer.get("aok_en"):
        layer["aok_en"] = "Human Sciences · Natural Sciences"
    if not layer.get("aok_kr"):
        layer["aok_kr"] = "인간과학 · 자연과학"
    if not layer.get("wok_en"):
        layer["wok_en"] = "Reason · Language · Emotion"
    if not layer.get("wok_kr"):
        layer["wok_kr"] = "이성 · 언어 · 감정"
    if not layer.get("claim_en"):
        layer["claim_en"] = (
            "Reliable knowledge about %s depends on verifiable evidence, not on how often a claim is repeated."
            % topic_en
        )
    if not layer.get("claim_kr"):
        layer["claim_kr"] = (
            "%s에 관한 신뢰할 수 있는 지식은 주장이 얼마나 반복되는지가 아니라 검증 가능한 근거에 달려 있다."
            % topic_kr
        )
    if not layer.get("counterclaim_en"):
        layer["counterclaim_en"] = (
            "But testimony and shared experience are also knowledge sources: communities often know things that data alone cannot capture."
        )
    if not layer.get("counterclaim_kr"):
        layer["counterclaim_kr"] = (
            "그러나 증언과 공유된 경험도 지식의 원천이다. 공동체는 데이터만으로는 담아낼 수 없는 것을 알고 있기도 하다."
        )
    if not layer.get("teded_keyword"):
        layer["teded_keyword"] = word.lower() if word else "critical thinking"
        filled.append("teded_keyword")
    if not layer.get("teded_why_en"):
        layer["teded_why_en"] = (
            "Search TED-Ed for a short lesson on this idea before you write, then note one claim you can test."
        )
    if not layer.get("teded_why_kr"):
        layer["teded_why_kr"] = (
            "쓰기 전에 TED-Ed에서 이 개념을 다룬 짧은 강의를 찾아보고, 검증해 볼 수 있는 주장 하나를 메모해 보세요."
        )
    if not layer.get("think_task_en"):
        layer["think_task_en"] = (
            "TED-Ed Think: Which evidence in today's story would you trust most, and what would change your mind?"
        )
    if not layer.get("think_task_kr"):
        layer["think_task_kr"] = (
            "TED-Ed Think: 오늘 기사에서 가장 신뢰하는 근거는 무엇이며, 무엇이 확인되면 생각이 바뀌겠는가?"
        )
    if not layer.get("dig_deeper_en"):
        layer["dig_deeper_en"] = (
            "Dig Deeper: Find one primary source (official statement, data release, or on-the-record interview) "
            "behind today's story and compare it with the news report."
        )
    if not layer.get("dig_deeper_kr"):
        layer["dig_deeper_kr"] = (
            "Dig Deeper: 오늘 기사 뒤에 있는 1차 자료(공식 발표, 통계, 실명 인터뷰) 하나를 찾아 보도 내용과 비교해 보세요."
        )
    if not layer.get("essay_task_en"):
        layer["essay_task_en"] = (
            "TOK extension (150 words): answer the knowledge question above, name one Area of Knowledge and one "
            "Way of Knowing, and give a counter-example that complicates your answer."
        )
    if not layer.get("essay_task_kr"):
        layer["essay_task_kr"] = (
            "TOK 확장 과제(150단어): 위 지식 질문에 답하고, 지식 영역(AOK) 하나와 인식 방법(WOK) 하나를 밝힌 뒤, "
            "자신의 답을 복잡하게 만드는 반례를 하나 제시해 봅시다."
        )
    filled.extend(ensure_complex_dilemma(layer, daily, topic_en, topic_kr))
    return filled


# ── main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default=None, help="data/daily-<date>.json to enrich in place")
    parser.add_argument("--news", default=None, help="data/news-context-<date>.json from fetch-news.py")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-network", action="store_true", help="skip FX/weather fetch (offline test)")
    parser.add_argument("--rate-only", action="store_true", help="print just the PHP/KRW rate for the prompt")
    args = parser.parse_args()

    if args.rate_only:
        rate, _source = fetch_rate()
        if rate is not None:
            print("%.2f" % rate)
        return 0

    if not args.json:
        parser.error("--json is required unless --rate-only is used")

    with open(args.json, encoding="utf-8") as fh:
        daily = json.load(fh)

    rate = rate_source = None
    weather = None
    if not args.no_network:
        log("[live] fetching PHP/KRW…")
        rate, rate_source = fetch_rate()
        log("[live] fetching Pasig weather…")
        weather = fetch_weather()

    changed = apply_dashboard(daily, rate, rate_source, weather)
    allowed = allowed_urls_from_news(args.news) if args.news else set()
    sourced = apply_source_guard(daily, allowed)
    filled = ensure_learning(daily)

    payload = json.dumps(daily, ensure_ascii=False, indent=2) + "\n"
    if not args.dry_run:
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(payload)

    dash = daily.get("dashboard", {})
    print("LIVE_JSON " + json.dumps({
        "file": args.json,
        "php_krw_rate": dash.get("php_krw_rate"),
        "rate_source": rate_source,
        "weather_en": dash.get("weather_en"),
        "weather_kr": dash.get("weather_kr"),
        "weather_source": dash.get("weather_source"),
        "updated_at_pht": dash.get("updated_at_pht"),
        "changed": changed,
        "sources_verified": sourced,
        "learning_fields_filled": filled,
        "dry_run": args.dry_run,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
