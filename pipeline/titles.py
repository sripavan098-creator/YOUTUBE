"""Deterministic title/description hardening. Runs after the LLM, never before."""
import re

YT_TITLE_MAX = 100
YT_TITLE_SAFE = 60
YT_DESC_MAX = 5000
IG_CAP_MAX = 2200
FOLD = 150

SUCCESS_WORDS = {"te": "ఇప్పుడే", "hi": "अभी", "en": "now"}


def _fold(s, limit):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if len(s) <= limit:
        return s
    cut = s[:limit]
    sp = cut.rfind(" ")
    if sp > limit * 0.6:
        cut = cut[:sp]
    return cut.rstrip(" ,;:-–—") + "…"


def _tags(raw, cap, must="#shorts"):
    out, seen = [], set()
    for t in raw or []:
        t = str(t).strip()
        if not t:
            continue
        t = "#" + re.sub(r"[^0-9A-Za-z\u0900-\u097F\u0C00-\u0C7F_]", "", t.lstrip("#"))
        if len(t) < 2:
            continue
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    if must and must not in [x.lower() for x in out]:
        out.insert(0, must)
    return out[:cap]


def harden(d, lang, brand="", handle="", link="", source_url=""):
    """Enforce platform limits + above-the-fold structure. Returns (data, report)."""
    rep = []
    title = str(d.get("title", "")).strip()
    if not title:
        title = str(d.get("hook_text", "")).strip() or brand
        rep.append("title rebuilt from hook")
    if len(title) > YT_TITLE_MAX:
        title = _fold(title, YT_TITLE_MAX - 1)
        rep.append("title trimmed to 100")
    elif len(title) > YT_TITLE_SAFE:
        rep.append("title >60 (mobile truncates)")
    d["title"] = title

    beats = d.get("beats") or []
    lines = [str(b.get("line", "")).strip() for b in beats if b.get("line")]
    question = next((l for l in reversed(lines) if "?" in l), "")
    cta = str(d.get("cta_screen", "")).strip()
    if not cta:
        cta = (d.get("ig_caption", "") or title).split("\n")[0]
        cta = _fold(cta, 60)
        d["cta_screen"] = cta
        rep.append("cta_screen derived")

    tags = _tags(d.get("hashtags"), 8)
    d["hashtags"] = tags

    body = str(d.get("description", "")).strip()
    head = body.split("\n")[0].strip() if body else ""
    if not head or len(head) < 20:
        head = title
        rep.append("desc line 1 = title")
    l2 = question or (lines[1] if len(lines) > 1 else "")
    parts = [_fold(head, FOLD - 4)]
    if l2:
        parts.append(_fold(l2, 120))
    parts.append("")
    parts.append(cta)
    if link:
        parts.append(str(link).strip())
    if source_url:
        parts.append("")
        parts.append(("మూలం: " if lang == "te" else "स्रोत: " if lang == "hi" else "Source: ") + str(source_url).strip())
    parts.append("")
    parts.append(" ".join(tags))
    desc = "\n".join(parts)
    if len(desc) > YT_DESC_MAX:
        desc = desc[:YT_DESC_MAX - 1] + "…"
        rep.append("description trimmed to 5000")
    d["description"] = desc

    ig = [title, "", cta]
    if question:
        ig.append(_fold(question, 140))
    ig.append("")
    ig.append(" ".join(_tags(tags, 5)))
    cap = "\n".join(ig)
    if len(cap) > IG_CAP_MAX:
        cap = cap[:IG_CAP_MAX - 1] + "…"
        rep.append("ig caption trimmed to 2200")
    d["ig_caption"] = cap

    d["title_len"] = len(title)
    d["fold_len"] = min(len(desc), FOLD)
    return d, rep
