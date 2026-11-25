import asyncio
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import edge_tts
from mutagen.mp3 import MP3


async def _run(text, voice, rate, pitch, volume, mp3_path, words_path):
    words = []
    with open(mp3_path, "wb") as f:
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch,
                                           volume=volume, boundary="WordBoundary")
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({
                    "text": chunk["text"],
                    "start": chunk["offset"] / 1e7,
                    "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                })
    if not words:
        raise RuntimeError("edge-tts returned no word boundaries")
    with open(words_path, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False)


def synth(text, voice, rate, mp3_path, words_path, attempts=3, pitch="+0Hz", volume="+0%"):
    """pitch/volume are optional per-channel tuning (config.yaml: pitch, volume).
    A small positive pitch and a slightly faster rate reads as more energetic."""
    last = None
    for i in range(attempts):
        try:
            asyncio.run(_run(text, voice, rate, pitch, volume, mp3_path, words_path))
            return MP3(mp3_path).info.length
        except Exception as e:
            last = e
            print(f"tts attempt {i + 1} failed: {e}")
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"tts failed for {voice}: {last}")


# ---------------------------------------------------------------- v4: per-beat voice
#
# One TTS call for a whole script gives one flat delivery and a fixed gap between every
# sentence. A human storyteller speeds up on shock, slows down and pauses before the
# payoff, and never leaves dead air. So each beat is voiced on its own with a mood, its
# silence is trimmed using the exact word timings, and the beats are stitched with
# deliberate pauses. Beat start times then come out exact, not estimated.

import pathlib
import subprocess
import wave

# mood -> (rate %, pitch Hz, volume %) added to the channel's base settings.
# Wider swings make the voice feel like a person, not a reader.
# Base rate in config.yaml should be +12% (energetic); moods shift from there.
MOODS = {
    "shock":    (+10, +2, +4),    # energetic without sounding rushed
    "urgent":   (+10, +1, +3),
    "excited":  (+8,  +3, +3),
    "curious":  (0,   0,  0),
    "calm":     (-3,  -1, -2),
    "serious":  (-4,  -2, +2),
}
# Silence BEFORE a beat (seconds). The dramatic pause before payoff is free emotion.
GAP_BEFORE = {"hook": 0.0, "fact": 0.04, "rehook": 0.12, "payoff": 0.18, "loop": 0.08}
DEFAULT_MOOD = {"hook": "shock", "fact": "curious", "rehook": "urgent",
                "payoff": "serious", "loop": "curious"}


def _num(s, default=0):
    m = re.search(r"-?\d+", str(s))
    return int(m.group()) if m else default


def _sarvam_pace(rate):
    return round(max(0.6, min(1.8, 1.30 + _num(rate) / 100)), 2)


def prosody(base_rate, base_pitch, base_volume, mood):
    dr, dp, dv = MOODS.get(mood, (0, 0, 0))
    r = max(-30, min(40, _num(base_rate) + dr))
    p = max(-20, min(20, _num(base_pitch) + dp))
    v = max(-20, min(20, _num(base_volume) + dv))
    return f"{r:+d}%", f"{p:+d}Hz", f"{v:+d}%"


def _synth_one(text, voice, rate, pitch, volume, mp3_path, words_path,
               lang=None, sarvam_voice_id=None, role="fact"):
    """Synthesise one beat.

    Priority:
      1. Sarvam AI — if SARVAM_API_KEY is set. Natural Indian-language prosody,
         voice cloning support, correct Telugu/Hindi accent. Pace and temperature
         are derived from the beat's role for natural expressive delivery.
      2. Edge TTS — fallback when Sarvam is unavailable.

    When Sarvam is used, word-boundary JSON is estimated from the audio duration
    (Sarvam doesn't return word timings). We generate one boundary spanning the
    full segment — the caption system will split on spaces instead.
    """
    # Try Sarvam first
    try:
        from pipeline.sarvam_voice import synth_sarvam, available as sarvam_ok, ROLE_SETTINGS
    except ImportError:
        sarvam_ok = lambda: False
        ROLE_SETTINGS = {}

    if sarvam_ok() and lang:
        # Role-based pace + temperature (research-validated per beat emotion)
        role_cfg = ROLE_SETTINGS.get(role, {"pace": 1.10, "temperature": 0.75})
        # Also factor in the mood's rate adjustment from Edge TTS rate setting
        r_num = int(re.search(r"-?\d+", rate).group()) if re.search(r"-?\d+", rate) else 0
        pace = round(max(0.6, min(1.8, role_cfg["pace"] + r_num / 200)), 2)  # blend
        temperature = role_cfg["temperature"]
        wav_path = str(pathlib.Path(mp3_path).with_suffix(".wav"))
        try:
            dur = synth_sarvam(text, lang, wav_path,
                               voice_id=sarvam_voice_id, pace=pace,
                               temperature=temperature)
            # Convert WAV → MP3 for consistency downstream
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav_path,
                            "-c:a", "libmp3lame", "-q:a", "2", mp3_path], check=True)
            # Estimate word boundaries (Sarvam gives no timings)
            words = _estimate_word_times(text, dur)
            pathlib.Path(words_path).write_text(
                json.dumps(words, ensure_ascii=False), encoding="utf-8"
            )
            return dur
        except Exception as e:
            print(f"  [sarvam] failed, falling back to Edge TTS: {e}")

    # Edge TTS fallback
    return synth(text, voice, rate, mp3_path, words_path, pitch=pitch, volume=volume)


def _estimate_word_times(text: str, duration: float) -> list:
    """Create approximate word-boundary entries from text + total duration.
    Distributes time proportionally by character count so captions are roughly right.
    Not as accurate as Edge TTS WordBoundary, but good enough for cut timing."""
    import re as _re
    # Split on whitespace, skip empty
    tokens = [w for w in _re.split(r"\s+", text.strip()) if w]
    if not tokens:
        return [{"text": text, "start": 0.0, "end": duration}]
    # Weight by character length (longer words take longer to say)
    weights = [max(1, len(t)) for t in tokens]
    total_w = sum(weights)
    # Keep only a tiny edge margin; the caller trims to these estimated boundaries.
    start_offset = min(0.02, duration / 2)
    usable = max(0.0, duration - start_offset - min(0.03, duration / 2))
    words = []
    t = start_offset
    for tok, w in zip(tokens, weights):
        seg = usable * (w / total_w)
        words.append({"text": tok, "start": round(t, 3), "end": round(t + seg, 3)})
        t += seg
    return words


def _wav_len(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def _ff(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, check=True)


def synth_beats(beats, lcfg, workdir, mp3_out):
    """Voice every beat with its own mood. Returns (words, beat_times, duration):
    words are global (seconds from 0), beat_times is [(start, end)] per beat.

    Uses Sarvam AI when SARVAM_API_KEY is set (best for Indian languages).
    Falls back to Edge TTS automatically.
    If SARVAM_VOICE_SAMPLE is set in .env, registers the cloned voice once and
    reuses it for every beat.
    """
    import json as _json
    workdir = pathlib.Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    SR = 48000
    parts, words_all, starts = [], [], []
    t = 0.0

    # Resolve cloned voice once per channel run
    sarvam_voice_id = None
    lang = lcfg.get("lang")
    sample = os.environ.get("SARVAM_VOICE_SAMPLE", "").strip()
    if sample and pathlib.Path(sample).exists() and lang:
        try:
            from pipeline.sarvam_voice import register_voice
            sarvam_voice_id = register_voice(sample, lang)
        except Exception as e:
            print(f"  [sarvam] voice clone registration failed: {e}")

    # Build per-beat synthesis args (prosody is cheap, done upfront)
    beat_args = []
    for i, b in enumerate(beats):
        role = b.get("role") or ("hook" if i == 0 else "fact")
        mood = b.get("mood") or DEFAULT_MOOD.get(role, "curious")
        rate, pitch, vol = prosody(lcfg.get("rate", "+0%"), lcfg.get("pitch", "+0Hz"),
                                   lcfg.get("volume", "+0%"), mood)
        raw, wj = workdir / f"b{i}.mp3", workdir / f"b{i}.json"
        beat_args.append((i, b, role, rate, pitch, vol, raw, wj))

    # ── Parallel TTS synthesis ──────────────────────────────────────────────
    # All Sarvam/Edge API calls run concurrently; file I/O stays serial below.
    # With 6 beats × ~3s each this drops total voice time from ~18s → ~3-4s.
    def _synth_beat(args):
        i, b, role, rate, pitch, vol, raw, wj = args
        _synth_one(b["line"], lcfg["voice"], rate, pitch, vol, str(raw), str(wj),
                   lang=lang, sarvam_voice_id=sarvam_voice_id, role=role)
        return i

    max_workers = min(len(beat_args), 6)
    if max_workers > 1:
        print(f"  [voice] synthesising {len(beat_args)} beats in parallel (workers={max_workers})", flush=True)
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_synth_beat, args): args[0] for args in beat_args}
            done = {}
            for f in as_completed(futures):
                idx = futures[f]
                try:
                    done[idx] = f.result()
                except Exception as e:
                    print(f"  [voice] beat {idx} failed: {e}", flush=True)
                    raise
    else:
        # Single beat — no overhead needed
        for args in beat_args:
            _synth_beat(args)

    # ── Assemble in original order (serial — file I/O must be ordered) ──────
    for i, b, role, rate, pitch, vol, raw, wj in beat_args:
        w = _json.loads(wj.read_text(encoding="utf-8"))
        # Keep a short natural edge around the spoken segment.
        cut0 = max(0.0, w[0]["start"] - 0.03)
        cut1 = w[-1]["end"] + 0.05
        seg = workdir / f"b{i}.wav"
        _ff(["-i", str(raw), "-ss", f"{cut0:.3f}", "-t", f"{cut1 - cut0:.3f}",
             "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", str(seg)])
        gap = GAP_BEFORE.get(role, 0.1) if i else 0.0
        if gap:
            g = workdir / f"g{i}.wav"
            _ff(["-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono", "-t", f"{gap:.3f}",
                 "-c:a", "pcm_s16le", str(g)])
            parts.append(g)
            t += _wav_len(g)
        starts.append(t)
        for x in w:
            words_all.append({"text": x["text"], "start": round(t + x["start"] - cut0, 3),
                              "end": round(t + x["end"] - cut0, 3)})
        parts.append(seg)
        t += _wav_len(seg)
    lst = workdir / "list.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    _ff(["-f", "concat", "-safe", "0", "-i", str(lst), "-c:a", "libmp3lame", "-q:a", "2",
         str(mp3_out)])
    dur = t
    # a beat owns the silence up to the next beat, so cuts tile the whole timeline
    times = [(s, e) for s, e in zip(starts, starts[1:] + [dur])]
    return words_all, times, dur
