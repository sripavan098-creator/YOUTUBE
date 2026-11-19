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


def npx_bin():
    exe = shutil.which("npx.cmd") if sys.platform == "win32" else shutil.which("npx")
    return exe or ("npx.cmd" if sys.platform == "win32" else "npx")


def render(sid, channel, lcfg, script, mp3, words_json, duration, shot_paths, layout):
    pub = REMOTION / "public" / "a" / str(sid) / channel
    pub.mkdir(parents=True, exist_ok=True)
    shutil.copy(mp3, pub / "v.mp3")
    for i, shot in enumerate(shot_paths):
        shutil.copy(shot, pub / f"{i}.jpg")

    props = {
        "lang": lcfg["lang"],
        "brandName": lcfg["brand"],
        "color": lcfg["color"],
        "accent": lcfg["accent"],
        "headline": script["title"],
        "cta": lcfg["cta"],
        "audio": f"a/{sid}/{channel}/v.mp3",
        "audioDuration": duration,
        "words": json.loads(pathlib.Path(words_json).read_text(encoding="utf-8")),
        "shots": [f"a/{sid}/{channel}/{i}.jpg" for i in range(len(shot_paths))],
    }
    props_file = pub / "props.json"
    props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    out = ROOT / "out" / f"{sid}_{channel}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    comp = COMPOSITIONS.get(layout, "ShortExplainer")
    subprocess.run([npx_bin(), "remotion", "render", comp, str(out),
                    f"--props={props_file}", "--codec=h264", "--concurrency=4",
                    "--overwrite", "--log=error"],
                   cwd=str(REMOTION), check=True)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"render produced no output for {sid}/{channel}")
    return str(out)
