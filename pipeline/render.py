import json
import os
import pathlib
import shutil
import subprocess
import sys

from pipeline import motion

ROOT = pathlib.Path(__file__).resolve().parent.parent
REMOTION = ROOT / "remotion"

COMPOSITIONS = {
    "list": "ShortList",
    "explainer": "ShortExplainer",
    "versus": "ShortVersus",
    "timeline": "ShortTimeline",
}

FPS = 30
TAIL = 0.6          # must match calculateMetadata in remotion/src/Root.tsx
FALLBACK_CUT = 4.0  # seconds per scene when no beat timings are supplied (long-form)


def npx_bin():
    exe = shutil.which("npx.cmd") if sys.platform == "win32" else shutil.which("npx")
    return exe or ("npx.cmd" if sys.platform == "win32" else "npx")


def _scenes(shot_paths, beats, duration):
    """Pair every cut with a media file (None = poster). Beats come from voice.synth_beats;
    without them (long-form) cut on a fixed rhythm and cycle through the footage."""
    total = duration + TAIL
    had_beats = bool(beats)
    if not beats:
        n = max(1, int(total // FALLBACK_CUT))
        step = total / n
        beats = [(i * step, (i + 1) * step) for i in range(n)]
    real = [p for p in shot_paths if p]
    out = []
    for i, (s, e) in enumerate(beats):
        if had_beats and i < len(shot_paths):
            src = shot_paths[i]
        else:
            src = real[i % len(real)] if real else None
        out.append((src, s, e))
    out[-1] = (out[-1][0], out[-1][1], total)  # the last scene runs through the tail
    return out


def _slam_time(word, words, s, e):
    """When the slammed word is actually spoken inside its beat."""
    strip = ".,!?।…\"'“”‘’():;-"
    key = word.strip(strip)
    for w in words:
        if s - 0.05 <= w["start"] < e and w["text"].strip(strip) == key:
            return w["start"]
    return None


def _prep_clip(src, dst, seconds):
    """Normalise a clip to exactly one scene: portrait 1080x1920, 30fps, silent, looped or
    trimmed to length. Rendering identical, pre-cut clips keeps Remotion fast and means a
    short stock clip can never freeze on its last frame."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", str(src),
         "-t", f"{seconds + 0.15:.2f}", "-an",
         "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps={FPS}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
         str(dst)], check=True)


def render(sid, channel, lcfg, script, mp3, words_json, duration, shot_paths, layout,
           beats=None):
    pub = REMOTION / "public" / "a" / str(sid) / channel
    if pub.exists():
        shutil.rmtree(pub)
    pub.mkdir(parents=True, exist_ok=True)
    shutil.copy(mp3, pub / "v.mp3")

    words = json.loads(pathlib.Path(words_json).read_text(encoding="utf-8"))
    meta = script.get("beats") or []
    use_meta = bool(beats) and len(meta) == len(beats)
    scenes = []
    for i, (src, s, e) in enumerate(_scenes(shot_paths, beats, duration)):
        sc = {"start": round(s, 3), "end": round(e, 3)}
        if not src:
            sc.update(
                src="",
                kind="poster",
                posterText=meta[i].get("line", "") if use_meta else "",
            )
        elif str(src).lower().endswith((".mp4", ".mov", ".webm")):
            name = f"s{i}.mp4"
            _prep_clip(src, pub / name, e - s)
            sc.update(src=f"a/{sid}/{channel}/{name}", kind="video")
        else:
            if os.getenv("MOTION_STILLS", "1") == "1":
                made = motion.still_to_clip(
                    src,
                    pub / f"s{i}.mp4",
                    e - s,
                    aggressive=(i == 0),
                    reverse=(i % 2 == 1),
                )
                name = pathlib.Path(made).name
                sc.update(
                    src=f"a/{sid}/{channel}/{name}",
                    kind="video" if name.endswith(".mp4") else "image",
                )
            else:
                name = f"s{i}.jpg"
                shutil.copy(src, pub / name)
                sc.update(src=f"a/{sid}/{channel}/{name}", kind="image")
        if use_meta:
            b = meta[i]
            sc["role"] = b.get("role") or ("hook" if i == 0 else "fact")
            sc["shake"] = sc["role"] in ("rehook", "payoff") or bool(b.get("shake"))
            if i and b.get("slam"):
                sc["slam"] = b["slam"]
                at = _slam_time(b["slam"], words, s, e)
                if at is not None:
                    sc["slamAt"] = round(at, 3)
            if i and b.get("stat"):
                sc["stat"] = str(b["stat"])
        scenes.append(sc)

    props = {
        "lang": lcfg["lang"],
        "brandName": lcfg["brand"],
        "color": lcfg["color"],
        "accent": lcfg["accent"],
        "headline": script["title"],
        "hook": script.get("hook_text") or script["title"],
        "emphasis": script.get("emphasis", []),
        "cta": script.get("cta_screen") or script.get("cta_text") or lcfg["cta"],
        "audio": f"a/{sid}/{channel}/v.mp3",
        "audioDuration": duration,
        "words": words,
        "nudge": lcfg.get("nudge", ""),
        "scenes": scenes,
        "shots": [s["src"] for s in scenes if s["src"]],
    }
    props_file = pub / "props.json"
    props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    out = ROOT / "out" / f"{sid}_{channel}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    comp = COMPOSITIONS.get(layout, "ShortExplainer")
    subprocess.run([npx_bin(), "remotion", "render", comp, str(out),
                    f"--props={props_file}", "--codec=h264", "--crf=20",
                    "--concurrency=2", "--overwrite", "--log=error"],
                   cwd=str(REMOTION), check=True)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"render produced no output for {sid}/{channel}")
    return str(out)
