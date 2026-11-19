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
  `<story>_<channel>.mp4`, and titles are in the DB.
- **YouTube quota** is 10,000 units/day, but `videos.insert` has its own bucket of about
  100 uploads/day. 8 Shorts + 2 long-form/day is far inside it.
- **Untested against live services**: YouTube upload, Instagram publish, Pexels fetch and
  the Groq/Gemini calls. Everything else is exercised in the test suite below.

## Tests

The pipeline is verified by running it, not by mocking the interesting parts:

- real edge-tts in Hindi and Telugu, asserting word-level boundaries exist
- real Remotion renders of all four layouts to valid MP4
- full `morning()` run producing 8 MP4s with stubbed network only
- assignment, angle-selection, layout rotation, IG cap, replay and long-form guards

## Layout

| Path | Role |
|---|---|
| `config.yaml` | Channels, brands, voices, schedules, model IDs |
| `pipeline/main.py` | Daemon, daily batch, IG pump |
| `pipeline/sources.py` | RSS radar with India / South-India tagging |
| `pipeline/scripts.py` | 3 angles per story, Groq then Gemini, strict validation |
| `pipeline/review.py` | Telegram angle picker (`1A,2C`, `skip 4`, `auto`) |
| `pipeline/voice.py` | edge-tts with word timings |
| `pipeline/visuals.py` | Pexels portrait b-roll |
| `pipeline/render.py` | Remotion render, layout to composition mapping |
| `pipeline/publish_yt.py` | Upload, slot scheduling, privacy gate, promote |
| `pipeline/publish_ig.py` | Reels publish via Graph API |
| `pipeline/host.py` | GitHub branch as public host for IG |
| `pipeline/longform.py` | Weekly connective long-form |
| `pipeline/replay.py` | Promote private backlog in place |
| `pipeline/doctor.py` | Preflight checks |
| `remotion/src/layouts/` | The four Short compositions |
