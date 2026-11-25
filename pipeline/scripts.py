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

from pipeline import retention as R
from pipeline import langfix as L
from pipeline.provider_keys import gemini_keys, groq_keys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Script constraints are shared by the prompt, validator, and render retry.
HOOK_MAX_WORDS = R.MAX_HOOK_WORDS
HOOK_MAX_SECONDS = R.MAX_HOOK_SEC
HOOK_CARD_MIN_WORDS = 2
HOOK_CARD_MAX_WORDS = 5
BEAT_MIN_WORDS = 5
BEAT_MAX_WORDS = R.MAX_BEAT_WORDS
MIN_BEATS = 6
MAX_BEATS = 9
SCRIPT_MIN_WORDS = R.TOTAL_WORDS[0]
SCRIPT_MAX_WORDS = R.TOTAL_WORDS[1]
STORY_FORMATS = {"explainer", "list", "versus", "timeline"}

# ---------------------------------------------------------------- stage 1: angles

SYS_ANGLES = """You are the head of content for an Indian tech Shorts channel.
For the SOURCE story, propose 3 DISTINCT angles. Each angle is a different reason a viewer
would care, not a rewording of the same headline. Pick from: verified money/jobs impact on
an Indian viewer, a change to something they use daily, an important qualification, what
the source says happens next, or a myth the source can actually disprove. Never manufacture
urgency, conflict, or a hidden motive.

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

SYS_WRITE = """You are a {lang_name} YouTuber who makes useful, engaging Shorts. Viewers decide quickly
whether to stay, so open with a specific, factual reason to care rather than manufactured
shock or urgency.

You THINK in {lang_name}. You never translate from English. You speak like a friend
explaining something genuinely interesting to another person.

Channel: "{brand}". Audience: {audience}.
Editorial identity: {editorial_identity}

STORY STRUCTURE:
Build one clear claim, support it with three distinct facts from the source, then explain
what those facts mean. The payoff must answer the question raised by the hook. Do not invent
stakes, force shock, or repeat the same point to fill time.

LANGUAGE (the most important rule):
{style}
Write primarily in the native script, but keep technical terms, acronyms, and brand names
in Latin exactly as commonly written (for example: FSSAI, Bromate, AI, Google). Do not
invent native-script spellings for English technical terms.

Return STRICT JSON:
{{
 "title": "<=60 chars, native script, a curiosity gap or a concrete stake, never a summary.
           If a TRENDING_SEARCH is given and fits, include it the way people type it.",
 "claim": "the video's single, concise, source-backed claim",
 "supporting_facts": ["three distinct concise facts from KEY_FACTS that support the claim"],
 "hook_text": "{hook_card_min_words}-{hook_card_max_words} native words shown huge on screen",
 "story_format": "explainer | list | versus | timeline",
 "cta_text": "a brief, topic-specific native-language question or invitation to share an experience",
 "cta_screen": "<=9 words, concrete asset plus channel follow reason",
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

HOOK (beats[0]) — the entire game lives here:
- {hook_max_words} words MAX. Spoken in under {hook_max_seconds} seconds. NEVER start with
  "today" or a greeting.
- Make a concrete, accurate promise or ask a question the story will answer. Do not inflate
  the stakes or imply danger not supported by the source.
- Speak TO them: "మీరు", "आप", using their direct address always.

EVIDENCE (middle beats):
- Give at least three distinct source-backed facts that support the claim.
- Keep each fact concrete, and make the connection to the claim clear.

RE-HOOK (middle beat, role="rehook"):
- Introduce a useful qualification, consequence, or detail that changes how the claim reads.
- Do not manufacture a twist or imply a fact the source does not establish.

PAYOFF (beats[-2], role="payoff"):
- Explain the practical takeaway and answer the question the hook opened.

LOOP (beats[-1], role="loop"):
- Ask a specific, relevant question viewers can answer from their experience or opinion.

HOOK ARCHETYPE for this video: {archetype}

DIRECTION (this drives voice, sound and screen, so use it deliberately):
- role: beats[0]="hook", one middle beat="rehook", beats[-2]="payoff", beats[-1]="loop",
  the rest "fact".
- mood: use "urgent" only for a real deadline; otherwise choose a delivery that fits the
  facts. The payoff is "serious" or "calm"; do not force shock into every story.
- slam: on at most 3 beats (never the hook), the single most powerful word. stat: on at
  most 2 beats, only a real number or a 2-word claim that is in the source.
- Never say "subscribe" or "follow" inside the lines; the screen handles that.

STYLE:
- {min_beats} to {max_beats} beats, each {beat_min_words} to {beat_max_words} words.
  Total {script_min_words}-{script_max_words} words. Short, clear sentences.
- Every beat gives NEW information or a new emotion. No filler, no recap.
- Use ONLY facts from KEY_FACTS and SOURCE. Never invent numbers, quotes or dates.
- 'shot' is a PHOTO search: a concrete, photogenic subject that matches the
  line, such as "smartphone in hand", "indian street night", "server room", "stock market
  screen", "student laptop". No abstract words, no brand names, no people's names. Add
  "india" when a local feel helps. Never repeat a shot query.

Return ONLY raw JSON. No markdown, no code fences."""

SYS_WRITE = SYS_WRITE + R.PROMPT_RULES

LANG_NAME = {"hi": "Hindi (Devanagari)", "te": "Telugu (Telugu script)", "en": "English"}

LANG_STYLE = {
    "te": """భాష నియమాలు (Language Rules — Telugu):
You are a Telugu content creator from Andhra Pradesh who has been making YouTube videos
for 5 years. You THINK in Telugu. You do NOT translate.

VOICE: Sound like you're naturally explaining something useful or surprising to a friend.
Use real Andhra Telugu rhythm; do not make every story sound alarming.

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
Hook (clear, 5-6 short words) → Fact 1 (medium, concrete) → Fact 2 (medium) →
RE-HOOK (slow down, pause word + fast restart) → Payoff (slow, serious) → Loop (question, conversational)

NATIVE WORD PREFERENCES:
డబ్బు (not ధనం), ఉద్యోగం (not వృత్తి), ఉచితంగా (not రుసుము లేకుండా),
జాగ్రత్త (not హెచ్చరిక), తెలుసా (not అవగాహన కలిగి ఉన్నారా)
""",
    "hi": """भाषा नियम (Language Rules — Hindi):
आप एक Hindi content creator हैं जो 5 साल से YouTube Shorts बना रहे हैं।
आप Hindi में सोचते हैं। आप translate नहीं करते।

VOICE: जैसे आप अपने दोस्त को कोई दिलचस्प या काम की बात बता रहे हों — natural और साफ़।

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
Hook (साफ़, 5-6 छोटे शब्द) → Fact 1 (normal speed, concrete) → Fact 2 →
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
    kwargs = {}
    if "gpt-oss" in model:
        kwargs["extra_body"] = {"reasoning_effort": "medium"}
    keys = groq_keys()
    if not keys:
        raise RuntimeError("GROQ_API_KEY is not configured")

    last_error = None
    for index, key in enumerate(keys):
        try:
            c = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1", timeout=60)
            result = _with_retry(lambda: c.chat.completions.create(
                model=model, temperature=temperature, max_tokens=4000,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}], **kwargs
            ).choices[0].message.content)
            if index:
                print("  Groq backup key succeeded", flush=True)
            return result
        except (requests.HTTPError, APIStatusError) as error:
            last_error = error
            if index + 1 < len(keys):
                print(f"  Groq primary key failed ({_status_of(error) or 'error'}), "
                      "trying backup key...", flush=True)
                continue
            raise
    raise last_error


def _gemini(system, prompt, model, temperature=0.7, timeout=60):
    def call():
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": key},
            json={"contents": [{"parts": [{"text": system + "\n\n" + prompt}]}],
                  "generationConfig": {"responseMimeType": "application/json",
                                       "temperature": temperature}},
            timeout=timeout)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    keys = gemini_keys()
    if not keys:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    for index, key in enumerate(keys):
        try:
            result = _with_retry(call)
            if index:
                print("  Gemini backup key succeeded", flush=True)
            return result
        except requests.HTTPError as error:
            if index + 1 == len(keys):
                raise
            print(f"  Gemini key {index + 1} failed ({_status_of(error) or 'error'}), "
                  "trying backup key...", flush=True)


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
    if not isinstance(beats, list) or not (MIN_BEATS <= len(beats) <= MAX_BEATS):
        return (f"need {MIN_BEATS}-{MAX_BEATS} beats, got "
                f"{len(beats) if isinstance(beats, list) else 'none'}")
    lines = []
    shots = set()
    for i, b in enumerate(beats):
        if not isinstance(b, dict) or not str(b.get("line", "")).strip():
            return f"beat {i} has no line"
        n = len(b["line"].split())
        if n < BEAT_MIN_WORDS or n > BEAT_MAX_WORDS:
            return f"beat {i} has {n} words (need {BEAT_MIN_WORDS}-{BEAT_MAX_WORDS})"
        shot = str(b.get("shot", "")).strip().lower()
        if not shot:
            return f"beat {i} has no shot"
        if shot in shots:
            return f"beat {i} repeats shot '{shot}'"
        shots.add(shot)
        lines.append(b["line"])
    hook_words = len(lines[0].split())
    if hook_words > HOOK_MAX_WORDS:
        return (f"hook is {hook_words} words (need <={HOOK_MAX_WORDS}, "
                f"it must be spoken in {HOOK_MAX_SECONDS} s)")
    total = sum(len(l.split()) for l in lines)
    if not (SCRIPT_MIN_WORDS <= total <= SCRIPT_MAX_WORDS):
        return f"script is {total} words (need {SCRIPT_MIN_WORDS}-{SCRIPT_MAX_WORDS})"
    if not any("?" in l for l in lines[-2:]):
        return "no closing question in the last two beats"
    if not str(d.get("title", "")).strip():
        return "missing title"
    if len(str(d["title"])) > 100:
        return "title too long"
    if not str(d.get("claim", "")).strip():
        return "missing central claim"
    supporting_facts = d.get("supporting_facts")
    if not isinstance(supporting_facts, list) or len(supporting_facts) != 3 or any(
        not str(fact).strip() for fact in supporting_facts
    ):
        return "need exactly 3 source-backed supporting_facts"
    if not str(d.get("hook_text", "")).strip():
        return "missing hook_text"
    hook_card_words = len(str(d["hook_text"]).split())
    if not (HOOK_CARD_MIN_WORDS <= hook_card_words <= HOOK_CARD_MAX_WORDS):
        return (f"hook_text has {hook_card_words} words (need "
                f"{HOOK_CARD_MIN_WORDS}-{HOOK_CARD_MAX_WORDS})")
    if d.get("story_format") not in STORY_FORMATS:
        return "story_format must be explainer, list, versus, or timeline"
    if not str(d.get("cta_text", "")).strip():
        return "missing topic-specific cta_text"
    retention_reason = R.gates(d, lang)
    if retention_reason:
        return retention_reason
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
                              editorial_identity=lcfg.get("editorial_identity", lcfg["audience"]),
                              archetype=f"{archetype}: {HOOK_ARCHETYPES.get(archetype, '')}",
                              hook_max_words=HOOK_MAX_WORDS,
                              hook_max_seconds=HOOK_MAX_SECONDS,
                              hook_card_min_words=HOOK_CARD_MIN_WORDS,
                              hook_card_max_words=HOOK_CARD_MAX_WORDS,
                              min_beats=MIN_BEATS, max_beats=MAX_BEATS,
                              beat_min_words=BEAT_MIN_WORDS, beat_max_words=BEAT_MAX_WORDS,
                              script_min_words=SCRIPT_MIN_WORDS,
                              script_max_words=SCRIPT_MAX_WORDS)
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
                    data = L.repair_script(data, lcfg.get("lang"), story)
                    data = L.judge(data, lcfg.get("lang"))
                    retention_reason = R.gates(data, lcfg.get("lang"))
                    if retention_reason:
                        feedback = (
                            "\n\nYOUR LANGFIX/JUDGE OUTPUT WAS REJECTED: "
                            f"{retention_reason}. Fix exactly that and return the full JSON."
                        )
                        print(f"  post-language gate rejected: {retention_reason}", flush=True)
                        _dump(f"{slug}_{model.replace('/', '-')}_langfix", raw)
                        continue
                    retention_score, retention_notes = R.score(data, lcfg.get("lang"))
                    print(
                        f"  retention {retention_score}/100 [{R.verdict(retention_score)}]"
                        + (f" :: {', '.join(retention_notes)}" if retention_notes else ""),
                        flush=True,
                    )
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
    for beat in d["beats"]:
        beat["line"] = beat["line"].strip()
        if beat["line"][-1] not in ".?!।…":
            beat["line"] += "."
    lines = [beat["line"] for beat in d["beats"]]
    d["script"] = " ".join(lines)
    d["shots"] = [beat["shot"].strip() for beat in d["beats"]]
    strip = ".,!?।…\"'“”‘’():;-"
    words = set(word.strip(strip) for line in lines for word in line.split())
    d["emphasis"] = [word.strip(strip) for word in d.get("emphasis", [])
                     if isinstance(word, str) and word.strip(strip) in words][:8]
    tags = []
    for tag in d.get("hashtags", []):
        tag = str(tag).strip()
        if tag and not tag.startswith("#"):
            tag = "#" + tag.replace(" ", "")
        if tag and tag not in tags:
            tags.append(tag)
    if "#shorts" not in [tag.lower() for tag in tags]:
        tags.insert(0, "#shorts")
    d["hashtags"] = tags[:8]
    _direct(d)
    d["tags"] = _seo_tags(d, lcfg)
    if d.get("story_format") not in STORY_FORMATS:
        d["story_format"] = "explainer"
    d.setdefault("cta_text", lcfg.get("cta", ""))
    d.setdefault("cta_screen", d["cta_text"])
    base_title = str(d.get("title", "")).strip()
    yt_hashtags = str(lcfg.get("yt_hashtags", "")).strip()
    if yt_hashtags and len(base_title) + 1 + len(yt_hashtags) <= 100:
        d["title_with_hashtags"] = f"{base_title} {yt_hashtags}"
    else:
        d["title_with_hashtags"] = base_title
    d.setdefault("description", d["title"])
    ig_hashtags = lcfg.get("ig_hashtags", " ".join(d["hashtags"][:5]))
    d.setdefault("ig_caption",
                 d["title"] + "\n\n" + "\n".join(lines[:2]) + "\n\n" + ig_hashtags)
    return d


SYS_POLISH = """You are a careful editor for {lang_name} Shorts. Below is a draft script as
JSON. Improve ONLY the wording of the "line" fields for clarity and natural delivery.
Keep: claim, supporting_facts, the same number of beats, the same facts,
roles/moods/shots/slam/stat fields, story_format, cta_text, and the original language.
Keep standard technical terms, acronyms, and brand names in Latin. Hook <= {hook_max_words}
words, and a closing question. Do not add facts.
Return the FULL JSON again with the same keys. ONLY raw JSON."""


def _polish(d, system, base, fn, model, lcfg):
    """One critic pass. If its output breaks any rule we keep the original: polishing may
    only ever improve a script, never lose one."""
    try:
        slim = {k: d[k] for k in ("title", "claim", "supporting_facts", "hook_text",
                                  "beats", "emphasis", "description",
                                  "ig_caption", "hashtags", "search_terms", "story_format",
                                  "cta_text", "cta_screen") if k in d}
        raw = fn(SYS_POLISH.format(lang_name=LANG_NAME.get(lcfg["lang"], lcfg["lang"]),
                                   hook_max_words=HOOK_MAX_WORDS),
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


def pick_layout(used_recently, layouts, preferred=None):
    """Prefer a layout that fits the story, without repeating recent treatments."""
    available = [l for l in layouts if l not in used_recently[-3:]]
    if preferred in available:
        return preferred
    return random.choice(available or layouts)


# === GULU TITLES ===
from pipeline import titles as _T

_gulu_prev_write = write_script
def write_script(story, angle, lcfg, cfg, note="", archetype="stake"):
    d = _gulu_prev_write(story, angle, lcfg, cfg, note=note, archetype=archetype)
    d, rep = _T.harden(
        d, lcfg.get("lang", "en"),
        brand=lcfg.get("brand", ""), handle=lcfg.get("handle", ""),
        link=cfg.get("bio_link", "") or lcfg.get("bio_link", ""),
        source_url=story.get("url", ""),
    )
    print("  titles hardened: " + str(d["title_len"]) + " chars, fold " + str(d["fold_len"])
          + (" | " + ", ".join(rep) if rep else ""), flush=True)
    return d

# === FLOWFIX ===
from pipeline import flowfix as _FF
_FF.wrap(__import__(__name__, fromlist=["x"]))
