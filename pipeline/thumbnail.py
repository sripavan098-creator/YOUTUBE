"""Custom thumbnail generator for YouTube Shorts and Instagram Reels covers.

Replaces the dumb 'extract frame at 0.5s' approach with a DESIGNED thumbnail:
- Bold hook text on a gradient background
- Brand colour + accent bar
- Emoji / stat callout box
- Face-safe composition (text in lower 60% so YouTube's face detection doesn't crop it)

Output: 1280×720 JPEG for YouTube, 1080×1920 JPEG for Instagram cover.
Requires: Pillow (pip install Pillow)

If Pillow is unavailable it falls back to the ffmpeg frame extract so the pipeline
never breaks.
"""
import os
import pathlib
import textwrap
import subprocess
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "assets" / "fonts"

# Bundled fallback font paths (NotoSans covers Telugu + Hindi + Latin)
_FONT_CANDIDATES = [
    FONTS_DIR / "NotoSans-Bold.ttf",
    FONTS_DIR / "NotoSansTelugu-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _pil():
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        return Image, ImageDraw, ImageFont, ImageFilter
    except ImportError:
        return None


def _load_font(size, lang="en"):
    Image, ImageDraw, ImageFont, _ = _pil()
    # Try bundled fonts first, then system
    candidates = list(_FONT_CANDIDATES)
    if lang == "te":
        candidates.insert(0, FONTS_DIR / "NotoSansTelugu-Bold.ttf")
    elif lang == "hi":
        candidates.insert(0, FONTS_DIR / "NotoSansDevanagari-Bold.ttf")
    for path in candidates:
        if pathlib.Path(path).exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                continue
    return ImageFont.load_default()


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _darken(rgb, factor=0.55):
    return tuple(max(0, int(c * factor)) for c in rgb)


def _lighten(rgb, factor=1.4):
    return tuple(min(255, int(c * factor)) for c in rgb)


def _wrap_text(text, font, max_width, draw):
    """Word-wrap text to fit max_width pixels."""
    words = text.split()
    lines = []
    current = []
    for word in words:
        test = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def _draw_text_shadow(draw, xy, text, font, fill, shadow_offset=4, shadow_color=(0, 0, 0, 180)):
    """Draw text with a drop shadow for legibility on any background."""
    sx, sy = xy
    draw.text((sx + shadow_offset, sy + shadow_offset), text, font=font, fill=shadow_color)
    draw.text(xy, text, font=font, fill=fill)


def generate_yt(
    hook_text: str,
    brand: str,
    color: str,
    accent: str,
    lang: str,
    out_path: str,
    stat: str = "",
    emoji: str = "",
) -> str:
    """Generate a 1280×720 YouTube thumbnail. Returns out_path."""
    pil = _pil()
    if not pil:
        raise ImportError("Pillow not installed")
    Image, ImageDraw, ImageFont, ImageFilter = pil

    W, H = 1280, 720
    brand_rgb = _hex_to_rgb(color)
    accent_rgb = _hex_to_rgb(accent)
    dark_rgb = _darken(brand_rgb, 0.35)
    mid_rgb = _darken(brand_rgb, 0.60)

    # ── Background gradient (dark → brand colour) ──────────────────────────
    img = Image.new("RGB", (W, H), dark_rgb)
    draw = ImageDraw.Draw(img, "RGBA")

    # Diagonal gradient sweep
    for x in range(W):
        t = x / W
        r = int(dark_rgb[0] + (mid_rgb[0] - dark_rgb[0]) * t)
        g = int(dark_rgb[1] + (mid_rgb[1] - dark_rgb[1]) * t)
        b = int(dark_rgb[2] + (mid_rgb[2] - dark_rgb[2]) * t)
        draw.line([(x, 0), (x, H)], fill=(r, g, b))

    # Vignette overlay (corners darker)
    for i in range(120):
        alpha = int(180 * (1 - i / 120) ** 2)
        draw.rectangle([i, i, W - i, H - i], outline=(0, 0, 0, alpha))

    # ── Accent stripe (left edge) ──────────────────────────────────────────
    draw.rectangle([0, 0, 18, H], fill=accent_rgb)

    # ── Brand chip (top left) ──────────────────────────────────────────────
    brand_font = _load_font(42, lang)
    chip_text = brand.upper()
    chip_bbox = draw.textbbox((0, 0), chip_text, font=brand_font)
    chip_w = chip_bbox[2] - chip_bbox[0] + 40
    chip_h = chip_bbox[3] - chip_bbox[1] + 20
    draw.rounded_rectangle([36, 24, 36 + chip_w, 24 + chip_h], radius=12, fill=brand_rgb)
    draw.text((56, 34), chip_text, font=brand_font, fill=(255, 255, 255))

    # ── Hook text (main) ──────────────────────────────────────────────────
    hook_font_size = 100 if len(hook_text) < 30 else (80 if len(hook_text) < 50 else 64)
    hook_font = _load_font(hook_font_size, lang)
    max_text_w = W - 160
    lines = _wrap_text(hook_text, hook_font, max_text_w, draw)
    line_h = hook_font_size * 1.3
    total_text_h = len(lines) * line_h
    # Position text in lower-middle area (safe for YouTube's face zone detection)
    text_top = max(H // 2 - total_text_h // 2, 120)

    for li, line in enumerate(lines):
        y = text_top + li * line_h
        # Glow
        for dx in [-3, 0, 3]:
            for dy in [-3, 0, 3]:
                if dx or dy:
                    draw.text((80 + dx, y + dy), line, font=hook_font, fill=(*dark_rgb, 120))
        # Shadow
        draw.text((84, y + 4), line, font=hook_font, fill=(0, 0, 0, 200))
        # Main text
        draw.text((80, y), line, font=hook_font, fill=(255, 255, 255, 255))

    # ── Stat callout box (bottom right) ──────────────────────────────────
    if stat:
        stat_font = _load_font(90, lang)
        stat_bbox = draw.textbbox((0, 0), stat, font=stat_font)
        sw = stat_bbox[2] - stat_bbox[0] + 60
        sh = stat_bbox[3] - stat_bbox[1] + 30
        bx = W - sw - 50
        by = H - sh - 50
        draw.rounded_rectangle([bx - 10, by - 10, bx + sw + 10, by + sh + 10],
                                radius=22, fill=(*accent_rgb, 230))
        draw.text((bx + 20, by + 10), stat, font=stat_font, fill=(0, 0, 0, 255))

    # ── Bottom gradient bar ───────────────────────────────────────────────
    for i in range(120):
        alpha = int(220 * (i / 120) ** 1.5)
        draw.line([(0, H - 120 + i), (W, H - 120 + i)], fill=(0, 0, 0, alpha))

    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=95)
    return out_path


def generate_ig_cover(
    hook_text: str,
    brand: str,
    color: str,
    accent: str,
    lang: str,
    out_path: str,
    stat: str = "",
) -> str:
    """Generate a 1080×1920 Instagram Reel cover. Returns out_path."""
    pil = _pil()
    if not pil:
        raise ImportError("Pillow not installed")
    Image, ImageDraw, ImageFont, ImageFilter = pil

    W, H = 1080, 1920
    brand_rgb = _hex_to_rgb(color)
    accent_rgb = _hex_to_rgb(accent)
    dark_rgb = _darken(brand_rgb, 0.30)

    img = Image.new("RGB", (W, H), dark_rgb)
    draw = ImageDraw.Draw(img, "RGBA")

    # Vertical gradient
    for y in range(H):
        t = y / H
        r = int(dark_rgb[0] + (brand_rgb[0] - dark_rgb[0]) * t * 0.5)
        g = int(dark_rgb[1] + (brand_rgb[1] - dark_rgb[1]) * t * 0.5)
        b = int(dark_rgb[2] + (brand_rgb[2] - dark_rgb[2]) * t * 0.5)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Top bar
    draw.rectangle([0, 0, W, 16], fill=accent_rgb)

    # Brand chip
    brand_font = _load_font(52, lang)
    chip_text = brand.upper()
    chip_bbox = draw.textbbox((0, 0), chip_text, font=brand_font)
    chip_w = chip_bbox[2] - chip_bbox[0] + 50
    chip_h = chip_bbox[3] - chip_bbox[1] + 24
    draw.rounded_rectangle([50, 50, 50 + chip_w, 50 + chip_h], radius=16, fill=brand_rgb)
    draw.text((75, 62), chip_text, font=brand_font, fill=(255, 255, 255))

    # Hook text — large, centred, upper half
    hook_font_size = 120 if len(hook_text) < 20 else (96 if len(hook_text) < 35 else 76)
    hook_font = _load_font(hook_font_size, lang)
    max_text_w = W - 120
    lines = _wrap_text(hook_text, hook_font, max_text_w, draw)
    line_h = hook_font_size * 1.35
    total_h = len(lines) * line_h
    text_top = H // 2 - total_h // 2 - 100  # slightly above centre

    for li, line in enumerate(lines):
        y = text_top + li * line_h
        bbox = draw.textbbox((0, 0), line, font=hook_font)
        lw = bbox[2] - bbox[0]
        x = (W - lw) // 2
        draw.text((x + 4, y + 6), line, font=hook_font, fill=(0, 0, 0, 180))
        draw.text((x, y), line, font=hook_font, fill=(255, 255, 255, 255))

    # Stat box
    if stat:
        stat_font = _load_font(130, lang)
        stat_bbox = draw.textbbox((0, 0), stat, font=stat_font)
        sw = stat_bbox[2] - stat_bbox[0] + 70
        sh = stat_bbox[3] - stat_bbox[1] + 40
        bx = (W - sw) // 2
        by = text_top + int(total_h) + 60
        draw.rounded_rectangle([bx - 10, by - 10, bx + sw + 10, by + sh + 10],
                                radius=28, fill=(*accent_rgb, 230))
        draw.text((bx + 25, by + 15), stat, font=stat_font, fill=(0, 0, 0, 255))

    # Bottom vignette
    for i in range(300):
        alpha = int(200 * (i / 300) ** 1.5)
        draw.line([(0, H - 300 + i), (W, H - 300 + i)], fill=(0, 0, 0, alpha))

    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=92)
    return out_path


def make_thumbnails(
    sid: str,
    channel: str,
    lcfg: dict,
    script: dict,
    video_path: str,
) -> tuple:
    """Generate both YT thumbnail and IG cover for a rendered video.

    Returns (yt_thumb_path, ig_cover_path). Either can be None on failure.
    Falls back to ffmpeg frame extract if Pillow is unavailable.
    """
    color = lcfg.get("color", "#FF6B00")
    accent = lcfg.get("accent", "#FFD166")
    brand = lcfg.get("brand", channel)
    lang = lcfg.get("lang", "hi")

    hook = script.get("hook_text") or script.get("title", "")[:40]
    # Find the most prominent stat in the script (first "stat" beat value)
    stat = ""
    for b in script.get("beats", []):
        if b.get("stat"):
            stat = b["stat"]
            break

    yt_path = str(ROOT / "out" / f"{sid}_{channel}_thumb.jpg")
    ig_path = str(ROOT / "out" / f"{sid}_{channel}_ig_cover.jpg")

    yt_ok, ig_ok = None, None

    # Try designed thumbnail first
    if _pil():
        try:
            generate_yt(hook, brand, color, accent, lang, yt_path, stat=stat)
            print(f"  [thumb] ✅ designed YT thumbnail → {pathlib.Path(yt_path).name}", flush=True)
            yt_ok = yt_path
        except Exception as e:
            print(f"  [thumb] designed YT failed: {e}", flush=True)

        try:
            generate_ig_cover(hook, brand, color, accent, lang, ig_path, stat=stat)
            print(f"  [thumb] ✅ designed IG cover → {pathlib.Path(ig_path).name}", flush=True)
            ig_ok = ig_path
        except Exception as e:
            print(f"  [thumb] designed IG failed: {e}", flush=True)

    # Fallback: ffmpeg frame extract for YT
    if not yt_ok and video_path and pathlib.Path(video_path).is_file():
        try:
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", str(video_path),
                 "-frames:v", "1", "-q:v", "2",
                 "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,"
                        "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black",
                 yt_path], check=True, timeout=30)
            yt_ok = yt_path
            print(f"  [thumb] ⚠️  ffmpeg fallback YT thumbnail", flush=True)
        except Exception as e:
            print(f"  [thumb] ffmpeg YT failed: {e}", flush=True)

    # Fallback: ffmpeg frame extract for IG
    if not ig_ok and video_path and pathlib.Path(video_path).is_file():
        try:
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", str(video_path),
                 "-frames:v", "1", "-q:v", "2",
                 "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",
                 ig_path], check=True, timeout=30)
            ig_ok = ig_path
        except Exception as e:
            print(f"  [thumb] ffmpeg IG failed: {e}", flush=True)

    return yt_ok, ig_ok
