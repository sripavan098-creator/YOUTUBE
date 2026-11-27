"""Machine-enforced retention rules for Shorts scripts and footage."""
import base64
import os
import re


WPS = {"te": 2.3, "hi": 2.4, "en": 2.8}
MAX_HOOK_SEC = 2.8
MAX_HOOK_WORDS = 6
MAX_BEAT_SEC = 4.0
MAX_BEAT_WORDS = 9
BEATS_RANGE = (6, 9)
TOTAL_WORDS = (50, 80)

SECOND_PERSON = [
    "మీరు", "మీ", "నీ", "మీకు", "నీకు",
    "आप", "आपका", "आपकी", "तुम", "तुम्हारा",
    "your", "you",
]
THREAT = [
    "విష", "ప్రమాద", "బ్యాన్", "బంద్", "మూసి", "ఆపే", "పోతుంద", "ఖరీదు",
    "పెరుగు", "జాగ్రత్త", "ఫెయిల్", "రికాల్", "నష్ట", "మోస",
    "खतरा", "बंद", "बैन", "महंगा", "नुकसान", "फेल", "रीकॉल", "सावधान",
    "poison", "banned", "recall", "danger", "expensive", "scam", "leak",
    "hacked",
]
GREETING_BAN = [
    "నమస్కార", "హలో", "ఈ రోజు", "ఈ వీడియో",
    "नमस्कार", "नमस्ते", "हैलो", "आज हम", "इस वीडियो",
    "hello", "welcome", "today we", "in this video",
]
CTA_REASON = [
    "లిస్ట్", "బ్రాండ్", "జాబితా", "సెట్టింగ", "స్టెప్", "లింక్", "చెక్",
    "लिस्ट", "ब्रांड", "सेटिंग", "स्टेप", "लिंक", "चेक",
    "list", "brands", "settings", "steps", "link", "check",
]
ABSTRACT_SHOT = {
    "concept", "idea", "future", "technology", "innovation", "abstract",
    "background", "business", "success", "problem", "solution", "impact",
    "market", "economy", "growth", "digital", "data", "security", "war",
}
BAD_VISUAL = (
    "map", "atlas", "flag", "emblem", "coat of arms", "war", "soldier",
    "military", "army", "nuclear", "atomic", "reactor", "poster",
    "propaganda", "vintage", "antique", "manuscript", "parchment", "sketch",
    "drawing", "illustration", "engraving", "architecture", "interior", "room",
    "window", "door", "ceiling", "closed", "sign board", "shop", "currency",
    "cash box", "coin", "banknote", "logo", "symbol", "seal", "heraldry",
    "church", "temple", "statue",
)

_STRIP = ".,!?।…\"'“”‘’():;-–—"


def _telugu_consonant(char):
    return 0x0C15 <= ord(char) <= 0x0C39


def _telugu_matra(char):
    return 0x0C3E <= ord(char) <= 0x0C4C or 0x0C55 <= ord(char) <= 0x0C56


def _devanagari_consonant(char):
    return 0x0915 <= ord(char) <= 0x0939 or 0x0958 <= ord(char) <= 0x095F


def _devanagari_matra(char):
    return 0x093E <= ord(char) <= 0x094C or 0x0962 <= ord(char) <= 0x0963


def _kind(lang):
    if lang == "te":
        return _telugu_consonant, _telugu_matra, "\u0c4d"
    if lang == "hi":
        return _devanagari_consonant, _devanagari_matra, "\u094d"
    return None, None, None


def gibberish_tokens(text, lang):
    """Detect invented native-script transliterations as a safety net."""
    consonant, matra, virama = _kind(lang)
    if consonant is None:
        return []
    bad = []
    for raw in str(text).split():
        token = raw.strip(_STRIP)
        if not token or re.search(r"[A-Za-z0-9]", token):
            continue
        virama_count = token.count(virama)
        consonant_count = sum(1 for char in token if consonant(char))
        matra_count = sum(1 for char in token if matra(char))
        if (virama_count >= 3
                or (len(token) >= 16 and matra_count / max(1, consonant_count) < 0.25)
                or (consonant_count >= 6 and matra_count == 0)):
            bad.append(token)
    return bad


def est_sec(line, lang):
    return len(str(line).split()) / WPS.get(lang, 2.6)


def _has_stake(line):
    low = str(line).lower()
    return (any(person in low for person in SECOND_PERSON)
            or any(threat in low for threat in THREAT)
            or bool(re.search(r"[0-9₹%]", low))
            or "?" in low)


def shot_ok(query):
    words = [word for word in str(query).lower().split() if word]
    if not (2 <= len(words) <= 4):
        return False, "shot must be 2-4 concrete words"
    if any(word in ABSTRACT_SHOT for word in words):
        return False, "abstract word; name a visible object"
    return True, ""


def gates(script, lang):
    """Return the first hard-gate violation, or None."""
    beats = script.get("beats") or []
    if not isinstance(beats, list) or not (BEATS_RANGE[0] <= len(beats) <= BEATS_RANGE[1]):
        return f"need {BEATS_RANGE[0]}-{BEATS_RANGE[1]} beats, got {len(beats)}"

    lines = [str(beat.get("line", "")).strip() for beat in beats]
    if any(not line for line in lines):
        return "a beat has an empty line"

    hook = lines[0]
    if len(hook.split()) > MAX_HOOK_WORDS:
        return f"hook is {len(hook.split())} words (max {MAX_HOOK_WORDS})"
    if est_sec(hook, lang) > MAX_HOOK_SEC:
        return f"hook runs {est_sec(hook, lang):.1f}s (max {MAX_HOOK_SEC}s)"
    if not _has_stake(hook):
        return ("hook has no stake: use second person (మీరు/आप/your), a real number, "
                "a threat word, or a question")
    for greeting in GREETING_BAN:
        if hook.lower().startswith(greeting.lower()):
            return f"hook opens with filler '{greeting}'; start mid-conflict"

    shots = set()
    for index, beat in enumerate(beats):
        words = len(lines[index].split())
        if words > MAX_BEAT_WORDS:
            return (f"beat {index} is {words} words (max {MAX_BEAT_WORDS}); "
                    f"it would hold one shot {est_sec(lines[index], lang):.1f}s")
        if est_sec(lines[index], lang) > MAX_BEAT_SEC:
            return f"beat {index} runs {est_sec(lines[index], lang):.1f}s (max {MAX_BEAT_SEC}s)"
        query = str(beat.get("shot", "")).strip().lower()
        valid, reason = shot_ok(query)
        if not valid:
            return f"beat {index} shot '{query}': {reason}"
        if query in shots:
            return f"beat {index} repeats shot '{query}'"
        shots.add(query)

    total = sum(len(line.split()) for line in lines)
    if not (TOTAL_WORDS[0] <= total <= TOTAL_WORDS[1]):
        return f"script is {total} words (need {TOTAL_WORDS[0]}-{TOTAL_WORDS[1]})"
    if not any(beat.get("stat") for beat in beats[1:]):
        return "no number card: one beat must carry a real number/amount as 'stat'"
    if "?" not in " ".join(lines[-2:]):
        return "no closing question in the last two beats"
    if not any(beat.get("role") == "rehook" for beat in beats):
        return "missing rehook beat"

    cta = str(script.get("cta_screen", "")).strip()
    if not cta:
        return "missing cta_screen"
    if len(cta.split()) > 9:
        return "cta_screen longer than 9 words"
    if not any(reason in cta.lower() for reason in CTA_REASON):
        return "cta_screen has no reason to act: promise a concrete asset, not 'follow daily'"

    for index, line in enumerate(lines):
        bad = gibberish_tokens(line, lang)
        if bad:
            return (f"beat {index} has invented spellings {bad[:2]}; keep technical terms "
                    "in Latin and plain native words elsewhere")
    if gibberish_tokens(script.get("hook_text", ""), lang):
        return "hook_text has invented spellings; use plain native words"
    return None


WEIGHTS = {
    "hook": 30,
    "number": 15,
    "cuts": 15,
    "language": 15,
    "cta": 10,
    "loop": 15,
}


def score(script, lang, footage_hits=None, footage_total=None):
    beats = script.get("beats") or []
    lines = [str(beat.get("line", "")) for beat in beats]
    total = 0
    notes = []
    hook = lines[0] if lines else ""
    hook_score = 0
    if len(hook.split()) <= MAX_HOOK_WORDS and est_sec(hook, lang) <= MAX_HOOK_SEC:
        hook_score += 15
    if _has_stake(hook):
        hook_score += 15
    total += hook_score
    if hook_score < 30:
        notes.append("hook weak")

    if any(beat.get("stat") for beat in beats[1:]):
        total += WEIGHTS["number"]
    else:
        notes.append("no number card")

    if beats and max(est_sec(line, lang) for line in lines) <= MAX_BEAT_SEC:
        total += WEIGHTS["cuts"]
    else:
        notes.append("shot held too long")

    gibberish = sum(len(gibberish_tokens(line, lang)) for line in lines)
    if gibberish:
        total += max(0, WEIGHTS["language"] - 5 * gibberish)
        notes.append(f"{gibberish} invented spellings")
    else:
        total += WEIGHTS["language"]

    cta = str(script.get("cta_screen", "")).lower()
    if cta and any(reason in cta for reason in CTA_REASON):
        total += WEIGHTS["cta"]
    else:
        notes.append("cta has no reason to act")

    if "?" in " ".join(lines[-2:]) and any(beat.get("role") == "rehook" for beat in beats):
        total += WEIGHTS["loop"]
    else:
        notes.append("weak loop/rehook")

    if footage_total:
        ratio = (footage_hits or 0) / footage_total
        total = int(total * (0.7 + 0.3 * ratio))
        if ratio < 0.7:
            notes.append(f"footage relevance {ratio:.0%}")
    return total, notes


def verdict(score):
    return "ship" if score >= 85 else ("polish" if score >= 70 else "regenerate")


def rank_results(results, query):
    keywords = {word.lower() for word in str(query).split() if len(word) > 2}
    best = None
    best_hits = 0
    for photo in results:
        blob = (
            str(photo.get("alt_description") or "")
            + " "
            + str(photo.get("description") or "")
            + " "
            + " ".join(
                str(tag.get("title") or tag.get("tag") or "")
                for tag in (photo.get("tags") or [])
            )
        ).lower()
        if any(bad in blob for bad in BAD_VISUAL):
            continue
        hits = sum(1 for keyword in keywords if keyword in blob)
        if hits > best_hits:
            best, best_hits = photo, hits
    return best, best_hits


def vision_ok(image_path, line, model=None):
    """Optional Gemini relevance check. Fails open when it cannot verify."""
    if os.getenv("VISION_VERIFY", "0") != "1":
        return True
    from pipeline.provider_keys import gemini_keys

    keys = gemini_keys()
    if not keys:
        return True
    model = model or os.getenv("VISION_MODEL", "gemini-1.5-flash-latest")
    try:
        import requests

        encoded = base64.b64encode(open(image_path, "rb").read()).decode()
        response = None
        for key in keys:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key},
                json={
                    "contents": [{"parts": [
                        {"text": (
                            "Does this photo clearly illustrate the line below? Answer only "
                            "YES or NO.\nLINE: " + str(line)
                        )},
                        {"inline_data": {"mime_type": "image/jpeg", "data": encoded}},
                    ]}],
                    "generationConfig": {"temperature": 0},
                },
                timeout=45,
            )
            if response.status_code == 200:
                break
        if response is None or response.status_code != 200:
            return True
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip().upper()
        return not text.startswith("NO")
    except Exception:
        return True


PROMPT_RULES = """
RETENTION LAW (hard-validated; violations are auto-rejected):
- Hook: <=6 words, spoken under 2.8s, opens mid-conflict. MUST contain one of: second person
  (మీరు / आप / your), a real number or ₹ amount, a threat word, or a question. Never a
  greeting, never "this video", never a topic summary.
- Every beat: <=9 words (target 5-8). One beat = one shot. Anything over 4 spoken seconds is
  rejected, because holding one image that long is where viewers swipe.
- 6-9 beats, 50-80 words total. One middle beat role="rehook". Last beat is a question that
  echoes the hook so the video loops.
- At least one beat carries "stat": a real number or ₹ amount from KEY_FACTS. Prefer an
  absolute amount the viewer feels (₹2 more per bottle) over a vague percentage.
- "shot": 2-4 words naming a VISIBLE OBJECT matching its own line ("water bottle label",
  "lab test tubes", "price tag rupees", "phone screen settings"). Never abstract words
  (market, future, security, impact), never maps, flags, war, posters, vintage art,
  interiors, logos or currency. Never repeat a shot.
- LANGUAGE: native script, but keep technical terms, acronyms and brands in Latin exactly as
  a real tech creator writes them: FSSAI, Bromate, Polyacrylamide, AI, Google. NEVER invent a
  native-script spelling of an English word — that is auto-rejected.
- "cta_screen": <=9 words promising a CONCRETE asset ("ఆ 5 బ్రాండ్ల లిస్ట్ — బయో లింక్",
  "ब्रांड लिस्ट — Bio लिंक"). Never "follow daily". Add "cta_screen" to the JSON.
"""
