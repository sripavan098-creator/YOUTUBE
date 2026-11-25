"""Sarvam AI TTS + Instant Voice Cloning for Telugu and Hindi.

Sarvam was built from scratch for Indian languages — it understands native
pronunciation, regional accents, and natural spoken rhythm in a way that
Edge TTS (trained on English-centric data) cannot.

Setup:
  1. Get a free API key at https://dashboard.sarvam.ai  (no credit card needed)
  2. Add SARVAM_API_KEY to your .env
  3. (Optional) Record 10-15 seconds of your own voice in a quiet room as a WAV file
     and set SARVAM_VOICE_SAMPLE=/path/to/sample.wav in .env — the pipeline will clone
     it on the first run and reuse the voice_id for every video.

Voice cloning consent: only clone a voice you have the right to use (your own).

Pricing: ₹20 per 10,000 characters (~1 month of daily Shorts for under ₹50)
"""
import base64
import json
import os
import pathlib
import subprocess
import time

import requests
from sarvamai import SarvamAI

SARVAM_BASE = "https://api.sarvam.ai"

# Sarvam language codes per channel language key
LANG_CODE = {"hi": "hi-IN", "te": "te-IN", "en": "en-IN"}

# Best Sarvam voices for each language (research-validated 2026)
# ritu_hi_reels: energetic reel voice — more expressive than ritu_hi_conversation
# kavitha_te_narration: best Telugu narration voice, smoother pacing
DEFAULT_VOICES = {
    "hi": "ritu_hi_reels",          # Ritu — energetic, emotional, made for Reels/Shorts
    "te": "kavitha_te_narration",    # Kavitha — best Telugu narration, natural rhythm
}

# Per-role pace & temperature (overrides the base synth_sarvam defaults)
# Research: hook needs urgency, payoff needs gravitas, rehook needs surprise peak
ROLE_SETTINGS = {
    "hook":    {"pace": 1.15, "temperature": 0.85},
    "fact":    {"pace": 1.00, "temperature": 0.65},
    "rehook":  {"pace": 1.20, "temperature": 0.90},
    "payoff":  {"pace": 1.10, "temperature": 0.80},
    "loop":    {"pace": 1.00, "temperature": 0.70},
}


def _voice_for(lang: str, voice_id: str = None) -> str:
    """Prefer a per-language configured or cloned voice over the built-in default."""
    return (
        voice_id
        or os.environ.get(f"SARVAM_VOICE_{lang.upper()}", "").strip()
        or DEFAULT_VOICES.get(lang, "ritu_hi_conversation")
    )


# Cache file for cloned voice IDs so we don't re-create every run
_CACHE_FILE = pathlib.Path(__file__).resolve().parent.parent / "out" / "sarvam_voice_cache.json"


def _headers():
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        raise RuntimeError(
            "SARVAM_API_KEY not set. Get a free key at https://dashboard.sarvam.ai "
            "and add it to your .env file."
        )
    return {"api-subscription-key": key, "Content-Type": "application/json"}


def _load_cache():
    try:
        return json.loads(_CACHE_FILE.read_text())
    except Exception:
        return {}


def _save_cache(cache):
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass


def register_voice(sample_wav_path: str, lang: str, name: str = "my-cloned-voice") -> str:
    """Upload a 10-15s voice sample and return a persistent voice_id.

    Call this once per sample file; the voice_id is cached to disk and reused.
    The sample must be a WAV file of your own voice, recorded in a quiet room.
    Returns the voice_id string on success.
    """
    cache = _load_cache()
    sample_path = pathlib.Path(sample_wav_path)
    cache_key = f"clone:{sample_path.stem}:{lang}"
    if cache_key in cache:
        print(f"  [sarvam] reusing cloned voice {cache[cache_key]!r}")
        return cache[cache_key]

    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        raise RuntimeError("SARVAM_API_KEY not set")

    lang_code = LANG_CODE.get(lang, "en-IN")
    print(f"  [sarvam] uploading voice sample {sample_path.name} for {lang_code}...")
    with open(sample_path, "rb") as f:
        response = SarvamAI(api_subscription_key=key).voice_cloning.create_voice(
            file=f,
            name=name,
            language=lang_code,
            style="conversational",
            remove_background_noise=True,
        )
    voice_id = response.data.voice_id
    print(f"  [sarvam] cloned voice registered: {voice_id}")
    cache[cache_key] = voice_id
    _save_cache(cache)
    return voice_id


def synth_sarvam(
    text: str,
    lang: str,
    wav_out: str,
    voice_id: str = None,
    pace: float = 1.15,
    temperature: float = 0.75,
    attempts: int = 3,
) -> float:
    """Synthesise text with Sarvam Bulbul V4 Flash, write a WAV file, return duration.

    - voice_id: a cloned voice_id from register_voice(), or None to use the default
      built-in Sarvam voice for the channel language.
    - pace: 0.5-2.0; 1.15 is slightly faster than neutral — natural for Shorts.
    - temperature: 0.5-1.0; higher = more expressive. 0.75 for Hindi, 0.65 for Telugu.
    - enable_preprocessing=True: Sarvam reads numbers, symbols and English words naturally.
    """
    lang_code = LANG_CODE.get(lang, "en-IN")
    voice = _voice_for(lang, voice_id)

    last = None
    for i in range(attempts):
        try:
            if voice_id and voice_id.startswith("svc-"):
                response = SarvamAI(
                    api_subscription_key=os.environ["SARVAM_API_KEY"]
                ).voice_cloning.convert(
                    voice_id=voice_id,
                    text=text,
                    language_code=lang_code,
                    pace=pace,
                    output_audio_codec="wav",
                )
                audio_b64 = getattr(response, "audio_b64", None) or getattr(
                    response, "audio", None
                )
                if not audio_b64:
                    raise RuntimeError("Sarvam cloned-voice API returned no audio data")
            else:
                payload = {
                    "inputs": [text],
                    "target_language_code": lang_code,
                    "speaker": voice,
                    "pace": pace,
                    "enable_preprocessing": True,
                    "model": "bulbul:v4",
                }
                r = requests.post(
                    f"{SARVAM_BASE}/text-to-speech",
                    headers=_headers(),
                    json=payload,
                    timeout=60,
                )
                if r.status_code == 429:
                    time.sleep(5 * (i + 1))
                    continue
                r.raise_for_status()
                audio_b64 = r.json()["audios"][0]

            raw = base64.b64decode(audio_b64)
            wav_path = pathlib.Path(wav_out)
            wav_path.parent.mkdir(parents=True, exist_ok=True)
            wav_path.write_bytes(raw)

            # Get duration via ffprobe
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(wav_path)],
                capture_output=True, text=True, timeout=15,
            )
            return float(result.stdout.strip() or "0")
        except Exception as e:
            last = e
            print(f"  [sarvam] attempt {i+1} failed: {e}")
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"Sarvam TTS failed after {attempts} attempts: {last}")


def available() -> bool:
    """True if SARVAM_API_KEY is set in the environment."""
    return bool(os.environ.get("SARVAM_API_KEY", "").strip())
