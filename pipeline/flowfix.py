"""Rate-limit breakers + deterministic beat/shot normalisation. v2"""
import math
import os
import re
import time

MIN_WORDS, MAX_WORDS = 5, 9
MIN_BEATS, MAX_BEATS = 6, 9
HOOK_MIN, HOOK_MAX = 5, 6
MIN_TOTAL = 50

CONCRETE = set("""screen display monitor chart graph phone laptop keyboard server room desk hand hands
bottle label tag board street shop office student crowd car bike road building tower antenna cable chip
camera battery charger wallet note coin receipt card machine robot drone satellite dish telescope tube
lab factory warehouse truck port bridge meter gauge dial button switch plug socket tablet watch speaker
mic headphone rupees price newspaper document file folder laptop""".split())

FILLER = {
    "hi": ["बहुत", "ही", "भी", "तो", "बस", "कुछ", "और", "यही", "वही", "अब", "ज़रा"],
    "te": ["చాలా", "కూడా", "అయితే", "కొంచెం", "మరి", "ఇదే", "అదే", "నిజంగా"],
    "en": ["very", "really", "just", "actually", "basically", "quite", "totally"],
}
KEEP_RE = re.compile(r"[0-9₹%?]|మీ|నీ|మీరు|आप|तुम|your|you", re.I)

LOANWORDS = set("""స్క్రీన్ డ్రాఫ్ట్ ఫ్లెక్సిబుల్ ఫోన్ యాప్ డేటా నెట్‌వర్క్ సర్వర్ సాఫ్ట్‌వేర్ హార్డ్‌వేర్
కంప్యూటర్ ల్యాప్‌టాప్ టెక్నాలజీ ఇంటర్నెట్ వెబ్‌సైట్ బ్రౌజర్ కెమెరా బ్యాటరీ చార్జర్ డిస్‌ప్లే ప్రాసెసర్
మెమరీ స్టోరేజ్ క్లౌడ్ కోడ్ ప్రోగ్రామ్ సిస్టమ్ అప్‌డేట్ వర్షన్ ఫీచర్ సెట్టింగ్ పాస్‌వర్డ్ అకౌంట్ లాగిన్
లింక్ క్లిక్ షేర్ పోస్ట్ వీడియో ఆడియో మెసేజ్ చాట్ గ్రూప్ ఛానల్ సబ్‌స్క్రైబ్ ఫాలో లైక్ కామెంట్
నోటిఫికేషన్ బ్యాంక్ పేమెంట్ ట్రాన్సాక్షన్ ఆన్‌లైన్ ఆఫ్‌లైన్ డిజిటల్ మార్కెట్ ప్రైస్ డీల్ ఆఫర్
డిస్కౌంట్ బడ్జెట్ కంపెనీ స్టార్టప్ జాబ్ శాలరీ ప్రాజెక్ట్ టీమ్ మీటింగ్ రిపోర్ట్ టెస్ట్ రిజల్ట్ స్కోర్
ర్యాంక్ లిస్ట్ బ్రాండ్ మోడల్ డిజైన్ కలర్ సైజ్ స్పీడ్ పవర్ ఛార్జ్ కనెక్షన్ సిగ్నల్ వైఫై బ్లూటూత్
జీపీఎస్ ఏఐ రోబోట్ డ్రోన్ సెన్సార్ చిప్ గేమ్ గేమింగ్ స్ట్రీమ్ డౌన్‌లోడ్ అప్‌లోడ్ ఫైల్ ఫోల్డర్
స్క్రీన్‌షాట్ బ్యాకప్ సెక్యూరిటీ ప్రైవసీ హ్యాక్ స్కామ్ ఫేక్ న్యూస్ అలర్ట్ వార్నింగ్ రూల్
స్क्रీన్ డ్రాఫ్ట్ ఫ్లెక్సిబుల్ టార్గెట్ రివ్యూ రేటింగ్ ప్లాన్ ట్రెండ్ వైరల్""".split())

_TE_C = dict(zip("కఖగఘఙచఛజఝఞటఠడఢణతథదధనపఫబభమయరలవళశషసహఱ",
    ["k", "kh", "g", "gh", "n", "c", "ch", "j", "jh", "n", "t", "th", "d", "dh", "n",
     "t", "th", "d", "dh", "n", "p", "ph", "b", "bh", "m", "y", "r", "l", "v", "l",
     "sh", "sh", "s", "h", "r"]))
_TE_M = {"ా": "a", "ి": "i", "ీ": "i", "ు": "u", "ూ": "u", "ృ": "r", "ె": "e",
         "ే": "e", "ై": "ai", "ొ": "o", "ో": "o", "ౌ": "au", "ం": "m", "ః": "h"}
_EN = """screen draft flexible phone app data network server software hardware computer laptop technology
internet website browser camera battery charger display processor memory storage cloud code program system
update version feature setting password account login link click share post video audio message chat group
channel subscribe follow like comment notification bank payment transaction online offline digital market
price deal offer discount budget company startup job salary project team meeting report test result score
rank list brand model design color size speed power charge connection signal wifi bluetooth gps robot drone
sensor chip game gaming stream download upload file folder screenshot backup security privacy hack scam fake
news alert warning rule target review rating plan trend viral""".split()
_SKEL = {re.sub(r"[aeiou]", "", word) for word in _EN}


def _to_latin(token):
    output, index = [], 0
    while index < len(token):
        char = token[index]
        if char in _TE_C:
            base = _TE_C[char]
            following = token[index + 1] if index + 1 < len(token) else ""
            if following == "\u0c4d":
                output.append(base)
                index += 2
                continue
            if following in _TE_M:
                output.append(base + _TE_M[following])
                index += 2
                continue
            output.append(base + "a")
            index += 1
            continue
        output.append(_TE_M.get(char, ""))
        index += 1
    return "".join(output)


def smart_gibberish(text, lang):
    """Flag suspicious Telugu conjuncts, but preserve known loanwords."""
    if lang != "te":
        return []
    bad = []
    for raw in str(text).split():
        token = raw.strip(".,!?।…\"'“”‘’():;-–—")
        if not token or re.search(r"[A-Za-z0-9]", token) or token in LOANWORDS:
            continue
        if token.count("\u0c4d") < 4:
            continue
        skeleton = re.sub(r"[aeiou]", "", _to_latin(token))
        if skeleton in _SKEL:
            continue
        if any(skeleton and (skeleton in word or word in skeleton)
               for word in _SKEL if len(word) > 3):
            continue
        bad.append(token)
    return bad


def _is_tpd(message):
    message = message.lower()
    return "tokens per day" in message or "tpd" in message or "per day" in message


def _retry_secs(message, default=0.0):
    match = re.search(
        r"try again in\s+(?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", message, re.I)
    if match:
        return (int(match.group(1) or 0) * 3600
                + int(match.group(2) or 0) * 60
                + float(match.group(3) or 0))
    match = re.search(r"retry in\s+([\d.]+)s", message, re.I)
    if match:
        return float(match.group(1))
    match = re.search(r'retryDelay"?\s*:\s*"?(\d+)', message)
    return float(match.group(1)) if match else default


def _trim(words, limit, lang):
    if len(words) <= limit:
        return words, 0
    fillers = set(FILLER.get(lang, []))
    output = list(words)
    for index in range(len(output) - 1, -1, -1):
        if len(output) <= limit:
            break
        word = output[index].strip(".,!?।…\"'“”‘’():;-–—")
        if word in fillers and not KEEP_RE.search(word):
            output.pop(index)
    if len(output) > limit:
        output = output[:limit]
    return output, len(words) - len(output)


def _word_count(beat):
    return len(str(beat.get("line", "")).split())


def normalize(script, lang):
    """Repair beat length/count and make every stock-footage query concrete and unique."""
    beats = script.get("beats")
    if not isinstance(beats, list) or not beats:
        return []
    beats = [dict(beat) for beat in beats
             if isinstance(beat, dict) and str(beat.get("line", "")).strip()]
    if not beats:
        return []
    log = []

    for _ in range(40):
        index = next((i for i, beat in enumerate(beats) if _word_count(beat) < MIN_WORDS), None)
        if index is None or len(beats) <= 1:
            break
        neighbour = index + 1 if index + 1 < len(beats) else index - 1
        left, right = min(index, neighbour), max(index, neighbour)
        merged = str(beats[left]["line"]).rstrip(".।") + " " + str(beats[right]["line"])
        if len(merged.split()) <= MAX_WORDS or len(beats) > MIN_BEATS:
            combined = dict(beats[left])
            combined["line"] = merged
            combined.pop("slam", None)
            beats[left:right + 1] = [combined]
            log.append(f"merged short beat {index}")
        else:
            words = merged.split()
            cut = max(MIN_WORDS, min(len(words) - MIN_WORDS, math.ceil(len(words) / 2)))
            first, second = dict(beats[left]), dict(beats[left])
            first["line"] = " ".join(words[:cut])
            second["line"] = " ".join(words[cut:])
            second["role"] = "fact"
            second.pop("slam", None)
            second.pop("stat", None)
            beats[left:right + 1] = [first, second]
            log.append(f"rebalanced short beat {index}")

    output = []
    for index, beat in enumerate(beats):
        words = str(beat["line"]).split()
        remaining = len(beats) - index - 1
        room = MAX_BEATS - len(output) - remaining
        if len(words) > MAX_WORDS and room >= 2:
            count = min(math.ceil(len(words) / MAX_WORDS), room)
            size = math.ceil(len(words) / count)
            chunks = [words[i:i + size] for i in range(0, len(words), size)]
            for chunk_index, chunk in enumerate(chunks):
                part = dict(beat)
                part["line"] = " ".join(chunk)
                if chunk_index:
                    part["role"] = "fact"
                    part.pop("slam", None)
                    part.pop("stat", None)
                output.append(part)
            log.append(f"split {len(words)}w beat")
        elif len(words) > MAX_WORDS:
            kept, removed = _trim(words, MAX_WORDS, lang)
            part = dict(beat)
            part["line"] = " ".join(kept)
            output.append(part)
            if removed:
                log.append(f"trimmed {removed}w")
        else:
            output.append(dict(beat))
    beats = output

    if beats:
        hook = str(beats[0]["line"]).split()
        if len(hook) > HOOK_MAX and len(beats) > 1:
            move = len(hook) - HOOK_MAX
            following = str(beats[1]["line"]).split()
            if len(following) + move <= MAX_WORDS:
                beats[0]["line"] = " ".join(hook[:HOOK_MAX])
                beats[1]["line"] = " ".join(hook[HOOK_MAX:] + following)
                log.append(f"hook -> {HOOK_MAX}w")
        elif len(hook) > HOOK_MAX:
            kept, removed = _trim(hook, HOOK_MAX, lang)
            beats[0]["line"] = " ".join(kept)
            if removed:
                log.append("hook trimmed")
        hook = str(beats[0]["line"]).split()
        if len(hook) < HOOK_MIN and len(beats) > 1:
            following = str(beats[1]["line"]).split()
            needed = HOOK_MIN - len(hook)
            if len(following) - needed >= MIN_WORDS:
                beats[0]["line"] = " ".join(hook + following[:needed])
                beats[1]["line"] = " ".join(following[needed:])
                log.append(f"hook padded to {HOOK_MIN}w")

    while len(beats) < MIN_BEATS:
        index = max(range(len(beats)), key=lambda i: _word_count(beats[i]))
        words = str(beats[index]["line"]).split()
        if len(words) < MIN_WORDS * 2:
            break
        cut = len(words) // 2
        first, second = dict(beats[index]), dict(beats[index])
        first["line"] = " ".join(words[:cut])
        second["line"] = " ".join(words[cut:])
        second["role"] = "fact"
        second.pop("slam", None)
        second.pop("stat", None)
        beats[index:index + 1] = [first, second]
        log.append("beat count floor")

    used_shots = set()
    for beat in beats:
        shot = str(beat.get("shot", "") or "tech screen").strip().lower()
        words = shot.split()
        if len(words) > 4:
            shot = " ".join(words[:3])
        words = shot.split()
        if len(words) < 2:
            shot = (shot + " screen").strip()
            words = shot.split()
        if not any(word in CONCRETE for word in words):
            shot = (" ".join(words[:3]) + " screen") if len(words) >= 4 else shot + " screen"
        base, index = shot, 0
        modifiers = ["closeup", "detail", "macro", "wide", "angle", "topview"]
        while shot in used_shots:
            words = base.split()
            modifier = modifiers[index % len(modifiers)]
            shot = " ".join(words[:3] + [modifier]) if len(words) >= 4 else base + " " + modifier
            index += 1
            if index > 12:
                shot = base + " s" + str(index)
        used_shots.add(shot)
        beat["shot"] = shot

    script["beats"] = beats
    if log:
        print("  normalised: " + "; ".join(log[:4]), flush=True)
    return log


class Breaker:
    def __init__(self, name):
        self.name = name
        self.until = 0.0
        self.hits = 0
        self.reason = ""

    def trip(self, seconds, reason):
        self.until = max(self.until, time.time() + seconds)
        self.reason = reason
        print(f"  [breaker] {self.name} paused {int(seconds)}s ({reason})", flush=True)

    def check(self):
        if time.time() < self.until:
            raise RuntimeError(f"{self.name} paused ({self.reason})")


GROQ = Breaker("groq")
GEMINI = Breaker("gemini")
_last_gemini = [0.0]


def wrap(module):
    if getattr(module, "_flowfix2", False):
        return
    module._flowfix2 = True
    previous_groq, previous_gemini, previous_check = (
        module._groq, module._gemini, module.check_script)

    from pipeline import retention

    retention.gibberish_tokens = smart_gibberish

    def groq(system, prompt, model, temperature=0.7):
        GROQ.check()
        try:
            return previous_groq(system, prompt, model, temperature)
        except Exception as error:
            message = str(error)
            if _is_tpd(message):
                GROQ.trip(_retry_secs(message, 1800), "TPD")
                raise RuntimeError("groq TPD exhausted") from None
            raise

    def gemini(system, prompt, model, temperature=0.7):
        GEMINI.check()
        gap = float(os.getenv("GEMINI_MIN_INTERVAL", "1.5"))
        wait = gap - (time.time() - _last_gemini[0])
        if wait > 0:
            time.sleep(wait)
        delay = 4.0
        for attempt in range(3):
            _last_gemini[0] = time.time()
            try:
                result = previous_gemini(system, prompt, model, temperature)
                GEMINI.hits = 0
                return result
            except Exception as error:
                message = str(error)
                code = ("503" if "503" in message else
                        "429" if "429" in message or "Too Many" in message else "")
                if not code:
                    raise
                if code == "503":
                    GEMINI.hits += 1
                    if GEMINI.hits >= 3:
                        GEMINI.trip(180, "503 overload")
                        raise RuntimeError("gemini overloaded") from None
                if attempt == 2:
                    raise
                wait_seconds = min(45.0, max(3.0, _retry_secs(message, delay)))
                print(f"    gemini {code}, waiting {int(wait_seconds)}s", flush=True)
                time.sleep(wait_seconds)
                delay *= 2
        raise RuntimeError("gemini retries exhausted")

    def check(script, lang=None):
        if isinstance(script, dict) and isinstance(script.get("beats"), list):
            normalize(script, lang or "en")
        return previous_check(script, lang)

    module._groq = groq
    module._gemini = gemini
    module.check_script = check
    print("[flowfix v2] beats 5-9 + hook 5-6 + concrete shots + 503 breaker", flush=True)
