"""Two-stage script writing.

Stage 1 (propose_angles): cheap, English. Three distinct takes per story plus the facts
the source actually supports. The editor picks a take on Telegram.
Stage 2 (write_script): only for the picked take, once per channel. Writes natively in
the channel's language as timed BEATS (one spoken line + one stock-footage query each),
validates the result against retention rules, and retries with the exact failure reason.
"""
import json
import os
import random
import re
import pathlib
import time

import requests
from openai import APIStatusError, OpenAI

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- stage 1: angles

SYS_ANGLES = """You are the head of content for a viral Indian tech Shorts channel.
For the SOURCE story, propose 3 DISTINCT angles. Each angle is a different reason a viewer
would care, not a rewording of the same headline. Pick from: money/jobs impact on an
Indian viewer, 'this changes what you use daily', hidden catch / what they are not telling
you, David-vs-Goliath, 'what happens next' prediction, myth-busting.

Return STRICT JSON:
{"angles": [
  {"angle_id": "A", "take": "one line, <=14 words, the unique claim of this angle",
   "hook_idea": "the single most scroll-stopping first sentence, in English",
   "key_facts": ["3-5 short facts that appear in the SOURCE. No outside facts."]},
  {"angle_id": "B", ...}, {"angle_id": "C", ...}
]}
If a TRENDING_SEARCH line is given, people in India are searching that term right now:
make at least one angle that uses it naturally. Never force it when it does not fit.
Facts must be traceable to the SOURCE text. If the source is thin, use fewer facts.
Return ONLY raw JSON. No markdown, no code fences."""

# ---------------------------------------------------------------- stage 2: script

SYS_WRITE = """You are a {lang_name} YouTuber who makes viral Shorts.
You have grown a channel to 1 million subscribers by speaking the way your audience
actually talks — not the way textbooks or news anchors talk. You THINK in {lang_name}.
You never translate from English.

Channel: "{brand}". Audience: {audience}.

LANGUAGE (the most important rule):
{style}
Every line must be written ONLY in the native script. No Latin letters at all. Product and
company names are written the way people say them, in native script.

Return STRICT JSON:
{{
 "title": "<=60 chars, native script, a curiosity gap or a concrete stake, never a summary.
           If a TRENDING_SEARCH is given and fits, include it the way people type it.",
 "hook_text": "2-5 native words shown huge on screen in the first 2 seconds",
 "beats": [{{"line": "one spoken sentence", "shot": "2-3 English words for a photo search",
            "role": "hook | fact | rehook | payoff | loop",
            "mood": "shock | urgent | excited | curious | calm | serious (how it is SPOKEN)",
            "slam": "optional: ONE word from the line, thrown huge on screen",
            "stat": "optional: a number or 2-word claim from the line to show as a big card, e.g. \u20b91,500"}}],
 "search_terms": ["6-8 phrases people really type into YouTube search for this topic: 3-4 in the native script, 3-4 in English"],
 "emphasis": ["up to 8 single words copied exactly from the lines that deserve color"],
 "description": "2 lines in native script. Line 1 carries the main keyword and the hook. Line 2 asks a question.",
 "ig_caption": "hook line, blank line, 2 short lines, a question, blank line, 5 hashtags",
 "hashtags": ["#shorts", "...5-7 tags, mix of broad and specific, native or English as people search"]
}}

THE 3-SECOND RULE. People decide to swipe in under 3 seconds, so beats[0] is everything:
- 8 words or fewer, spoken in about 2.5 seconds. Starts with the stake, not the topic.
- It must do ONE of: threaten the viewer's money/job/phone/account; promise a secret they
  are missing; state a shocking number; ask a question they cannot answer yet.
- Never greet. Never say the channel name. Never start with "today" or "in this video".
- Speak TO the viewer ("you/your" in their language), not about a company.

STRUCTURE after the hook:
1. beats[1-2]: the concrete fact, with the one number or name that makes it real.
2. A RE-HOOK around the middle (a turn like "but here is the catch") so attention resets
   exactly where people swipe away.
3. beats[-2]: the payoff that closes the loop the hook opened.
4. beats[-1]: a question that invites a comment AND echoes the first beat so the video
   loops cleanly when it replays.

HOOK ARCHETYPE for this video: {archetype}

DIRECTION (this drives voice, sound and screen, so use it deliberately):
- role: beats[0]="hook", one middle beat="rehook", beats[-2]="payoff", beats[-1]="loop",
  the rest "fact".
- mood: the hook is "shock" or "urgent"; the payoff is "serious" or "calm"; do not give every
  beat the same mood. A calm beat right before a shocking one makes the shock land.
- slam: on at most 3 beats (never the hook), the single most powerful word. stat: on at
  most 2 beats, only a real number or a 2-word claim that is in the source.
- Never say "subscribe" or "follow" inside the lines; the screen handles that.

STYLE:
- 6 to 9 beats, each 5 to 14 words. Total 60-95 words. Short punchy sentences.
- Every beat gives NEW information or a new emotion. No filler, no recap.
- Use ONLY facts from KEY_FACTS and SOURCE. Never invent numbers, quotes or dates.
- 'shot' is a PHOTO search for Unsplash: a concrete, photogenic subject that matches the
  line, such as "smartphone in hand", "indian street night", "server room", "stock market
  screen", "student laptop". No abstract words, no brand names, no people's names. Add
  "india" when a local feel helps. Never repeat a shot query.

Return ONLY raw JSON. No markdown, no code fences."""

LANG_NAME = {"hi": "Hindi (Devanagari)", "te": "Telugu (Telugu script)", "en": "English"}

LANG_STYLE = {
    "te": """భాష నియమాలు (Language Rules — Telugu):
You are a Telugu content creator from Andhra Pradesh who has been making YouTube videos
for 5 years. You THINK in Telugu. You do NOT translate.

VOICE: Sound like you're excitedly telling your best friend something shocking you just
found out. Fast, natural, real Andhra Telugu rhythm.

WHAT REAL TELUGU SOUNDS LIKE:
✓ "అరే, మీకు తెలుసా ఏమైందో?"  (casual opening, not "నమస్కారం" or "ఈ రోజు మనం")
✓ "ఇప్పుడే చూశాను, నమ్మలేకపోయాను"  (excited personal tone)
✓ "అది చాలా పెద్ద తప్పు అవుతుంది"  (warning, not robotic)
✓ Short exclamations: "అరే!", "చూడండి!", "జాగ్రత్త!", "ఏంటి సంగతి?"

FORBIDDEN (these make it sound translated or robotic):
✗ Long compound sentences joined by కానీ/మరియు without pause
✗ "ఈ వీడియోలో మనం చూస్తాం" — never say what the video is about
✗ Starting sentences with "అయినప్పటికీ", "అందువల్ల", "అందుకే" (too formal/textbook)
✗ Repeating the same sentence structure beat after beat
✗ Using "సదస్సు", "ప్రకటన", "సేవలు" — use "మీటింగ్", "న్యూస్", "పని" instead

RHYTHM PATTERN (follow this loosely):
Hook (fast, shocking, 6-8 words) → Fact 1 (medium, concrete) → Fact 2 (medium) →
RE-HOOK (slow down, pause word + fast restart) → Payoff (slow, serious) → Loop (question, conversational)

NATIVE WORD PREFERENCES:
డబ్బు (not ధనం), ఉద్యోగం (not వృత్తి), ఉచితంగా (not రుసుము లేకుండా),
జాగ్రత్త (not హెచ్చరిక), తెలుసా (not అవగాహన కలిగి ఉన్నారా)
""",
    "hi": """भाषा नियम (Language Rules — Hindi):
आप एक Hindi content creator हैं जो 5 साल से YouTube Shorts बना रहे हैं।
आप Hindi में सोचते हैं। आप translate नहीं करते।

VOICE: जैसे आप अपने दोस्त को कोई बड़ी खबर सुना रहे हों — जल्दी, excited, real।

असली HINDI कैसी लगती है:
✓ "अरे यार, ये देखो क्या हो गया!" (casual, real)
✓ "बस अभी-अभी पता चला, believe नहीं हो रहा" (excited)
✓ "ये गलती मत करना, वरना..."  (warning, not robotic)
✓ Short exclamations: "सुनो!", "ध्यान दो!", "रुको!", "सच बताऊं?"

FORBIDDEN (इससे robotic या translated लगता है):
✗ "इस वीडियो में हम देखेंगे" — never explain the video
✗ Long formal sentences with "तथापि", "अतः", "इसलिए"
✗ Same sentence structure for every beat
✗ "नमस्कार दोस्तों" — never greet
✗ Passive voice: "किया जाएगा", "बताया गया" — use active: "करेंगे", "बताया"

RHYTHM PATTERN:
Hook (तेज़, shocking, 6-8 words) → Fact 1 (normal speed, concrete) → Fact 2 →
RE-HOOK (थोड़ा slow, turn) → Payoff (slow, serious) → Loop (question, friendly)

NATIVE WORD PREFERENCES:
पैसा (not धन), नौकरी (not रोजगार), मुफ़्त (not निःशुल्क),
सावधान (not चेतावनी), जानते हो? (not क्या आप जानते हैं?)
""",
    "en": "Write plain, punchy spoken English.",
}


HOOK_ARCHETYPES = {
    "stake": "Threaten something the viewer owns: their money, phone, account, job, data.",
    "secret": "Promise a thing they are being kept from: 'the setting nobody tells you about'.",
    "number": "Open on one shocking number or amount, then say what it means for them.",
    "question": "Ask a question they cannot answer yet and badly want to.",
    "contrarian": "Say the opposite of what they believe, in one line, then prove it.",
    "countdown": "Urgency: something ends, changes or starts today and they must act.",
}


def _extract_json(text):
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    return json.loads(t[start:end + 1])


_RETRY_STATUS = {429, 500, 502, 503, 504}


def _status_of(exc):
    """HTTP status from either a requests or an OpenAI SDK error."""
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None)
    if status is None:
        status = getattr(exc, "status_code", None)
    return status


def _with_retry(fn, attempts=3, base=2.0):
    """Retry transient provider failures with exponential backoff.

    Gemini returns 503 "high demand" often enough that a single attempt drops a
    channel to the next provider for the whole run.
    """
    retryable = (requests.HTTPError, APIStatusError)
    for i in range(attempts):
        try:
            return fn()
        except retryable as e:
            status = _status_of(e)
            if status not in _RETRY_STATUS or i == attempts - 1:
                raise
            wait = base * (2 ** i)
            print(f"    {status} from provider, retrying in {wait:.0f}s...", flush=True)
            time.sleep(wait)


def _groq(system, prompt, model, temperature=0.7):
    c = OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1",
               timeout=60)
    kwargs = {}
    if "gpt-oss" in model:
        kwargs["extra_body"] = {"reasoning_effort": "medium"}
    return _with_retry(lambda: c.chat.completions.create(
        model=model, temperature=temperature, max_tokens=4000,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": prompt}], **kwargs).choices[0].message.content)


def _gemini(system, prompt, model, temperature=0.7):
    def call():
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
            json={"contents": [{"parts": [{"text": system + "\n\n" + prompt}]}],
                  "generationConfig": {"responseMimeType": "application/json",
                                       "temperature": temperature}},
            timeout=60)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _with_retry(call)


def _providers(cfg):
    p = [(_groq, cfg["model_primary"]), (_gemini, cfg["model_fallback"])]
    if cfg.get("model_fallback2"):
        p.append((_gemini, cfg["model_fallback2"]))
    return p


def _dump(tag, text):
    try:
        d = ROOT / "out" / "debug"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{tag}.txt").write_text(text or "", encoding="utf-8")
    except Exception:
        pass


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower())[:40]


# ---------------------------------------------------------------- validation

def _check_angles(angles):
    if not isinstance(angles, list) or len(angles) < 2:
        return "need at least 2 angles"
    seen = set()
    for i, a in enumerate(angles):
        if not isinstance(a, dict):
            return f"angle {i} is not an object"
        take = str(a.get("take", "")).strip().lower()
        if not take:
            return f"angle {i} has empty take"
        if take in seen:
            return f"angle {i} duplicate take"
        seen.add(take)
        if not str(a.get("hook_idea", "")).strip():
            return f"angle {i} missing hook_idea"
        if not isinstance(a.get("key_facts"), list) or not a["key_facts"]:
            return f"angle {i} missing key_facts"
    return None


def check_script(d, lang=None):
    """Retention rules. Returns None if usable, else the exact reason."""
    if not isinstance(d, dict):
        return "not an object"
    beats = d.get("beats")
    if not isinstance(beats, list) or not (5 <= len(beats) <= 10):
        return f"need 5-10 beats, got {len(beats) if isinstance(beats, list) else 'none'}"
    lines = []
    shots = set()
    for i, b in enumerate(beats):
        if not isinstance(b, dict) or not str(b.get("line", "")).strip():
            return f"beat {i} has no line"
        n = len(b["line"].split())
        if n < 3 or n > 18:
            return f"beat {i} has {n} words (need 3-18)"
        shot = str(b.get("shot", "")).strip().lower()
        if not shot:
            return f"beat {i} has no shot"
        if shot in shots:
            return f"beat {i} repeats shot '{shot}'"
        shots.add(shot)
        lines.append(b["line"])
    hook_words = len(lines[0].split())
    if hook_words > 8:
        return f"hook is {hook_words} words (need <=8, it must be spoken in about 2.5 s)"
    if lang in ("hi", "te"):
        for i, l in enumerate(lines):
            if re.search(r"[A-Za-z]", l):
                return (f"beat {i} contains Latin letters; write it entirely in "
                        f"{'Devanagari' if lang == 'hi' else 'Telugu'} script")
        if re.search(r"[A-Za-z]", str(d.get("hook_text", ""))):
            return "hook_text contains Latin letters"
    total = sum(len(l.split()) for l in lines)
    if not (50 <= total <= 105):
        return f"script is {total} words (need 50-105)"
    if not any("?" in l for l in lines[-2:]):
        return "no closing question in the last two beats"
    if not str(d.get("title", "")).strip():
        return "missing title"
    if len(str(d["title"])) > 100:
        return "title too long"
    if not str(d.get("hook_text", "")).strip():
        return "missing hook_text"
    if len(str(d["hook_text"]).split()) > 6:
        return "hook_text longer than 6 words"
    if not d.get("hashtags"):
        return "missing hashtags"
    return None


# ---------------------------------------------------------------- public API

def _story_prompt(story):
    return f"TITLE: {story['title']}\nSOURCE_URL: {story['url']}\nSOURCE:\n{story['body']}"


def propose_angles(story, cfg):
    prompt = _story_prompt(story)
    if story.get("trend_hits"):
        prompt += "\nTRENDING_SEARCH: " + ", ".join(story["trend_hits"][:3])
    errors = []
    slug = _slug(story["title"])
    for fn, model in _providers(cfg):
        raw = ""
        try:
            print(f"  angles via {model}...", flush=True)
            raw = fn(SYS_ANGLES, prompt, model, 0.8)
            angles = _extract_json(raw).get("angles", [])
            reason = _check_angles(angles)
            if reason is None:
                angles = angles[:3]
                for i, a in enumerate(angles):
                    a["angle_id"] = chr(65 + i)
                return angles
            _dump(f"{slug}_angles_{model.replace('/', '-')}", raw)
            errors.append(f"{model}: {reason}")
        except Exception as e:
            if raw:
                _dump(f"{slug}_angles_{model.replace('/', '-')}", raw)
            errors.append(f"{model}: {e}")
    raise RuntimeError("angle generation failed -> " + " | ".join(errors))


def write_script(story, angle, lcfg, cfg, note="", archetype="stake"):
    """Write the picked angle natively for one channel. Retries feed the exact failure
    back to the model so the second attempt fixes the specific rule that was broken."""
    system = SYS_WRITE.format(lang_name=LANG_NAME.get(lcfg["lang"], lcfg["lang"]),
                              style=LANG_STYLE.get(lcfg["lang"], ""),
                              brand=lcfg["brand"], audience=lcfg["audience"].replace("_", " "),
                              archetype=f"{archetype}: {HOOK_ARCHETYPES.get(archetype, '')}")
    base = (_story_prompt(story) +
            f"\n\nANGLE: {angle['take']}\nHOOK_IDEA (translate the energy, not the words): "
            f"{angle.get('hook_idea', '')}\nKEY_FACTS:\n" +
            "\n".join(f"- {f}" for f in angle.get("key_facts", [])))
    if story.get("trend_hits"):
        base += ("\nTRENDING_SEARCH (people in India are searching this right now; use it in the "
                 "title and early in the script only if it truly fits): "
                 + ", ".join(story["trend_hits"][:3]))
    if note:
        base += "\n\nEDITOR NOTE: " + note
    errors = []
    slug = _slug(story["title"]) + "_" + lcfg["lang"]
    for fn, model in _providers(cfg):
        feedback = ""
        for attempt in range(2):
            raw = ""
            try:
                print(f"  script [{lcfg['lang']}] via {model} try {attempt + 1}...", flush=True)
                raw = fn(system, base + feedback, model, 0.75)
                data = _extract_json(raw)
                reason = check_script(data, lcfg.get("lang"))
                if reason is None:
                    data = _finish(data, lcfg)
                    data["archetype"] = archetype
                    if cfg.get("polish", True):
                        data = _polish(data, system, base, fn, model, lcfg)
                    return data
                feedback = (f"\n\nYOUR PREVIOUS ANSWER WAS REJECTED: {reason}. "
                            f"Fix exactly that and return the full JSON again.")
                _dump(f"{slug}_{model.replace('/', '-')}_{attempt}", raw)
                errors.append(f"{model}#{attempt + 1}: {reason}")
            except Exception as e:
                if raw:
                    _dump(f"{slug}_{model.replace('/', '-')}_{attempt}", raw)
                errors.append(f"{model}#{attempt + 1}: {e}")
                break
    raise RuntimeError("script writing failed -> " + " | ".join(errors))


ROLES = {"hook", "fact", "rehook", "payoff", "loop"}
MOODS = {"shock", "urgent", "excited", "curious", "calm", "serious"}
_STRIP = ".,!?।…\"'“”‘’():;-"


def _direct(d):
    """Make the director fields safe whatever the model returned: valid roles and moods,
    slam words that really are in their line, short stats, never more than the budget."""
    beats = d["beats"]
    n = len(beats)
    for i, b in enumerate(beats):
        role = str(b.get("role", "")).strip().lower()
        if i == 0:
            role = "hook"
        elif i == n - 1:
            role = "loop"
        elif i == n - 2:
            role = "payoff"
        elif role not in ROLES or role in ("hook", "loop", "payoff"):
            role = "fact"
        b["role"] = role
        mood = str(b.get("mood", "")).strip().lower()
        b["mood"] = mood if mood in MOODS else ""
    if not any(b["role"] == "rehook" for b in beats) and n >= 5:
        beats[n // 2]["role"] = "rehook"  # the turn the retention curve needs
    slams, stats = 0, 0
    for i, b in enumerate(beats):
        words = [w.strip(_STRIP) for w in b["line"].split()]
        sl = str(b.get("slam") or "").strip().strip(_STRIP)
        if i == 0 or sl not in words or slams >= 3:
            b.pop("slam", None)
        else:
            b["slam"] = sl
            slams += 1
        st = str(b.get("stat") or "").strip()
        if i == 0 or not st or len(st) > 12 or stats >= 2:
            b.pop("stat", None)
        else:
            b["stat"] = st
            stats += 1


def _seo_tags(d, lcfg):
    """YouTube tags: the model's real search phrases first, then hashtag words, deduplicated
    and kept inside the 500-character tag budget."""
    out, seen, total = [], set(), 0
    cands = [str(t).strip() for t in d.get("search_terms", []) if isinstance(t, str)]
    cands += [t.lstrip("#") for t in d.get("hashtags", [])]
    cands += ["shorts", "tech news", "telugu" if lcfg["lang"] == "te" else "hindi"]
    for t in cands:
        k = t.lower()
        if not t or k in seen or len(t) > 60:
            continue
        if total + len(t) + 1 > 480:
            break
        seen.add(k)
        out.append(t)
        total += len(t) + 1
    return out


def _finish(d, lcfg):
    """Derive the fields the rest of the pipeline reads."""
    for b in d["beats"]:
        b["line"] = b["line"].strip()
        if b["line"][-1] not in ".?!।…":
            b["line"] += "."  # terminal punctuation gives the TTS a natural pause per beat
    lines = [b["line"] for b in d["beats"]]
    d["script"] = " ".join(lines)
    d["shots"] = [b["shot"].strip() for b in d["beats"]]
    # Split on whitespace, not \w: Python's \w breaks Devanagari/Telugu words at vowel signs.
    strip = ".,!?।…\"'“”‘’():;-"
    words = set(w.strip(strip) for l in lines for w in l.split())
    d["emphasis"] = [w.strip(strip) for w in d.get("emphasis", [])
                     if isinstance(w, str) and w.strip(strip) in words][:8]
    tags = []
    for t in d.get("hashtags", []):
        t = str(t).strip()
        if t and not t.startswith("#"):
            t = "#" + t.replace(" ", "")
        if t and t not in tags:
            tags.append(t)
    if "#shorts" not in [t.lower() for t in tags]:
        tags.insert(0, "#shorts")
    d["hashtags"] = tags[:8]
    _direct(d)
    d["tags"] = _seo_tags(d, lcfg)
    d.setdefault("description", d["title"])
    d.setdefault("ig_caption", d["title"] + "\n\n" + " ".join(d["hashtags"][:5]))
    return d


SYS_POLISH = """You are a ruthless retention editor for {lang_name} Shorts. Below is a draft
script as JSON. Improve ONLY the wording of the "line" fields: cut every filler word, make the
hook hit harder in fewer words, make each beat start with its strongest word, sharpen the
re-hook and the payoff, and keep it sounding like a native speaker talking to a friend.
Keep: the same number of beats, the same facts, the same roles/moods/shots/slam/stat fields,
native script only (no Latin letters), hook <= 8 words, a closing question. Do not add facts.
Return the FULL JSON again with the same keys. ONLY raw JSON."""


def _polish(d, system, base, fn, model, lcfg):
    """One critic pass. If its output breaks any rule we keep the original: polishing may
    only ever improve a script, never lose one."""
    try:
        slim = {k: d[k] for k in ("title", "hook_text", "beats", "emphasis", "description",
                                  "ig_caption", "hashtags", "search_terms") if k in d}
        raw = fn(SYS_POLISH.format(lang_name=LANG_NAME.get(lcfg["lang"], lcfg["lang"])),
                 json.dumps(slim, ensure_ascii=False), model, 0.5)
        cand = _extract_json(raw)
        if check_script(cand, lcfg.get("lang")) is None and len(cand["beats"]) == len(d["beats"]):
            cand = _finish(cand, lcfg)
            cand["archetype"] = d.get("archetype")
            print("  polish pass applied")
            return cand
        print("  polish pass rejected by validator, keeping original")
    except Exception as e:
        print(f"  polish pass failed ({str(e)[:60]}), keeping original")
    return d


def pick_layout(used_recently, layouts):
    """Rotate layouts so one channel does not look templated from video to video."""
    available = [l for l in layouts if l not in used_recently[-3:]]
    return random.choice(available or layouts)
