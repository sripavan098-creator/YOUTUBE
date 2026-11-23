import os


def groq_keys():
    """Return configured Groq keys in priority order, without duplicates."""
    names = (
        "GROQ_API_KEY",
        "GROQ_API_KEY_2",
        "groq_api_key",
        "groq_api_key_2",
    )
    keys = []
    for name in names:
        value = os.environ.get(name, "").strip()
        if value and value not in keys:
            keys.append(value)
    return keys


def gemini_keys():
    """Return configured Gemini keys in priority order, without duplicates."""
    names = (
        "GEMINI_API_KEY",
        "GEMINI_API_KEY_2",
        "gemini_api_key",
        "gemini_api_key_2",
    )
    keys = []
    for name in names:
        value = os.environ.get(name, "").strip()
        if value and value not in keys:
            keys.append(value)
    return keys
