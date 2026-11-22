import asyncio
import json
import re
import time

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

# mood -> (rate %, pitch Hz, volume %) added to the channel's base settings
MOODS = {
    "shock": (10, 4, 6), "urgent": (14, 3, 4), "excited": (10, 5, 4),
    "curious": (-2, 2, 0), "calm": (-6, -2, -2), "serious": (-8, -4, 2),
}
# seconds of silence BEFORE a beat, by role. The pause before a payoff is the cheapest
# way to make it land.
GAP_BEFORE = {"hook": 0.0, "fact": 0.10, "rehook": 0.32, "payoff": 0.38, "loop": 0.26}
DEFAULT_MOOD = {"hook": "shock", "fact": "curious", "rehook": "urgent",
                "payoff": "serious", "loop": "curious"}


def _num(s, default=0):
    m = re.search(r"-?\d+", str(s))
    return int(m.group()) if m else default


def prosody(base_rate, base_pitch, base_volume, mood):
    dr, dp, dv = MOODS.get(mood, (0, 0, 0))
    r = max(-30, min(40, _num(base_rate) + dr))
    p = max(-20, min(20, _num(base_pitch) + dp))
    v = max(-20, min(20, _num(base_volume) + dv))
    return f"{r:+d}%", f"{p:+d}Hz", f"{v:+d}%"


def _synth_one(text, voice, rate, pitch, volume, mp3_path, words_path):
    """Seam for tests; the real network call."""
    return synth(text, voice, rate, mp3_path, words_path, pitch=pitch, volume=volume)


def _wav_len(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def _ff(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, check=True)


def synth_beats(beats, lcfg, workdir, mp3_out):
    """Voice every beat with its own mood. Returns (words, beat_times, duration):
    words are global (seconds from 0), beat_times is [(start, end)] per beat."""
    import json as _json
    workdir = pathlib.Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    SR = 48000
    parts, words_all, starts = [], [], []
    t = 0.0
    for i, b in enumerate(beats):
        role = b.get("role") or ("hook" if i == 0 else "fact")
        mood = b.get("mood") or DEFAULT_MOOD.get(role, "curious")
        rate, pitch, vol = prosody(lcfg.get("rate", "+0%"), lcfg.get("pitch", "+0Hz"),
                                   lcfg.get("volume", "+0%"), mood)
        raw, wj = workdir / f"b{i}.mp3", workdir / f"b{i}.json"
        _synth_one(b["line"], lcfg["voice"], rate, pitch, vol, str(raw), str(wj))
        w = _json.loads(wj.read_text(encoding="utf-8"))
        # cut to the speech: 30 ms before the first word, 110 ms after the last
        cut0 = max(0.0, w[0]["start"] - 0.03)
        cut1 = w[-1]["end"] + 0.11
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
