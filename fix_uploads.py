"""Repair Shorts that were published with filename-derived titles.

upload_batch.py derived titles from the mp4 filename, so videos named
"25_hi.mp4" went live as "25". This rewrites the snippet (title, description,
tags) in place. Videos are NOT re-uploaded and view counts are preserved.

    python fix_uploads.py            # dry run, prints the diff
    python fix_uploads.py --apply    # actually update

Requires tokens/yt_hi.json with the `youtube` scope (videos.update).
"""

import json
import pathlib
import sys

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

ROOT = pathlib.Path(__file__).parent
TOKENS_DIR = ROOT / "tokens"

# Titles and descriptions rebuilt from each video's own transcript.
FIXES = {
    "fP7Y6iqhMGg": {
        "title": "Google Labs Table Top: टीम के लिए नया AI टूल",
        "desc": "Google Labs का Table Top सिर्फ निजी इस्तेमाल के लिए नहीं, टीमों के लिए है। "
                "लिंक, फाइलें और आइडिया डालें, फिर @Table Top से expense splitter या "
                "tournament bracket जैसे टेम्पलेट बनाएं — Google Docs की तरह सब साथ काम कर सकते हैं।",
        "tags": ["google labs", "table top", "ai tools", "productivity", "tech news"],
    },
    "dWcCcFwnZzI": {
        "title": "Google का नया AI साइडबार: SEO बदलने वाला है?",
        "desc": "Google Search में नया AI साइडबार यूज़र के search intent को बदल रहा है। "
                "एक ही सत्र में कई सवाल, thread history और notebook connection — "
                "मार्केटर्स को ज़्यादा डेटा मिलेगा। क्या ब्रांड्स को अपनी SEO रणनीति बदलनी होगी?",
        "tags": ["google ai", "seo", "search", "marketing", "tech news"],
    },
    "Q2WQnWi3MhQ": {
        "title": "Anthropic का Amazon पर $100 बिलियन का दांव",
        "desc": "Anthropic ने अगले 10 साल में Amazon पर $100 बिलियन से ज़्यादा क्लाउड खर्च करने "
                "का वादा किया है। भारतीय कंपनियों को तेज़ AI सेवाएं और AWS की कीमतों में बदलाव "
                "दिख सकता है। क्या भारतीय व्यवसाय इस अवसर को पकड़ पाएंगे?",
        "tags": ["anthropic", "amazon", "aws", "ai business", "tech news"],
    },
    "SKNhzpmPkV4": {
        "title": "Google Search में विजुअल जवाब: नया AI अपग्रेड",
        "desc": "Google Search अब और विजुअल हो गया है — जवाब में इमेज, तुलना तालिकाएं और "
                "कस्टम टूल्स मिलेंगे, वह भी सेकंडों में। यह अपग्रेड सभी भाषाओं में काम करता है, "
                "इसलिए हिंदी में पूछने पर भी साफ़ जवाब मिलेगा।",
        "tags": ["google search", "gemini", "ai search", "india tech", "tech news"],
    },
    "_aYeYwC6_GQ": {
        "title": "Nvidia की सप्लाई डील: भारत बनेगा AI हब?",
        "desc": "Nvidia ने अगले दशक तक सप्लाई एग्रीमेंट साइन किए हैं, जिससे भारत के डेटा सेंटरों "
                "को हाई परफॉर्मेंस GPU मिलेंगे। AI स्टार्टअप्स को तेज़ प्रोसेसिंग और कम लागत मिल "
                "सकती है, पर स्थानीय निर्माताओं को प्रतिस्पर्धा का सामना करना पड़ेगा।",
        "tags": ["nvidia", "india ai", "data center", "gpu", "tech news"],
    },
    "6-D8TaRc5AY": {
        "title": "OpenAI और AMD: चिप डिज़ाइन में 14% सुधार",
        "desc": "OpenAI ने AMD के साथ मिलकर अपने मॉडल से चिप डिज़ाइन में 14% PPA सुधार किया। "
                "AMD ने इस कोड को अपने प्रोडक्शन फाइलों में जोड़ा, और EDA टूल्स के साथ मॉडल ने "
                "RTL को एक्सपर्ट लेवल पर रीराइट किया। क्या सेमीकंडक्टर उद्योग बदल रहा है?",
        "tags": ["openai", "amd", "semiconductor", "chip design", "tech news"],
    },
    "rW6rrc3L5yw": {
        "title": "Apple का AI एजेंट: थर्ड पार्टी ऐप्स पर रोक",
        "desc": "Apple अपना AI एजेंट लॉन्च करते ही थर्ड पार्टी एजेंट्स पर कड़ी रोक लगाने की "
                "तैयारी में है। Bloomberg के मुताबिक macOS में पूर्ण एक्सेस के लिए स्पष्ट अनुमति "
                "मांगी जाएगी। Anthropic और Meta जैसे प्रतिस्पर्धियों के सामने यह Apple की नई रणनीति है।",
        "tags": ["apple", "ai agent", "macos", "privacy", "tech news"],
    },
}


def load_creds(channel):
    path = TOKENS_DIR / f"yt_{channel}.json"
    if not path.exists():
        sys.exit(f"Missing {path}. Run the OAuth flow for '{channel}' first.")
    data = json.loads(path.read_text())
    return Credentials(
        token=data.get("token") or data.get("access_token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes") or ["https://www.googleapis.com/auth/youtube"],
    )


def main():
    apply = "--apply" in sys.argv
    yt = build("youtube", "v3", credentials=load_creds("hi"))

    # One list call for all ids, then merge into the existing snippet so we do
    # not clobber fields we are not changing (categoryId, defaultLanguage, ...).
    ids = ",".join(FIXES)
    resp = yt.videos().list(part="snippet", id=ids).execute()
    current = {v["id"]: v["snippet"] for v in resp.get("items", [])}

    missing = set(FIXES) - set(current)
    if missing:
        print(f"Not found or not owned by this channel: {', '.join(sorted(missing))}")

    for vid, fix in FIXES.items():
        if vid not in current:
            continue
        snippet = current[vid]
        print(f"\n{vid}")
        print(f"  title: {snippet.get('title')!r}")
        print(f"     -> {fix['title']!r}")
        print(f"  desc : {snippet.get('description', '')[:60]!r}...")
        print(f"     -> {fix['desc'][:60]!r}...")

        if not apply:
            continue

        snippet["title"] = fix["title"][:100]
        snippet["description"] = fix["desc"][:5000]
        snippet["tags"] = fix["tags"]
        try:
            yt.videos().update(part="snippet", body={"id": vid, "snippet": snippet}).execute()
            print("  updated")
        except HttpError as e:
            print(f"  FAILED: {e}")

    if not apply:
        print("\nDry run. Re-run with --apply to write these changes.")


if __name__ == "__main__":
    main()
