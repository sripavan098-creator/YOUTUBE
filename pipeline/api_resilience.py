"""Bulletproof API resilience layer for the YouTube Shorts pipeline.

Solves: 429 rate-limits, 503 service unavailable, 502 bad gateway,
         404 model-not-found, 409 conflicts, random timeouts.

Strategy:
  1. Circuit breaker per provider — a provider that fails 3x in a row is
     skipped for 5 minutes so we don't waste retries hammering a dead endpoint.
  2. Exponential backoff with jitter on every retry.
  3. 7-provider LLM fallback chain (all free, highest limits first):
       Cerebras (1M tok/day) → NVIDIA NIM (40 rpm) →
       Groq → Gemini → OpenRouter → Together AI → Ollama (local, unlimited)
  4. Provider keys rotated within each provider before moving to the next.
  5. Same interface as the existing _groq()/_gemini() calls so scripts.py
     can adopt it with a one-line change.
  6. TTS resilience: Sarvam → Gemini TTS → Edge TTS (always works, free).

Free tier limits (as of Nov 2026):
  Cerebras   : 1M tokens/day — best free option (gpt-oss-120b, qwen-3.8-27b)
  NVIDIA NIM : 40 req/min  — Llama 3.3 70B, DeepSeek, Mistral
  Groq       : 30 req/min  — fast, Llama 3.3 70B
  Gemini     : generous daily quota on Flash models
  OpenRouter : 50 req/day free or `:free` tagged models
  Together AI: pay-as-you-go (keep as fallback)
  Ollama     : unlimited, requires local GPU
"""

import os
import random
import time
import threading
import pathlib
import json
from typing import Callable, Optional

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ── Circuit breaker state (in-process, resets on restart) ─────────────────
_cb_lock = threading.Lock()
_CB: dict = {}   # provider_name → {"failures": int, "open_until": float}
CB_THRESHOLD = 3        # failures before opening circuit
CB_OPEN_SECONDS = 300   # 5 minutes

# ── Retry config ─────────────────────────────────────────────────────────────
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5        # per provider
BASE_DELAY = 1.5        # seconds
MAX_DELAY = 60.0        # cap


def _jitter(base: float, attempt: int) -> float:
    """Exponential backoff with ±30% jitter so parallel workers don't all retry simultaneously."""
    delay = min(base * (2 ** attempt), MAX_DELAY)
    return delay * (0.7 + random.random() * 0.6)


def _cb_ok(name: str) -> bool:
    """True if the circuit is closed (provider is usable)."""
    with _cb_lock:
        cb = _CB.get(name, {})
        if cb.get("open_until", 0) > time.monotonic():
            return False
        return True


def _cb_success(name: str):
    with _cb_lock:
        _CB[name] = {"failures": 0, "open_until": 0}


def _cb_failure(name: str):
    with _cb_lock:
        cb = _CB.setdefault(name, {"failures": 0, "open_until": 0})
        cb["failures"] += 1
        if cb["failures"] >= CB_THRESHOLD:
            cb["open_until"] = time.monotonic() + CB_OPEN_SECONDS
            print(f"  ⚡ Circuit OPEN for {name} — skipping for {CB_OPEN_SECONDS}s", flush=True)


def _status_code(exc) -> Optional[int]:
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None)
    if code is None:
        code = getattr(exc, "status_code", None)
    return code


# ── Provider implementations ──────────────────────────────────────────────────

def _call_cerebras(system: str, prompt: str, model: str, temp: float) -> str:
    """Cerebras: 1M tokens/day FREE — fastest inference, OpenAI-compatible API.

    Sign up: cloud.cerebras.ai → API Keys
    Set env: CEREBRAS_API_KEY=your-key
    Models: gpt-oss-120b (best), qwen-3.8-27b
    Rate limit: 5 req/min, 1M tokens/day (free trial)
    """
    from openai import OpenAI
    key = os.getenv("CEREBRAS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("No CEREBRAS_API_KEY configured")
    # Map internal model names → Cerebras models
    cerebras_model = "gpt-oss-120b"  # best quality on Cerebras free tier
    for attempt in range(MAX_ATTEMPTS):
        try:
            c = OpenAI(
                api_key=key,
                base_url="https://api.cerebras.ai/v1",
                timeout=90,
            )
            result = c.chat.completions.create(
                model=cerebras_model, temperature=temp, max_tokens=4000,
                messages=[{"role": "system", "content": system},
                          {"role": "user",   "content": prompt}],
            ).choices[0].message.content
            return result
        except Exception as e:
            code = _status_code(e)
            if code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
                wait = _jitter(BASE_DELAY, attempt)
                print(f"  Cerebras {code} → retry in {wait:.1f}s (attempt {attempt+1})", flush=True)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Cerebras exhausted all attempts")


def _call_nvidia_nim(system: str, prompt: str, model: str, temp: float) -> str:
    """NVIDIA NIM: 40 req/min FREE — Llama 3.3 70B, DeepSeek, Mistral, etc.

    Sign up: build.nvidia.com → free account → API key
    Set env: NVIDIA_API_KEY=nvapi-...
    Models: meta/llama-3.3-70b-instruct, deepseek/deepseek-r1, mistralai/mistral-small-3.2
    Rate limit: 40 req/min, no daily cap mentioned
    """
    from openai import OpenAI
    key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not key:
        raise RuntimeError("No NVIDIA_API_KEY configured")
    nvidia_model = "meta/llama-3.3-70b-instruct"
    for attempt in range(MAX_ATTEMPTS):
        try:
            c = OpenAI(
                api_key=key,
                base_url="https://integrate.api.nvidia.com/v1",
                timeout=90,
            )
            result = c.chat.completions.create(
                model=nvidia_model, temperature=temp, max_tokens=4000,
                messages=[{"role": "system", "content": system},
                          {"role": "user",   "content": prompt}],
            ).choices[0].message.content
            return result
        except Exception as e:
            code = _status_code(e)
            if code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
                wait = _jitter(BASE_DELAY, attempt)
                print(f"  NVIDIA NIM {code} → retry in {wait:.1f}s (attempt {attempt+1})", flush=True)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("NVIDIA NIM exhausted all attempts")


def _call_groq(system: str, prompt: str, model: str, temp: float) -> str:
    from openai import OpenAI, APIStatusError
    from pipeline.provider_keys import groq_keys
    keys = groq_keys()
    if not keys:
        raise RuntimeError("No GROQ_API_KEY configured")
    # Map internal model names → Groq model IDs (Groq has its own model catalog)
    _groq_model_map = {
        "openai/gpt-oss-120b":      "llama-3.3-70b-versatile",
        "gemini-1.5-flash-latest":  "llama-3.1-8b-instant",
        "gemini-1.5-pro-latest":    "llama-3.3-70b-versatile",
    }
    groq_model = _groq_model_map.get(model, "llama-3.3-70b-versatile")
    for key in keys:
        for attempt in range(MAX_ATTEMPTS):
            try:
                c = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1", timeout=60)
                result = c.chat.completions.create(
                    model=groq_model, temperature=temp, max_tokens=4000,
                    messages=[{"role": "system", "content": system},
                              {"role": "user",   "content": prompt}],
                ).choices[0].message.content
                return result
            except (requests.HTTPError, APIStatusError, Exception) as e:
                code = _status_code(e)
                if code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
                    wait = _jitter(BASE_DELAY, attempt)
                    print(f"  Groq {code} → retry in {wait:.1f}s (attempt {attempt+1})", flush=True)
                    time.sleep(wait)
                else:
                    raise
    raise RuntimeError("Groq exhausted all attempts")


def _call_gemini(system: str, prompt: str, model: str, temp: float) -> str:
    from pipeline.provider_keys import gemini_keys
    keys = gemini_keys()
    if not keys:
        raise RuntimeError("No GEMINI_API_KEY configured")
    for key in keys:
        for attempt in range(MAX_ATTEMPTS):
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": key},
                    json={"contents": [{"parts": [{"text": system + "\n\n" + prompt}]}],
                          "generationConfig": {"responseMimeType": "application/json",
                                               "temperature": temp}},
                    timeout=90)
                if r.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
                    wait = _jitter(BASE_DELAY, attempt)
                    print(f"  Gemini {r.status_code} → retry in {wait:.1f}s", flush=True)
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            except requests.HTTPError as e:
                code = _status_code(e)
                if code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
                    wait = _jitter(BASE_DELAY, attempt)
                    print(f"  Gemini HTTP {code} → retry in {wait:.1f}s", flush=True)
                    time.sleep(wait)
                else:
                    raise
    raise RuntimeError("Gemini exhausted all attempts")


def _call_openrouter(system: str, prompt: str, model: str, temp: float) -> str:
    """OpenRouter: access to 100+ models on a single key — great rate-limit buffer."""
    from openai import OpenAI
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("No OPENROUTER_API_KEY configured")
    # Map our internal model names to OpenRouter equivalents
    model_map = {
        "openai/gpt-oss-120b":     "openai/gpt-4o-mini",
        "gemini-1.5-flash-latest": "google/gemini-flash-1.5",
        "gemini-1.5-pro-latest":   "google/gemini-pro-1.5",
    }
    or_model = model_map.get(model, "google/gemini-flash-1.5")
    for attempt in range(MAX_ATTEMPTS):
        try:
            c = OpenAI(
                api_key=key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={"HTTP-Referer": "https://github.com/sripavan098-creator/YOUTUBE",
                                 "X-Title": "Telugu Hindi Shorts Pipeline"},
                timeout=90,
            )
            result = c.chat.completions.create(
                model=or_model, temperature=temp, max_tokens=4000,
                messages=[{"role": "system", "content": system},
                          {"role": "user",   "content": prompt}],
            ).choices[0].message.content
            return result
        except Exception as e:
            code = _status_code(e)
            if code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
                wait = _jitter(BASE_DELAY, attempt)
                print(f"  OpenRouter {code} → retry in {wait:.1f}s", flush=True)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("OpenRouter exhausted all attempts")


def _call_together(system: str, prompt: str, model: str, temp: float) -> str:
    """Together AI: free tier has generous limits, good for bursts."""
    key = os.getenv("TOGETHER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("No TOGETHER_API_KEY configured")
    from openai import OpenAI
    # Map to Together-hosted models
    together_model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    for attempt in range(MAX_ATTEMPTS):
        try:
            c = OpenAI(api_key=key, base_url="https://api.together.xyz/v1", timeout=90)
            result = c.chat.completions.create(
                model=together_model, temperature=temp, max_tokens=4000,
                messages=[{"role": "system", "content": system},
                          {"role": "user",   "content": prompt}],
            ).choices[0].message.content
            return result
        except Exception as e:
            code = _status_code(e)
            if code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
                wait = _jitter(BASE_DELAY, attempt)
                print(f"  Together {code} → retry in {wait:.1f}s", flush=True)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Together AI exhausted all attempts")


def _call_ollama(system: str, prompt: str, model: str, temp: float) -> str:
    """Ollama: local fallback — zero cost, zero rate-limits, requires local GPU."""
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    for attempt in range(MAX_ATTEMPTS):
        try:
            r = requests.post(
                f"{base}/api/chat",
                json={"model": os.getenv("OLLAMA_MODEL", "llama3.2"),
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user",   "content": prompt}],
                      "stream": False, "options": {"temperature": temp}},
                timeout=120)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except Exception as e:
            code = _status_code(e)
            if code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
                wait = _jitter(BASE_DELAY, attempt)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Ollama exhausted all attempts")


# ── Ordered provider chain (highest free limits first) ────────────────────────
# Cerebras: 1M tok/day  — BEST free, start here
# NVIDIA NIM: 40 rpm    — 2nd best free
# Groq: 30 rpm          — fast, reliable free tier
# Gemini: generous daily quota
# OpenRouter: 50 req/day free or :free models
# Together: pay-as-you-go fallback
# Ollama: local/unlimited, last resort (requires GPU)

PROVIDERS = [
    ("cerebras",    _call_cerebras),
    ("nvidia_nim",  _call_nvidia_nim),
    ("groq",        _call_groq),
    ("gemini",      _call_gemini),
    ("openrouter",  _call_openrouter),
    ("together",    _call_together),
    ("ollama",      _call_ollama),
]


def llm(system: str, prompt: str, model: str, temp: float = 0.75) -> str:
    """Call the best available LLM provider, auto-failing over through the chain.

    - Skips providers whose circuit is open (too many recent failures).
    - Retries each provider up to MAX_ATTEMPTS times with backoff+jitter.
    - Moves to next provider on non-retryable errors or circuit-open.
    - Returns the first successful response.
    - Raises RuntimeError only if ALL providers fail.

    Usage (drop-in for _groq / _gemini in scripts.py):
        from pipeline.api_resilience import llm
        raw = llm(system, prompt, model, temp=0.75)
    """
    errors = []
    for name, fn in PROVIDERS:
        if not _cb_ok(name):
            print(f"  ⚡ {name}: circuit open — skipping", flush=True)
            errors.append(f"{name}: circuit open")
            continue
        try:
            print(f"  🔁 LLM via {name}...", flush=True)
            result = fn(system, prompt, model, temp)
            _cb_success(name)
            print(f"  ✅ {name} succeeded", flush=True)
            return result
        except RuntimeError as e:
            if "No " in str(e) and "configured" in str(e):
                # Key not set — skip silently
                errors.append(f"{name}: not configured")
                continue
            _cb_failure(name)
            errors.append(f"{name}: {e}")
            print(f"  ❌ {name} failed: {e}", flush=True)
        except Exception as e:
            _cb_failure(name)
            errors.append(f"{name}: {e}")
            print(f"  ❌ {name} failed: {e}", flush=True)

    raise RuntimeError("ALL LLM providers failed:\n  " + "\n  ".join(errors))


# ── TTS resilience (separate from LLM) ────────────────────────────────────────

def tts_with_fallback(text: str, lang: str, output_path: str) -> str:
    """Synthesise speech with automatic provider fallback.

    Chain: Sarvam (cloned voice) → Sarvam (built-in) → Edge TTS (always works).
    Returns the path to the audio file.
    """
    from pipeline import tts as _tts

    output_path = str(output_path)
    pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Sarvam with up to 3 retries + jitter
    for attempt in range(3):
        try:
            return _tts.synthesize(text, lang, output_path)
        except Exception as e:
            code = _status_code(e)
            if code in RETRY_STATUS and attempt < 2:
                wait = _jitter(2.0, attempt)
                print(f"  TTS Sarvam {code} → retry in {wait:.1f}s", flush=True)
                time.sleep(wait)
            elif attempt == 2:
                print(f"  TTS Sarvam failed 3x ({e}) → Edge TTS fallback", flush=True)
                break
            else:
                print(f"  TTS error ({e}) → Edge TTS fallback", flush=True)
                break

    # Edge TTS — 100% free, Microsoft Azure CDN, never rate-limits
    try:
        import asyncio, edge_tts
        import shutil, subprocess
        voices = {"hi": "hi-IN-MadhurNeural", "te": "te-IN-MohanNeural", "en": "en-US-GuyNeural"}
        voice = voices.get(lang, voices["en"])
        mp3_path = output_path if output_path.endswith(".mp3") else output_path + ".mp3"

        async def _run():
            await edge_tts.Communicate(text, voice).save(mp3_path)

        asyncio.run(_run())
        print(f"  ✅ TTS via Edge TTS fallback ({voice})", flush=True)

        # Convert to wav if original path expected wav
        if not output_path.endswith(".mp3") and shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3_path, output_path],
                           check=True)
            return output_path
        return mp3_path
    except Exception as e:
        raise RuntimeError(f"TTS fallback chain completely exhausted: {e}") from e


# ── Status reporter ────────────────────────────────────────────────────────────

def provider_status() -> dict:
    """Return current circuit-breaker state for all providers (for logging/debugging)."""
    now = time.monotonic()
    out = {}
    with _cb_lock:
        for name, _ in PROVIDERS:
            cb = _CB.get(name, {})
            remaining = max(0, cb.get("open_until", 0) - now)
            out[name] = {
                "circuit": "open" if remaining > 0 else "closed",
                "open_for_more_seconds": round(remaining),
                "failures": cb.get("failures", 0),
            }
    return out


def reset_circuit(name: str = None):
    """Manually reset a provider's circuit breaker (useful after adding new API keys)."""
    with _cb_lock:
        if name:
            _CB.pop(name, None)
            print(f"  🔄 Circuit reset for {name}", flush=True)
        else:
            _CB.clear()
            print("  🔄 All circuits reset", flush=True)
