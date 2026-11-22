import base64
import os
import pathlib

import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
VOICE_SAMPLE_DIR = ROOT / "assets" / "voice_samples"
SUPPORTED_AUDIO_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg"}
SARVAM_MAX_AUDIO_BYTES = 50 * 1024 * 1024


def _audio_mime_type(path: pathlib.Path) -> str:
    try:
        return SUPPORTED_AUDIO_TYPES[path.suffix.lower()]
    except KeyError as exc:
        raise ValueError(f"Unsupported audio format: {path.suffix}") from exc


def _samples_in(directory: pathlib.Path) -> list[pathlib.Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_TYPES
    ) if directory.is_dir() else []


def find_voice_sample(root: pathlib.Path = ROOT) -> pathlib.Path:
    sample_dir = root / "assets" / "voice_samples"
    preferred = sample_dir / "my_voice.wav"
    if preferred.is_file():
        return preferred

    candidates = _samples_in(sample_dir)
    if not candidates:
        preferred = root / "my_voice.wav"
        if preferred.is_file():
            return preferred
        candidates = _samples_in(root)

    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        names = ", ".join(path.name for path in candidates)
        raise RuntimeError(
            f"Multiple voice samples found ({names}); keep one or add "
            "assets/voice_samples/my_voice.wav."
        )
    raise FileNotFoundError(
        "No .wav or .mp3 voice sample found. Add "
        "assets/voice_samples/my_voice.wav."
    )


def _response_json(response: requests.Response, provider: str) -> dict:
    if not response.ok:
        detail = response.text.strip() or "no response body"
        raise RuntimeError(f"{provider} returned HTTP {response.status_code}: {detail}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{provider} returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{provider} returned an unexpected response.")
    return payload


def register_sarvam(
    sample_path: pathlib.Path,
    api_key: str,
    language: str = "te-IN",
) -> str:
    if sample_path.stat().st_size > SARVAM_MAX_AUDIO_BYTES:
        raise ValueError("Sarvam voice samples must be 50 MB or smaller.")

    with sample_path.open("rb") as audio_file:
        response = requests.post(
            "https://api.sarvam.ai/voices/create",
            headers={"api-subscription-key": api_key},
            files={
                "file": (
                    sample_path.name,
                    audio_file,
                    _audio_mime_type(sample_path),
                )
            },
            data={
                "name": "my-cloned-voice",
                "language": language,
                "style": "conversational",
                "remove_background_noise": "true",
            },
            timeout=120,
        )

    payload = _response_json(response, "Sarvam")
    data = payload.get("data")
    voice_id = data.get("voice_id") if isinstance(data, dict) else None
    if not isinstance(voice_id, str) or not voice_id:
        raise RuntimeError("Sarvam response did not contain data.voice_id.")
    return voice_id


def register_gemini(
    sample_path: pathlib.Path,
    consent_path: pathlib.Path,
    api_key: str,
) -> str:
    if sample_path.resolve() == consent_path.resolve():
        raise ValueError("Google requires a separate recording of the consent phrase.")

    sample_data = base64.b64encode(sample_path.read_bytes()).decode("ascii")
    consent_data = base64.b64encode(consent_path.read_bytes()).decode("ascii")
    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/voices",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "voice": {
                "type": "replicated",
                "display_name": "my-cloned-voice",
                "replicated": {
                    "source_audio": {
                        "data": sample_data,
                        "mime_type": _audio_mime_type(sample_path),
                    },
                    "consent_audio": {
                        "data": consent_data,
                        "mime_type": _audio_mime_type(consent_path),
                    },
                },
            },
            "store": True,
        },
        timeout=120,
    )

    payload = _response_json(response, "Google")
    voice = payload.get("voice", payload)
    voice_id = voice.get("id") if isinstance(voice, dict) else None
    if not isinstance(voice_id, str) or not voice_id:
        raise RuntimeError("Google response did not contain a voice id.")
    return voice_id


def main() -> int:
    load_dotenv(ROOT / ".env")
    sarvam_key = os.getenv("SARVAM_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not sarvam_key and not gemini_key:
        print("❌ Set SARVAM_API_KEY and/or GEMINI_API_KEY in .env.")
        return 1

    try:
        sample_path = find_voice_sample()
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"❌ {exc}")
        return 1

    print(f"🎙️ Found voice sample: {sample_path.name}")
    sarvam_id = None
    gemini_id = None
    failed = False

    if sarvam_key:
        print("🔄 Registering with Sarvam AI...")
        try:
            sarvam_id = register_sarvam(
                sample_path,
                sarvam_key,
                os.getenv("SARVAM_VOICE_LANGUAGE", "te-IN").strip() or "te-IN",
            )
            print(f"✅ Sarvam Voice ID: {sarvam_id}")
        except (requests.RequestException, RuntimeError, ValueError, OSError) as exc:
            print(f"❌ Sarvam registration failed: {exc}")
            failed = True
    else:
        print("ℹ️ Skipping Sarvam: SARVAM_API_KEY is not set.")

    if gemini_key:
        consent_setting = os.getenv(
            "GEMINI_CONSENT_AUDIO", "assets/voice_samples/consent.wav"
        ).strip()
        consent_path = pathlib.Path(consent_setting).expanduser()
        if not consent_path.is_absolute():
            consent_path = ROOT / consent_path

        if not consent_path.is_file():
            print(
                "❌ Google registration requires a separate recording of the "
                "required consent phrase. Set GEMINI_CONSENT_AUDIO to its path."
            )
            failed = True
        else:
            print("🔄 Registering with Google...")
            try:
                gemini_id = register_gemini(sample_path, consent_path, gemini_key)
                print(f"✅ Google Voice ID: {gemini_id}")
            except (requests.RequestException, RuntimeError, ValueError, OSError) as exc:
                print(f"❌ Google registration failed: {exc}")
                failed = True
    else:
        print("ℹ️ Skipping Google: GEMINI_API_KEY is not set.")

    lines = []
    if sarvam_id:
        lines.extend(
            [
                f"SARVAM_VOICE_TE={sarvam_id}",
                f"SARVAM_VOICE_HI={sarvam_id}",
            ]
        )
    if gemini_id:
        lines.extend(
            [
                f"TTS_VOICE_TE={gemini_id}",
                f"TTS_VOICE_HI={gemini_id}",
            ]
        )
    if lines:
        print("\nAdd these lines to your .env file:")
        print("\n".join(lines))
    elif not failed:
        print("❌ No voice was registered.")
        failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
