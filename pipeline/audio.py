"""Audio finishing: broadcast voice chain, procedural sound design, ducked music, loudness.

Three layers (everything is synthesised with ffmpeg, so there is no sample licence to
worry about; drop your own files into assets/sfx or assets/music to override):

  1. Voice  - high-pass, warmth (+2 dB ~150 Hz), presence (+2.5 dB ~4 kHz), compression
  2. SFX    - impact on the hook, whoosh on cuts, riser into re-hooks/payoffs, pop on
              slammed words and stats (about -12 dB under the voice)
  3. Music  - a quiet bed that ducks under speech and swells in the pauses

The voice stays the master clock: nothing here changes the length of the voice track, so
the word timings written by voice.synth_beats stay valid for the captions.
"""
import glob
import pathlib
import random
import subprocess

from mutagen.mp3 import MP3

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
TARGET_LUFS = -14  # what Shorts and Reels normalise toward; louder than that gets turned down

# kind -> (ffmpeg input args, seconds long, gain relative to the voice, lead-in seconds)
# lead-in is how long BEFORE the cue time the sound should start so its peak lands on it.
_SFX = {
    "whoosh": (["-f", "lavfi", "-i", "anoisesrc=d=0.45:c=pink:a=0.6"],
               "highpass=f=500,lowpass=f=6500,afade=t=in:d=0.18,afade=t=out:st=0.2:d=0.25",
               0.30, 0.14),
    "impact": (["-f", "lavfi", "-i",
                "aevalsrc='sin(2*PI*(48+110*exp(-t*16))*t)*exp(-t*4.2)+0.25*random(0)*exp(-t*38)':d=1.1:s=48000"],
               "lowpass=f=1800,volume=1.4", 0.55, 0.0),
    "riser": (["-f", "lavfi", "-i",
               "aevalsrc='(sin(2*PI*(260*t+330*t*t)*1)*0.5+0.35*random(0))*pow(t/1.1,2.2)':d=1.1:s=48000"],
              "highpass=f=250,lowpass=f=7000,afade=t=out:st=1.0:d=0.1", 0.28, 1.1),
    "pop": (["-f", "lavfi", "-i",
             "aevalsrc='sin(2*PI*(160+1100*exp(-t*38))*t)*exp(-t*30)':d=0.16:s=48000"],
            "highpass=f=120", 0.5, 0.0),
}


def _ffmpeg(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, check=True)


def _sfx_file(kind):
    custom = ASSETS / "sfx" / f"{kind}.wav"
    if custom.exists():
        return custom
    out = ASSETS / "sfx" / f"_gen_{kind}.wav"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        src, flt, _, _ = _SFX[kind]
        _ffmpeg(src + ["-af", flt + ",aformat=channel_layouts=mono", "-ar", "48000", str(out)])
    return out


def _music():
    """A real track if one is dropped in assets/music; otherwise a generated warm pad."""
    files = [f for ext in ("mp3", "wav", "m4a") for f in glob.glob(str(ASSETS / "music" / f"*.{ext}"))]
    if files:
        return random.choice(files)
    out = ASSETS / "music" / "_gen_pad.wav"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        # A minor 9 pad (A2 E3 A3 C4 B4), slow tremolo, low-passed: felt more than heard.
        expr = ("(sin(2*PI*110*t)+0.8*sin(2*PI*164.8*t)+0.6*sin(2*PI*220*t)+"
                "0.4*sin(2*PI*261.6*t)+0.25*sin(2*PI*493.9*t))*(0.75+0.25*sin(2*PI*0.18*t))*0.2")
        _ffmpeg(["-f", "lavfi", "-i", f"aevalsrc='{expr}':d=24:s=48000",
                 "-af", "lowpass=f=1100,afade=t=in:d=1,afade=t=out:st=23:d=1", str(out)])
    return str(out)


def default_cues(cuts, roles=None):
    """Cues from beat start times. roles (hook/fact/rehook/payoff/loop per beat) lets
    the sound follow the story: impact on the hook, a riser into turns and payoffs."""
    cues = [(0.0, "impact")]
    for i, t in enumerate(cuts):
        if i == 0:
            continue
        role = roles[i] if roles and i < len(roles) else "fact"
        if role in ("rehook", "payoff"):
            cues.append((t, "riser"))
            cues.append((t, "impact"))
        else:
            cues.append((t, "whoosh"))
    return cues


def finish(mp3_in, mp3_out, cut_times, duration, sfx=True, music_volume=0.16,
           cues=None, music=True):
    """Write the finished mix to mp3_out and return its length in seconds."""
    if cues is None:
        cues = default_cues(cut_times)
    inputs = ["-i", str(mp3_in)]
    n_in = 1  # ffmpeg input index of the next file added (len(inputs) is not it: flags count)
    chains = ["[0:a]highpass=f=80,"
              "equalizer=f=150:t=o:w=1.2:g=2,"          # warmth
              "equalizer=f=4000:t=o:w=1.5:g=2.5,"       # presence / clarity
              "acompressor=threshold=0.09:ratio=3.5:attack=5:release=90:makeup=2,"
              "aresample=48000,aformat=channel_layouts=stereo[v]"]
    mix = []

    if music_volume and music:
        inputs += ["-stream_loop", "-1", "-i", _music()]
        mi, n_in = n_in, n_in + 1
        chains.append("[v]asplit=2[vmix][vsc]")
        chains.append(f"[{mi}:a]aresample=48000,aformat=channel_layouts=stereo,"
                      f"volume={music_volume},atrim=0:{duration + 0.5:.2f},"
                      f"afade=t=in:d=0.4[m]")
        # duck under speech (about -10 dB), swell back in the pauses
        chains.append("[m][vsc]sidechaincompress=threshold=0.012:ratio=9:attack=12:"
                      "release=450:makeup=1[md]")
        mix = ["[vmix]", "[md]"]
    else:
        mix = ["[v]"]

    if sfx:
        for n, (t, kind) in enumerate(c for c in cues if c[1] in _SFX):
            _, _, gain, lead = _SFX[kind]
            inputs += ["-i", str(_sfx_file(kind))]
            wi, n_in = n_in, n_in + 1
            ms = max(0, int((t - lead) * 1000))
            chains.append(f"[{wi}:a]aformat=channel_layouts=stereo,adelay={ms}|{ms},"
                          f"volume={gain}[s{n}]")
            mix.append(f"[s{n}]")

    chains.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,"
                  f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=9[out]")
    _ffmpeg(inputs + ["-filter_complex", ";".join(chains), "-map", "[out]",
                      "-c:a", "libmp3lame", "-q:a", "2", str(mp3_out)])
    return MP3(str(mp3_out)).info.length
