"""Rate-limit circuit breakers + deterministic beat normalisation."""
import math, os, re, time

MAX_BEATS = 9
MAX_WORDS = 9
MAX_HOOK = 6
MIN_TOTAL = 55

FILLER = {
    "hi": ["बहुत", "ही", "भी", "तो", "बस", "कुछ", "और", "यही", "वही", "अब", "ज़रा", "सच", "असल"],
    "te": ["చాలా", "కూడా", "అయితే", "కొంచెం", "మరి", "ఇదే", "అదే", "నిజంగా", "అసలు"],
    "en": ["very", "really", "just", "actually", "basically", "quite", "totally", "now"],
}
KEEP_RE = re.compile(r"[0-9₹%?]|మీ|నీ|మీరు|आप|तुम|your|you", re.I)


def _is_tpd(msg):
    m = msg.lower()
    return "tokens per day" in m or "tpd" in m or "per day" in m


def _retry_secs(msg, default=0.0):
    m = re.search(r"try again in\s+(?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", msg, re.I)
    if m:
        h = int(m.group(1) or 0); mi = int(m.group(2) or 0); s = float(m.group(3) or 0)
        return h * 3600 + mi * 60 + s
    m = re.search(r"retry in\s+([\d.]+)s", msg, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r'retryDelay"?\s*:\s*"?(\d+)', msg)
    if m:
        return float(m.group(1))
    return default


def _trim(words, limit, lang):
    """Drop filler first, never numbers or second-person words."""
    if len(words) <= limit:
        return words, 0
    fill = set(FILLER.get(lang, []))
    out = list(words)
    i = len(out) - 1
    while len(out) > limit and i >= 0:
        w = out[i].strip(".,!?।…\"'“”‘’():;-–—")
        if w in fill and not KEEP_RE.search(w):
            out.pop(i)
        i -= 1
    dropped = len(words) - len(out)
    if len(out) > limit:
        prot = [w for w in out if KEEP_RE.search(w)]
        keep = out[:limit]
        for w in prot:
            if w not in keep:
                keep[-1] = w
        dropped += len(out) - len(keep)
        out = keep
    return out, dropped


def normalize(d, lang):
    """Split/trim beats so they can never fail a word-count rule. Mutates d."""
    beats = d.get("beats")
    if not isinstance(beats, list) or not beats:
        return []
    log = []
    shots = set()

    def uniq(base):
        base = str(base or "tech closeup").strip().lower()
        mods = ["closeup", "detail", "macro", "wide", "angle", "topview"]
        cand, i = base, 0
        while cand in shots:
            w = base.split()
            m = mods[i % len(mods)]
            cand = " ".join(w[:-1] + [m]) if len(w) >= 4 else base + " " + m
            i += 1
            if i > 12:
                cand = base + " s" + str(i)
        shots.add(cand)
        return cand

    out = []
    for bi, b in enumerate(beats):
        if not isinstance(b, dict):
            continue
        line = str(b.get("line", "")).strip()
        words = line.split()
        n = len(words)
        remaining = len(beats) - bi - 1
        room = MAX_BEATS - len(out) - remaining
        k = max(1, min(math.ceil(n / MAX_WORDS), room)) if n > MAX_WORDS else 1
        if k <= 1:
            nb = dict(b)
            nb["shot"] = uniq(b.get("shot"))
            out.append(nb)
            continue
        size = math.ceil(n / k)
        chunks = [words[i:i + size] for i in range(0, n, size)]
        for ci, ch in enumerate(chunks):
            nb = dict(b)
            nb["line"] = " ".join(ch)
            nb["shot"] = uniq(b.get("shot"))
            if ci:
                nb["role"] = "fact"
                nb.pop("slam", None)
                nb.pop("stat", None)
            out.append(nb)
        log.append("beat " + str(bi) + " split " + str(n) + "w into " + str(len(chunks)))

    total = sum(len(str(b.get("line", "")).split()) for b in out)
    for b in out:
        w = str(b.get("line", "")).split()
        if len(w) <= MAX_WORDS:
            continue
        kept, dropped = _trim(w, MAX_WORDS, lang)
        if dropped and total - dropped >= MIN_TOTAL:
            b["line"] = " ".join(kept)
            total -= dropped
            log.append("trimmed " + str(dropped) + "w")

    hook = str(d.get("hook_text", "")).strip()
    hw = hook.split()
    if len(hw) > MAX_HOOK:
        kept, dr = _trim(hw, MAX_HOOK, lang)
        if dr:
            d["hook_text"] = " ".join(kept)
            log.append("hook_text " + str(len(hw)) + "->" + str(len(kept)))

    first = str(out[0].get("line", "")).split()
    if len(first) > MAX_HOOK:
        kept, dr = _trim(first, MAX_HOOK, lang)
        if dr:
            out[0]["line"] = " ".join(kept)
            log.append("hook beat ->" + str(len(kept)) + "w")

    d["beats"] = out
    if log:
        print("  normalised: " + "; ".join(log[:4]), flush=True)
    return log


class Breaker:
    def __init__(self):
        self.dead_until = 0.0
        self.reason = ""

    def open_for(self, secs, reason):
        self.dead_until = max(self.dead_until, time.time() + max(30.0, secs))
        self.reason = reason
        print("  [breaker] Groq paused " + str(int(secs / 60)) + "m (" + reason + ")", flush=True)

    def check(self):
        if time.time() < self.dead_until:
            raise RuntimeError("groq quota exhausted, skipping (" + self.reason + ")")


GROQ = Breaker()
_last_gemini = [0.0]


def wrap(scripts_mod):
    """Install breakers + throttle + normaliser onto the live scripts module."""
    if getattr(scripts_mod, "_flowfix", False):
        return
    scripts_mod._flowfix = True

    prev_groq = scripts_mod._groq
    prev_gemini = scripts_mod._gemini
    prev_check = scripts_mod.check_script

    def groq(system, prompt, model, temperature=0.7):
        GROQ.check()
        try:
            return prev_groq(system, prompt, model, temperature)
        except Exception as e:
            msg = str(e)
            if _is_tpd(msg):
                GROQ.open_for(_retry_secs(msg, 1800), "TPD")
                raise RuntimeError("groq TPD exhausted") from None
            raise

    def gemini(system, prompt, model, temperature=0.7):
        gap = float(os.getenv("GEMINI_MIN_INTERVAL", "2.0"))
        wait = gap - (time.time() - _last_gemini[0])
        if wait > 0:
            time.sleep(wait)
        delay = 3.0
        for attempt in range(4):
            _last_gemini[0] = time.time()
            try:
                return prev_gemini(system, prompt, model, temperature)
            except Exception as e:
                msg = str(e)
                if "429" not in msg and "Too Many Requests" not in msg:
                    raise
                if attempt == 3:
                    raise
                d = _retry_secs(msg, delay)
                d = min(60.0, max(2.0, d))
                print("    gemini 429, waiting " + str(int(d)) + "s", flush=True)
                time.sleep(d)
                delay *= 2
        raise RuntimeError("gemini retries exhausted")

    def check(d, lang=None):
        if isinstance(d, dict) and isinstance(d.get("beats"), list):
            original_error = prev_check(d, lang)
            if original_error and original_error.startswith("hook is "):
                return original_error
            normalize(d, lang or "en")
        return prev_check(d, lang)

    scripts_mod._groq = groq
    scripts_mod._gemini = gemini
    scripts_mod.check_script = check
    print("[flowfix] beat normaliser + groq breaker + gemini throttle active", flush=True)
