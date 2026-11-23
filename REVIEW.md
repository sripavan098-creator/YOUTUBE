# Review and v3 upgrade notes

## Bugs found in v2 (all fixed on this branch)
1. `main.py` called `_clean_dict()`, which is never defined. Every YouTube upload raised
   NameError, which a broad `except` printed as "YT upload failed". Uploads never ran.
2. `review.py` default `timeout_s=5` is 5 *seconds* but the Telegram message says
   "no reply in 0 min". You could never pick an angle before it auto-chose A. Now 300 s.
3. `visuals.py` had inconsistent Unsplash/Pexels documentation. Unsplash is primary,
   Wikimedia Commons provides a no-key CC0/public-domain fallback, and Pexels is optional.
4. Only the Explainer layout showed the CTA, and only for 0.6 s (18 frames). The other
   three layouts had no CTA at all. Now all layouts show it for the last 2.8 s.
5. `List` layout faded the photo to 0 opacity at every shot boundary (visible dark
   flicker) and never changed shot after 12 s because shots clamped to the last index.
6. `fonts.ts` loaded all 54 Noto weight/subset files, which can exceed Remotion's 30 s
   render timeout on a slow connection. Now only weights 800/900 and the needed subsets.
7. IG caption was the literal string `#shorts #hi`. Now a written hook + question + tags.
8. `videos.zip` (77 MB of rendered output) is committed. Remove it and add it to .gitignore.

## What was weak for retention (and what replaced it)
| Area | v2 | v3 |
|---|---|---|
| Script | one LLM call wrote 3 angles x 2 languages, `reasoning_effort: low`, one attempt, only checked >=20 words | stage 1 cheap angles + facts; stage 2 writes the picked angle per channel as timed beats, validated (hook <=6 words and <=2.8 seconds, 50-80 words, 6-9 beats, source-backed claim/facts, unique visible-object shots, number card, concrete CTA, closing question) with the exact failure fed back on retry |
| Hook | pinned headline for the whole video, no on-screen hook | 2-5 word hook card pops in for 2.8 s, spoken hook <=6 words and <=2.8 s, loop-friendly last line |
| Footage | one still photo per 3-4 s, queries unrelated to the line | one portrait video clip per spoken line, query written per line, no repeats |
| Cuts | none (slow zoom on 4 stills) | hard cut on every sentence with a punch-in, alternating drift, whoosh on the cut |
| Captions | 3-word chunks, active word recoloured | sentence-aware chunks, spring pop, thick stroke, keyword words coloured in brand colour, safe zone above Shorts/Reels UI |
| Voice | raw edge-tts | +pitch per channel, compressor, high-pass, normalised to -14 LUFS, optional ducked music |
| Metadata | title + first sentence | title, 2-line keyword description, tags, per-video IG caption |

## Not done (needs you)
- Drop 3-5 royalty-free tracks into `assets/music/` to enable the ducked music bed.
- Add your Pexels key for optional video footage; Unsplash and the Wikimedia fallback do
  not require it.
- Viewed-vs-swiped-away is not currently exposed by the Analytics API query used here; check
  that metric manually in YouTube Studio. Retention and subscriber signals are used when the
  token has the read-only Analytics scope.
- Long-form still uses the old fixed 4 s cut rhythm; it is 16:9-unaware (1080x1920).
