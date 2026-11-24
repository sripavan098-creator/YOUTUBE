import os, base64, pathlib, subprocess, shutil, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Sarvam Config ---
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
# Supports both built-in names (e.g., "maitreyi") AND cloned IDs (e.g., "svc-804803aa...")
SARVAM_VOICES = {
    "hi": os.getenv("SARVAM_VOICE_HI", "meera"),
    "te": os.getenv("SARVAM_VOICE_TE", "maitreyi")
}

# --- Gemini Config (Fallback) ---
GEMINI_VOICES = {"hi": os.getenv("TTS_VOICE_HI", "Charon"), "te": os.getenv("TTS_VOICE_TE", "Charon")}
GEMINI_STYLE = "energetic, crisp tech-news anchor; fast-paced but clearly articulated"

def _sarvam_tts(text, lang, wav_path):
    """Primary: Sarvam AI (Minimal payload to support cloned 'svc-' voices)"""
    if not SARVAM_API_KEY:
        raise ValueError("No SARVAM_API_KEY")

    speaker = SARVAM_VOICES.get(lang, "maitreyi")
    if speaker.startswith("svc-"):
        if len(text) > 1000:
            raise ValueError("Sarvam cloned-voice requests are limited to 1000 characters")
        r = requests.post(
            "https://api.sarvam.ai/voices/clone",
            headers={"api-subscription-key": SARVAM_API_KEY},
            data={
                "voice_id": speaker,
                "text": text,
                "language_code": f"{lang}-IN",
            },
            timeout=60,
        )
        if not r.ok:
            print(f"  ⚠️ Sarvam API Error {r.status_code}: {r.text}", flush=True)
            r.raise_for_status()
        data = r.json()
        audio_b64 = data.get("audio_b64") or data.get("audio")
        if not audio_b64:
            raise RuntimeError("Sarvam cloned-voice API returned no audio data")
        pathlib.Path(wav_path).write_bytes(base64.b64decode(audio_b64))
        print(f"  ✅ TTS via Sarvam clone ({speaker})", flush=True)
        return

    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }
    
    # MINIMAL PAYLOAD: Extra fields like pitch/pace cause 400 errors with cloned voices
    payload = {
        "inputs": [text],
        "target_language_code": f"{lang}-IN",
        "speaker": speaker,
        "model": "bulbul:v4",
        "loudness": 1.5,
        "speech_sample_rate": 22050,
        "enable_preprocessing": True,
    }
    
    r = requests.post(url, json=payload, headers=headers, timeout=30)
    if not r.ok:
        # Print the EXACT error message from Sarvam so we know why it failed
        print(f"  ⚠️ Sarvam API Error {r.status_code}: {r.text}", flush=True)
        r.raise_for_status()

    data = r.json()
    if "audios" in data and len(data["audios"]) > 0:
        pathlib.Path(wav_path).write_bytes(base64.b64decode(data["audios"][0]))
        print(f"  ✅ TTS via Sarvam ({speaker})", flush=True)
        return
    raise Exception("Sarvam returned no audio data")

def _gemini_tts(text, lang, wav_path):
    """Fallback 1: Gemini 3.8 Flash TTS"""
    from pipeline.provider_keys import gemini_keys

    keys = gemini_keys()
    if not keys:
        raise ValueError("No GEMINI_API_KEY")
    from google import genai

    for model in ["gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts"]:
        for index, key in enumerate(keys):
            try:
                client = genai.Client(
                    api_key=key, http_options={"api_version": "v1beta"})
                it = client.interactions.create(
                    model=model,
                    input=[{"type": "user_input", "content": [{
                        "type": "text", "text": text,
                        "annotations": [{"type": "speech_metadata", "style": GEMINI_STYLE}]}]}],
                    response_format={"type": "audio"},
                    generation_config={
                        "speech_config": [{"voice": GEMINI_VOICES.get(lang, "Charon")}]
                    },
                )
                pathlib.Path(wav_path).write_bytes(base64.b64decode(it.output_audio.data))
                if index:
                    print("  Gemini backup key succeeded", flush=True)
                print(f"  ✅ TTS via Gemini ({model} / {GEMINI_VOICES.get(lang)})", flush=True)
                return
            except Exception as e:
                print(f"  ⚠️ Gemini {model} key {index + 1} failed: {e}", flush=True)
    raise Exception("All Gemini models failed")

def _edge_tts(text, lang, out_path):
    """Fallback 2: Edge TTS (100% Free, Unlimited)"""
    import asyncio, edge_tts
    voices = {"hi": "hi-IN-MadhurNeural", "te": "te-IN-MohanNeural", "en": "en-US-GuyNeural"}
    async def run():
        await edge_tts.Communicate(text, voices.get(lang, voices["en"])).save(out_path)
    asyncio.run(run())
    print(f"  ✅ TTS via Edge TTS (Free Fallback)", flush=True)

def synthesize_many(items, max_workers=6):
    """Synthesise multiple (text, lang, output_path) tuples in parallel.

    Returns list of output paths in the same order as items.
    Use this whenever you have N beats/segments to synthesise — all API calls
    fire concurrently so total time ≈ slowest single call, not sum of all.
    """
    results = [None] * len(items)

    def _one(args):
        idx, text, lang, out = args
        return idx, synthesize(text, lang, out)

    with ThreadPoolExecutor(max_workers=min(len(items), max_workers)) as ex:
        futures = {ex.submit(_one, (i, t, l, o)): i for i, (t, l, o) in enumerate(items)}
        for f in as_completed(futures):
            idx, path = f.result()
            results[idx] = path
    return results


def synthesize(text, lang, output_path):
    """Main entry point: Tries Sarvam -> Gemini -> Edge TTS"""
    output_path = str(output_path)
    pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wav_path = str(pathlib.Path(output_path).with_suffix(".wav"))

    try:
        _sarvam_tts(text, lang, wav_path)
    except Exception as e:
        print(f"  ⚠️ Sarvam failed -> Trying Gemini: {e}", flush=True)
        try:
            _gemini_tts(text, lang, wav_path)
        except Exception as e2:
            print(f"  ⚠️ Gemini failed -> Trying Edge TTS: {e2}", flush=True)
            _edge_tts(text, lang, output_path)
            return output_path

    if output_path.endswith(".mp3") and shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path,
                        "-codec:a", "libmp3lame", "-qscale:a", "2", output_path], check=True)
        return output_path
    return wav_path
