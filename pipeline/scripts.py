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

SYS_WRITE = """You write 30-40 second vertical-video scripts that win on RETENTION, for
people who will watch in {lang_name} and nothing else.
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
 "beats": [{{"line": "one spoken sentence", "shot": "2-3 English words for a photo search"}}],
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
    "te": """Write PURE, everyday spoken Telugu (వాడుక భాష) as a Telugu person from Andhra or
Telangana would say it to a friend. Think in Telugu; never translate from English.
Prefer native Telugu words over English ones whenever a natural one exists
(ఉచితంగా, డబ్బు, ఉద్యోగం, ఖాతా, జాగ్రత్త, తెలుసా). Use natural spoken endings and rhythm
(-తోంది, -తున్నారు, "ఏంటో తెలుసా?", "చూడండి", "వినండి"). Short sentences. No Hindi or English
words mixed in. Good hook shapes (do not copy, match the energy):
  "మీ ఫోన్‌లో ఈ ఒక్క సెట్టింగ్ మీ డబ్బు తినేస్తోంది!"
  "గూగుల్ ఇది ఉచితంగా ఇస్తోంది, కానీ ఎందుకో తెలుసా?"
  "ఈ ఒక్క తప్పుతో మీ ఖాతా ఖాళీ అవుతుంది!"
""",
    "hi": """Write PURE, everyday spoken Hindi (रोज़ की बोलचाल की हिंदी) as you would say it to a
friend. Think in Hindi; never translate from English. This is NOT Hinglish: use Hindi
words wherever a natural one exists (मुफ़्त, पैसा, नौकरी, खाता, ख़बर, सावधान, जानते हैं).
Short sentences, natural spoken rhythm. No English words mixed in. Good hook shapes (do
not copy, match the energy):
  "आपके फ़ोन की ये एक सेटिंग आपका पैसा खा रही है!"
  "गूगल ये मुफ़्त दे रहा है, पर क्यों?"
  "सावधान! ये एक गलती और आपका खाता खाली!"
""",
    "en": "Write plain, punchy spoken English.",
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


def write_script(story, angle, lcfg, cfg, note=""):
    """Write the picked angle natively for one channel. Retries feed the exact failure
    back to the model so the second attempt fixes the specific rule that was broken."""
    system = SYS_WRITE.format(lang_name=LANG_NAME.get(lcfg["lang"], lcfg["lang"]),
                              style=LANG_STYLE.get(lcfg["lang"], ""),
                              brand=lcfg["brand"], audience=lcfg["audience"].replace("_", " "))
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
                    return _finish(data, lcfg)
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
    d.setdefault("description", d["title"])
    d.setdefault("ig_caption", d["title"] + "\n\n" + " ".join(d["hashtags"][:5]))
    return d


def pick_layout(used_recently, layouts):
    """Rotate layouts so one channel does not look templated from video to video."""
    available = [l for l in layouts if l not in used_recently[-3:]]
    return random.choice(available or layouts)
