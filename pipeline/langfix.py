"""Language integrity: repair transliterations, judge nativeness, and verify audio."""
import difflib
import json
import os
import pathlib
import re


STRIP = ".,!?।…\"'“”‘’():;-–—"
SEED = [
    "FSSAI", "Bromate", "Polyacrylamide", "AI", "Google", "Amazon",
    "Microsoft", "OpenAI", "WhatsApp", "Instagram", "YouTube", "Facebook",
    "Nvidia", "Apple", "Samsung", "Tesla", "RBI", "SEBI", "TRAI", "UPI",
    "Aadhaar", "GPU", "CPU", "API", "Bisleri", "Aquafina", "Kinley",
]
KEEP = {
    "మీరు", "మీ", "మీకు", "నీ", "నీకు", "నీరు", "ధర", "ధరలు",
    "పెరుగుతుంది", "అసలు", "కానీ", "ఇప్పుడు", "చూడండి", "జాగ్రత్త",
    "తెలుసా", "ఎందుకు", "ఏమిటి", "విషం", "డబ్బు", "కంపెనీ",
    "आप", "आपका", "आपकी", "पानी", "कीमत", "बढ़", "असली", "लेकिन",
    "अभी", "देखो", "सावधान", "पता", "क्यों", "क्या", "पैसा", "कंपनी",
    "नहीं", "है", "और", "यह", "वो",
}

TE_C = dict(zip(
    "కఖగఘఙచఛజఝఞటఠడఢణతథదధనపఫబభమయరలవళశషసహఱ",
    ["ka", "kha", "ga", "gha", "na", "ca", "cha", "ja", "jha", "na",
     "ta", "tha", "da", "dha", "na", "ta", "tha", "da", "dha", "na",
     "pa", "pha", "ba", "bha", "ma", "ya", "ra", "la", "va", "la",
     "sha", "sha", "sa", "ha", "ra"],
))
TE_M = {
    "ా": "a", "ి": "i", "ీ": "i", "ు": "u", "ూ": "u", "ృ": "r",
    "ె": "e", "ే": "e", "ై": "ai", "ొ": "o", "ో": "o", "ౌ": "au",
    "ం": "m", "ః": "h",
}
TE_V = "\u0c4d"

DV_C = dict(zip(
    "कखगघङचछजझञटठडढणतथदधनपफबभमयरलवळशषसह",
    ["ka", "kha", "ga", "gha", "na", "ca", "cha", "ja", "jha", "na",
     "ta", "tha", "da", "dha", "na", "ta", "tha", "da", "dha", "na",
     "pa", "pha", "ba", "bha", "ma", "ya", "ra", "la", "va", "la",
     "sha", "sha", "sa", "ha"],
))
DV_M = {
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "r",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ं": "m", "ः": "h", "ँ": "n",
}
DV_V = "\u094d"


def to_latin(token, lang):
    consonants, matras, virama = (
        (TE_C, TE_M, TE_V) if lang == "te" else (DV_C, DV_M, DV_V)
    )
    output = []
    index = 0
    while index < len(token):
        char = token[index]
        if char in consonants:
            base = consonants[char]
            next_char = token[index + 1] if index + 1 < len(token) else ""
            if next_char == virama:
                output.append(base[:-1])
                index += 2
                continue
            if next_char in matras:
                output.append(base[:-1] + matras[next_char])
                index += 2
                continue
            output.append(base)
            index += 1
            continue
        output.append(matras.get(char, ""))
        index += 1
    return "".join(output)


def _skeleton(text):
    return re.sub(r"[^a-z]", "", re.sub(r"[aeiou]", "", text.lower()))


def glossary(story):
    text = str(story.get("title", "")) + " " + str(story.get("body", ""))
    terms = set(SEED)
    terms.update(re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", text))
    terms.update(re.findall(r"\b[A-Z]{2,6}\b", text))
    return sorted(term for term in terms if len(term) >= 3)


def _suspicious(token, lang):
    virama = TE_V if lang == "te" else DV_V
    return token.count(virama) >= 2 or len(token) >= 10


def repair_line(line, lang, terms):
    if lang not in ("te", "hi"):
        return line, []
    output = []
    fixes = []
    for raw in str(line).split():
        token = raw.strip(STRIP)
        if (not token or token in KEEP or re.search(r"[A-Za-z0-9]", token)
                or len(token) < 4):
            output.append(raw)
            continue
        latin = to_latin(token, lang)
        best = None
        best_score = 0.0
        for term in terms:
            score = max(
                difflib.SequenceMatcher(None, latin.lower(), term.lower()).ratio(),
                difflib.SequenceMatcher(None, _skeleton(latin), _skeleton(term)).ratio(),
            )
            if score > best_score:
                best, best_score = term, score
        threshold = 0.62 if _suspicious(token, lang) else 0.86
        if best and best_score >= threshold:
            output.append(raw.replace(token, best))
            fixes.append((token, best, round(best_score, 2)))
        else:
            output.append(raw)
    return " ".join(output), fixes


def repair_script(script, lang, story):
    terms = glossary(story)
    all_fixes = []
    for beat in script.get("beats", []):
        beat["line"], fixes = repair_line(beat.get("line", ""), lang, terms)
        all_fixes.extend(fixes)
    script["hook_text"], fixes = repair_line(script.get("hook_text", ""), lang, terms)
    all_fixes.extend(fixes)
    if all_fixes:
        script["script"] = " ".join(beat["line"] for beat in script["beats"])
        print(f"  langfix repaired {len(all_fixes)}: {all_fixes[:3]}", flush=True)
    return script


def judge(script, lang, model=None):
    """Native-speaker pass for Telugu and Hindi. Applies fixes only if retention gates pass."""
    if os.getenv("NATIVE_JUDGE", "0") != "1" or lang not in ("te", "hi"):
        return script
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return script
    model = model or os.getenv("VISION_MODEL", "gemini-3.5-flash-lite")
    lines = [beat["line"] for beat in script.get("beats", [])]
    name = "Telugu" if lang == "te" else "Hindi"
    prompt = (
        f"You are a native {name} speaker and Shorts editor. Below are spoken lines. "
        f"Find words that are NOT real {name} words or phrasing that sounds translated/robotic. "
        "Rewrite ONLY broken lines, keeping the same meaning and at most the same word count, "
        "and keep technical terms in Latin. "
        'Return JSON {"lines": [...same count...]}.\n\n'
        + json.dumps(lines, ensure_ascii=False)
    )
    try:
        import requests

        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.2,
                },
            },
            timeout=60,
        )
        if response.status_code != 200:
            return script
        payload = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        new_lines = json.loads(payload).get("lines", [])
        if len(new_lines) != len(lines):
            return script
        candidate = json.loads(json.dumps(script))
        for beat, line in zip(candidate["beats"], new_lines):
            beat["line"] = str(line).strip()
        from pipeline import retention

        if retention.gates(candidate, lang) is None:
            candidate["script"] = " ".join(beat["line"] for beat in candidate["beats"])
            print("  native judge applied", flush=True)
            return candidate
        print("  native judge rejected by gates", flush=True)
    except Exception as error:
        print(f"  native judge skipped ({str(error)[:50]})", flush=True)
    return script


def _cer(actual, expected):
    actual = re.sub(r"\s+", " ", actual).strip()
    expected = re.sub(r"\s+", " ", expected).strip()
    if not actual or not expected:
        return 1.0
    previous = list(range(len(expected) + 1))
    for i, actual_char in enumerate(actual, 1):
        current = [i]
        for j, expected_char in enumerate(expected, 1):
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (actual_char != expected_char),
            ))
        previous = current
    return previous[-1] / max(len(actual), len(expected))


def audio_gate(mp3, script_text, lang):
    """Optional Whisper round-trip for the final rendered voice."""
    if os.getenv("ASR_GATE", "0") != "1":
        return None, None
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None, None
    try:
        import requests

        response = None
        for model in ("whisper-large-v3-turbo", "whisper-large-v3"):
            with open(mp3, "rb") as audio_file:
                response = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": (pathlib.Path(mp3).name, audio_file, "audio/mpeg")},
                    data={"model": model, "language": lang, "response_format": "json"},
                    timeout=120,
                )
            if response.status_code == 200:
                heard = response.json().get("text", "")
                cer = _cer(script_text, heard)
                tag = "OK" if cer <= 0.22 else "BAD"
                print(f"  audio CER {cer:.2f} [{tag}] via {model}", flush=True)
                return cer, heard
        print(f"  ASR gate skipped ({response.status_code})", flush=True)
    except Exception as error:
        print(f"  ASR gate skipped ({str(error)[:50]})", flush=True)
    return None, None
