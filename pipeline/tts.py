import os
import asyncio
import edge_tts
import pathlib

async def generate_tts(text, lang, output_path):
    """Generates highly natural TTS using Microsoft Edge (Free, no API key)."""
    # Map languages to natural-sounding Edge voices
    voices = {
        "hi": "hi-IN-MadhurNeural",  # Natural Hindi Male
        "te": "te-IN-MohanNeural",   # Natural Telugu Male
        "en": "en-US-GuyNeural"      # Natural English Male
    }
    
    voice = voices.get(lang, voices["en"])
    
    # Clean up text for better TTS pronunciation
    text = text.replace("#", "hashtag").replace("&", "and")
    
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)
    return output_path

def synthesize(text, lang, output_path):
    """Synchronous wrapper for asyncio TTS."""
    pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(generate_tts(text, lang, output_path))
    return output_path
