"""Deterministic title/description hardening. Runs after the LLM, never before."""
import re

YT_TITLE_MAX = 100
YT_TITLE_SAFE = 60
YT_DESC_MAX = 5000
IG_CAP_MAX = 2200
FOLD = 125  # chars visible in YT search result snippet / mobile player before "Show more"

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
        t = "#" + re.sub(r"[^0-9A-Za-zऀ-ॿఀ-౿_]", "", t.lstrip("#"))
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


def _viral_hook_line(d):
    """Return the strongest single-sentence hook for the top of the description.

    YouTube shows the first ~125 chars in search results and the first ~100 in
    the mobile player before 'Show more'. This line is the difference between
    a click and a scroll-past.

    Priority: hook_text > beats[0].line > title.
    """
    hook = str(d.get("hook_text", "")).strip()
    if hook and len(hook) >= 20:
        return hook
    beats = d.get("beats") or []
    if beats:
        first = str(beats[0].get("line", "")).strip()
        if first and len(first) >= 20:
            return first
    return str(d.get("title", "")).strip()


# CTA emoji suffixes per lang — adds urgency without feeling generic
_CTA_EMOJI = {"te": "👇🔔", "hi": "👇🔔", "en": "👇🔔"}

# Channel-link CTA templates (native script, no robotic English)
_DESC_CTA = {
    "te": "రోజూ అప్డేట్స్ కోసం ఛానెల్ ఫాలో చేయండి",
    "hi": "रोज़ के अपडेट के लिए चैनल फ़ॉलो करें",
    "en": "Follow the channel for daily updates",
}


def harden(d, lang, brand="", handle="", link="", source_url=""):
    """Enforce platform limits + above-the-fold structure. Returns (data, report).

    Description structure (viral-optimised):
      Line 1: strongest hook sentence  ← shown in search results (≤125 chars)
      Line 2: 2nd hook beat or question ← keeps reader reading
      (blank)
      CTA line
      Link (if any)
      Source
      (blank)
      Hashtags

    YT title structure:
      title kept ≤60 chars for mobile  ← avoids truncation
      title_with_hashtags appends 2-3 niche hashtags INSIDE the title
        (clickable, boost discovery more than description hashtags)
    """
    rep = []
    title = str(d.get("title", "")).strip()
    if not title:
        title = str(d.get("hook_text", "")).strip() or brand
        rep.append("title rebuilt from hook")
    if len(title) > YT_TITLE_MAX:
        title = _fold(title, YT_TITLE_MAX - 1)
        rep.append("title trimmed to 100")
    elif len(title) > YT_TITLE_SAFE:
        rep.append("title >60 chars (mobile truncates)")
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

    # ── Build viral YT description ────────────────────────────────────────────
    # Line 1: hook (≤125 chars — this is what YT shows in search results)
    hook_line = _viral_hook_line(d)
    hook_line = _fold(hook_line, FOLD)

    # Line 2: second-strongest beat or the closing question
    l2 = ""
    if question and question != hook_line:
        l2 = _fold(question, 120)
    elif len(lines) > 1 and lines[1] != hook_line:
        l2 = _fold(lines[1], 120)

    # CTA: use channel CTA or the per-channel cta_screen, plus emoji
    cta_line = _DESC_CTA.get(lang, _DESC_CTA["en"])
    emoji = _CTA_EMOJI.get(lang, "👇🔔")

    parts = [hook_line]
    if l2:
        parts.append(l2)
    parts.append("")
    parts.append(f"{cta_line} {emoji}")
    if handle:
        parts.append(f"@{handle.lstrip('@')}")
    if link:
        parts.append(str(link).strip())
    if source_url:
        src_label = "మూలం: " if lang == "te" else "स्रोत: " if lang == "hi" else "Source: "
        parts.append("")
        parts.append(src_label + str(source_url).strip())
    parts.append("")
    parts.append(" ".join(tags))

    desc = "\n".join(parts)
    if len(desc) > YT_DESC_MAX:
        desc = desc[:YT_DESC_MAX - 1] + "…"
        rep.append("description trimmed to 5000")
    d["description"] = desc

    # ── Instagram caption (viral-optimised) ──────────────────────────────────
    # Structure: hook + blank + question/beat2 + blank + CTA + blank + hashtags
    # Emoji used deliberately for readability in IG feed, not decoration.
    ig_hook = _fold(hook_line, 150)
    ig_parts = [ig_hook]
    if l2:
        ig_parts.append("")
        ig_parts.append(l2)
    ig_parts.append("")
    # CTA with emoji nudge
    ig_cta = str(d.get("cta_screen", "")).strip() or cta_line
    ig_parts.append(f"👉 {ig_cta}")
    ig_parts.append("")
    ig_parts.append(" ".join(_tags(tags, 5)))
    cap = "\n".join(ig_parts)
    if len(cap) > IG_CAP_MAX:
        cap = cap[:IG_CAP_MAX - 1] + "…"
        rep.append("ig caption trimmed to 2200")
    d["ig_caption"] = cap

    d["title_len"] = len(title)
    # fold_len: how much is visible before 'Show more' (approx 125 chars)
    d["fold_len"] = min(len(desc), FOLD)
    return d, rep
