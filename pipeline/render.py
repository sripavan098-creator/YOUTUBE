import json
import pathlib
import shutil
import subprocess
import sys

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
    """Pair every cut with a media file. Beats come from timing.beat_times; without
    them (long-form) cut on a fixed rhythm and cycle through the footage."""
    total = duration + TAIL
    if not beats:
        n = max(1, int(total // FALLBACK_CUT))
        step = total / n
        beats = [(i * step, (i + 1) * step) for i in range(n)]
    out = []
    for i, (s, e) in enumerate(beats):
        out.append((shot_paths[i % len(shot_paths)], s, e))
    out[-1] = (out[-1][0], out[-1][1], total)  # the last scene runs through the tail
    return out


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
    if not shot_paths:
        raise RuntimeError(f"no footage fetched for {sid}/{channel}")
    pub = REMOTION / "public" / "a" / str(sid) / channel
    if pub.exists():
        shutil.rmtree(pub)
    pub.mkdir(parents=True, exist_ok=True)
    shutil.copy(mp3, pub / "v.mp3")

    scenes = []
    for i, (src, s, e) in enumerate(_scenes(shot_paths, beats, duration)):
        if str(src).lower().endswith((".mp4", ".mov", ".webm")):
            name, kind = f"s{i}.mp4", "video"
            _prep_clip(src, pub / name, e - s)
        else:
            name, kind = f"s{i}.jpg", "image"
            shutil.copy(src, pub / name)
        scenes.append({"src": f"a/{sid}/{channel}/{name}", "kind": kind,
                       "start": round(s, 3), "end": round(e, 3)})

    props = {
        "lang": lcfg["lang"],
        "brandName": lcfg["brand"],
        "color": lcfg["color"],
        "accent": lcfg["accent"],
        "headline": script["title"],
        "hook": script.get("hook_text") or script["title"],
        "emphasis": script.get("emphasis", []),
        "cta": lcfg["cta"],
        "audio": f"a/{sid}/{channel}/v.mp3",
        "audioDuration": duration,
        "words": json.loads(pathlib.Path(words_json).read_text(encoding="utf-8")),
        "scenes": scenes,
        "shots": [s["src"] for s in scenes],
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
