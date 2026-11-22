# shorts-engine (v2)

Local automation for two Shorts channels: **Vincodez Tech** (Hindi) and
**Tech Muchatlu** (Telugu). One daemon fetches stories, proposes three angles per story,
takes your Telegram pick, renders 4 Shorts per channel per day across four rotating
layouts, schedules them to YouTube, and queues Reels to Instagram.

## First run

```bash
pip install -r requirements.txt
cd remotion && npm install && npm rebuild esbuild && cd ..
cp .env.example .env          # fill in the 10 keys
python -m pipeline.doctor     # lists exactly what is still missing
python -m pipeline.main --now # one batch: 8 Shorts -> out/
```

## Commands

| Command | What it does |
|---|---|
| `python -m pipeline.main --now` | One morning batch (fetch, angles, review, render, upload) |
| `python -m pipeline.main --ig` | Post any Reels whose slot has arrived |
| `python -m pipeline.main --longform` | Build the weekly long-form for each channel |
| `python -m pipeline.main --replay` | Promote the private backlog after the API audit clears |
| `python -m pipeline.main` | Daemon: 06:00 daily, long-form Tue/Fri, IG pump every 15 min |
| `python -m pipeline.doctor` | Preflight checks |

## The audit gate

`config.yaml` ships with `yt_public_after_audit: false`. Until you flip it, every
upload is created **private with no publishAt**, because an unaudited Google Cloud
project cannot publish public videos. Nothing is lost: the files stay in `out/` and in
the DB, and `--replay` flips them public in place once the audit clears.

`--replay` uses `videos.update`, which requires the `youtube` or `youtube.force-ssl`
scope. It does **not** re-upload, because a second upload of the same file duplicates
the video on your channel. If your tokens were created before v2, re-run
`python -m pipeline.auth <channel>` to pick up the wider scope.

## v3: retention upgrade
Two-stage scripts (angles, then a validated per-channel beat script), one portrait video
clip per spoken line, hard cuts with punch-in and whoosh, word-pop captions with keyword
colour, a 2-second hook card, loudness-normalised voice. Details and the bug list are in
`REVIEW.md`. Optional: put royalty-free tracks in `assets/music/` for a ducked music bed.

## v3.1: trends, pure-language scripts, Unsplash-only footage
- **Google Trends** (`pipeline/trends.py`): stories that match what India (and AP/Telangana for
  the Telugu channel) is searching right now get a score boost, and trending tech searches can
  become stories themselves. It needs no API key; if Google is unreachable the pipeline runs
  without the boost. Turn off with `trends: false` in `config.yaml`.
- **Pure Telugu / Hindi**: the writer prompt asks for everyday spoken language in the native
  script, and the validator rejects any line containing Latin letters.
- **3-second hook**: the first spoken line must be 8 words or fewer, and after TTS its real
  length is measured; if it runs past 3.4 s the script is rewritten once with that number.
- **Unsplash only**: one portrait photo per spoken line, 9:16 crop. Demo apps are limited to
  50 requests/hour; searches are cached in `out/unsplash_cache.json` and the fetcher waits for
  the next hour when the quota runs out (`UNSPLASH_WAIT=0` to skip waiting). Applying for
  Production access in the Unsplash dashboard lifts the limit.
- `upload_batch.py` writes `<story>_<channel>.uploaded.json` and skips renders that have one.

## What changed from v1

- `channels` replaces `langs`. A channel owns its brand, voice and audience, so a story
  is re-angled per channel instead of translated.
- `stories` is keyed by `(channel, url)`. One story can serve both channels; it gets a
  different angle on each so the two videos are not the same script twice.
- Four layouts (`list`, `explainer`, `versus`, `timeline`) rotate, never repeating
  within three videos on the same channel.
- IG is capped at `ig_daily` posts, alternating channels, and only uses slots that have
  not already passed.
- Long-form has a same-day guard, so a daemon restart cannot upload two in one day.

## Known limits

- **Studio has no CSV import.** Google's upload page says "up to 15 videos at a time"
  with per-file editing; there is no bulk metadata CSV. So the audit-wait workflow is:
  run `--now`, then drag `out/*.mp4` into Studio (15 at a time). Files are already named
  `<story>_<channel>.mp4`, and the generated metadata is beside each file as
  `<story>_<channel>.meta.json`.
- **YouTube quota** is 10,000 units/day, but `videos.insert` has its own bucket of about
  100 uploads/day. 8 Shorts + 2 long-form/day is far inside it.
- **Untested against live services**: Instagram publish and the Groq/Gemini calls are
  not exercised by anything in this repo. YouTube upload and the Unsplash fetch have
  run in production.

## Verification

There is no committed test suite. Each run is verified by doing the real thing:

- `python -m pipeline.doctor` - preflight: config, env keys, OAuth tokens, ffmpeg,
  node/esbuild, Telegram reachability
- `python -m pipeline.probe` - real RSS fetch and a real angle-generation call
- one real render end to end: edge-tts word timings, ffmpeg audio finish, Remotion
  render, YouTube upload

## Layout

| Path | Role |
|---|---|
| `config.yaml` | Channels, brands, voices, schedules, model IDs |
| `pipeline/main.py` | Daemon, daily batch, IG pump |
| `pipeline/sources.py` | RSS radar with India / South-India tagging |
| `pipeline/scripts.py` | 3 angles per story, Groq then Gemini, strict validation |
| `pipeline/review.py` | Telegram angle picker (`1A,2C`, `skip 4`, `auto`) |
| `pipeline/voice.py` | edge-tts with word timings |
| `pipeline/visuals.py` | Unsplash portrait images |
| `pipeline/render.py` | Remotion render, layout to composition mapping |
| `pipeline/publish_yt.py` | Upload, slot scheduling, privacy gate, promote |
| `pipeline/publish_ig.py` | Reels publish via Graph API |
| `pipeline/host.py` | GitHub branch as public host for IG |
| `pipeline/longform.py` | Weekly connective long-form |
| `pipeline/replay.py` | Promote private backlog in place |
| `pipeline/doctor.py` | Preflight checks |
| `remotion/src/layouts/` | The four Short compositions |

## v4 (viral engine)
- **Voice**: every beat is voiced separately with its own mood (shock/urgent/curious/calm/serious), silence trimmed using exact word timings, deliberate pauses before re-hooks and payoffs. Beat cut times are exact.
- **Sound**: broadcast voice chain (80 Hz HPF, +2 dB warmth, +2.5 dB presence, compression, -14 LUFS); procedural impact / riser / whoosh / pop placed by beat role; generated music bed that ducks under speech. Drop files in `assets/sfx/<kind>.wav` or `assets/music/` to override.
- **Screen**: flash cuts, re-framing every 2.6 s, impact shake, grade + vignette + grain, hook slam with RGB glitch, kinetic keyword slam, stat cards, mid-video follow nudge, poster scenes when no photo is found. Telugu/Devanagari fonts are bundled (`npm install` in `remotion/`).
- **Content/SEO**: hook archetypes (stake, secret, number, question, contrarian, countdown), director fields per beat, critic polish pass, real search phrases (native + English) into tags and description, topic de-duplication over 14 days.
- **Learning**: `python -m pipeline.main --learn` (also nightly 05:30) pulls view stats and steers archetype choice. Only effective once videos are public.
- Rollback: `git revert` to commit abbba14 (pre-v4).
