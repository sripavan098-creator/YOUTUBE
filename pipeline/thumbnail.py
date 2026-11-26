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


def _draw_neon_glow(draw, xy, text, font, fill, glow_color, spread=12):
    """Draw text with a wide neon glow effect that pops on dark backgrounds."""
    x, y = xy
    for radius in range(spread, 0, -4):
        alpha = int(80 * (1 - radius / spread))
        for dx in range(-radius, radius + 1, max(1, radius // 3)):
            for dy in range(-radius, radius + 1, max(1, radius // 3)):
                draw.text((x + dx, y + dy), text, font=font,
                          fill=(*glow_color[:3], alpha))
    # Crisp shadow
    draw.text((x + 4, y + 5), text, font=font, fill=(0, 0, 0, 220))
    # Main text
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
    bg_image_path: str = "",
) -> str:
    """Generate a 1280×720 YouTube thumbnail. Returns out_path.

    Viral design principles applied:
    - Real photo background (from Pixabay/Unsplash) with dark overlay — far more
      CTR than solid colour; falls back to dark gradient if no image available
    - Hook text: huge, bold, neon glow — readable on mobile at 120×90px preview
    - Accent bar + brand chip: brand recognition in <0.3s
    - Stat box: big number in accent pill (most clicked thumbnails have a number)
    - Bottom gradient for depth and text contrast
    """
    pil = _pil()
    if not pil:
        raise ImportError("Pillow not installed")
    Image, ImageDraw, ImageFont, ImageFilter = pil

    W, H = 1280, 720
    brand_rgb = _hex_to_rgb(color)
    accent_rgb = _hex_to_rgb(accent)

    bg_dark = (14, 14, 20)
    bg_mid = (28, 28, 38)

    # ── Background: real photo OR dark gradient ───────────────────────────────
    if bg_image_path and pathlib.Path(bg_image_path).is_file():
        try:
            bg = Image.open(bg_image_path).convert("RGB")
            # Crop to fill 1280×720 without distortion
            bg_w, bg_h = bg.size
            scale = max(W / bg_w, H / bg_h)
            new_w, new_h = int(bg_w * scale), int(bg_h * scale)
            bg = bg.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - W) // 2
            top = (new_h - H) // 2
            bg = bg.crop((left, top, left + W, top + H))
            img = bg
        except Exception as e:
            print(f"  [thumb] bg image load failed: {e} — using gradient", flush=True)
            img = Image.new("RGB", (W, H), bg_dark)
            draw_tmp = ImageDraw.Draw(img, "RGBA")
            for x in range(W):
                t = x / W
                r = int(bg_dark[0] + (bg_mid[0] - bg_dark[0]) * t)
                g = int(bg_dark[1] + (bg_mid[1] - bg_dark[1]) * t)
                b = int(bg_dark[2] + (bg_mid[2] - bg_dark[2]) * t)
                draw_tmp.line([(x, 0), (x, H)], fill=(r, g, b))
    else:
        img = Image.new("RGB", (W, H), bg_dark)
        draw_tmp = ImageDraw.Draw(img, "RGBA")
        for x in range(W):
            t = x / W
            r = int(bg_dark[0] + (bg_mid[0] - bg_dark[0]) * t)
            g = int(bg_dark[1] + (bg_mid[1] - bg_dark[1]) * t)
            b = int(bg_dark[2] + (bg_mid[2] - bg_dark[2]) * t)
            draw_tmp.line([(x, 0), (x, H)], fill=(r, g, b))

    draw = ImageDraw.Draw(img, "RGBA")

    # Dark overlay so text is always readable regardless of photo content
    # Uses a gradient: heavier on the left (where text goes), lighter on right
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    for x in range(W):
        # Left side: 70% dark, right side: 40% dark
        alpha = int(180 - 80 * (x / W))
        ov_draw.line([(x, 0), (x, H)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    # ── Brand colour top bar (thin, identity anchor) ─────────────────────────
    draw.rectangle([0, 0, W, 10], fill=brand_rgb)

    # ── Left neon accent stripe ───────────────────────────────────────────────
    for i, w in enumerate([22, 10, 4]):
        alpha = [255, 160, 80][i]
        draw.rectangle([0, 0, w, H], fill=(*accent_rgb, alpha))

    # ── Brand chip (top-left) ─────────────────────────────────────────────────
    brand_font = _load_font(38, lang)
    chip_text = brand.upper()
    chip_bbox = draw.textbbox((0, 0), chip_text, font=brand_font)
    chip_w = chip_bbox[2] - chip_bbox[0] + 36
    chip_h = chip_bbox[3] - chip_bbox[1] + 18
    draw.rounded_rectangle([40, 20, 40 + chip_w, 20 + chip_h], radius=10,
                            fill=(*brand_rgb, 230))
    draw.text((58, 29), chip_text, font=brand_font, fill=(255, 255, 255, 255))

    # ── Hook text — split lines, first word or key number highlighted ─────────
    hook_font_size = 108 if len(hook_text) <= 24 else (88 if len(hook_text) <= 40 else 70)
    hook_font = _load_font(hook_font_size, lang)
    max_text_w = W - 180  # leave room for accent stripe + padding
    lines = _wrap_text(hook_text, hook_font, max_text_w, draw)
    line_h = int(hook_font_size * 1.28)
    total_text_h = len(lines) * line_h

    # Vertically centre text, biased slightly upward (more space below for stat)
    text_top = max(80, H // 2 - total_text_h // 2 - 30)

    for li, line in enumerate(lines):
        y = int(text_top + li * line_h)
        x = 70  # left-aligned, offset for accent stripe

        # Check if line contains a number/stat — highlight it in accent colour
        has_number = bool(re.search(r'[\d₹$%]', line))
        text_fill = (255, 255, 255, 255)
        glow = accent_rgb if has_number else brand_rgb

        _draw_neon_glow(draw, (x, y), line, hook_font, text_fill, glow, spread=14)

    # ── Stat / number callout pill (bottom-right corner) ─────────────────────
    if stat:
        stat_font_size = 86
        stat_font = _load_font(stat_font_size, lang)
        stat_bbox = draw.textbbox((0, 0), stat, font=stat_font)
        sw = stat_bbox[2] - stat_bbox[0] + 56
        sh = stat_bbox[3] - stat_bbox[1] + 28
        margin = 50
        bx = W - sw - margin
        by = H - sh - margin
        # Pill with brand colour + slight glow
        for expand in [16, 8, 0]:
            alpha = [60, 120, 240][expand // 8] if expand else 240
            draw.rounded_rectangle(
                [bx - expand, by - expand, bx + sw + expand, by + sh + expand],
                radius=28 + expand,
                fill=(*accent_rgb, alpha)
            )
        draw.text((bx + 20, by + 10), stat, font=stat_font, fill=(0, 0, 0, 255))

    # ── Emoji (top-right if provided) ────────────────────────────────────────
    if emoji:
        try:
            em_font = _load_font(90, "en")
            draw.text((W - 120, 20), emoji, font=em_font, fill=(255, 255, 255, 255))
        except Exception:
            pass

    # ── Bottom vignette for depth ─────────────────────────────────────────────
    for i in range(160):
        alpha = int(190 * (i / 160) ** 1.8)
        draw.line([(0, H - 160 + i), (W, H - 160 + i)], fill=(0, 0, 0, alpha))

    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=96, optimize=True)
    return out_path


def generate_ig_cover(
    hook_text: str,
    brand: str,
    color: str,
    accent: str,
    lang: str,
    out_path: str,
    stat: str = "",
    bg_image_path: str = "",
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

    # ── Background: real photo OR dark gradient ───────────────────────────────
    if bg_image_path and pathlib.Path(bg_image_path).is_file():
        try:
            bg = Image.open(bg_image_path).convert("RGB")
            bg_w, bg_h = bg.size
            scale = max(W / bg_w, H / bg_h)
            new_w, new_h = int(bg_w * scale), int(bg_h * scale)
            bg = bg.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - W) // 2
            top = (new_h - H) // 2
            bg = bg.crop((left, top, left + W, top + H))
            img = bg
        except Exception:
            img = Image.new("RGB", (W, H), dark_rgb)
    else:
        img = Image.new("RGB", (W, H), dark_rgb)

    draw = ImageDraw.Draw(img, "RGBA")

    # Dark overlay — heavier at top and bottom for text zones
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    for y in range(H):
        # Stronger at top (brand) and bottom (CTA), lighter in middle
        t = y / H
        alpha = int(160 + 60 * abs(t - 0.5) * 2)
        ov_draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")

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

    # ── Fetch a real background image (Pixabay → Unsplash → Pexels → Wikimedia) ──
    bg_image = None
    try:
        from pipeline.images import fetch_background_for_script
        bg_image = fetch_background_for_script(script, lang=lang)
        if bg_image:
            print(f"  [thumb] real photo background fetched", flush=True)
        else:
            print(f"  [thumb] no photo available — using gradient background", flush=True)
    except Exception as e:
        print(f"  [thumb] image fetch error: {e} — using gradient", flush=True)

    # Try designed thumbnail first
    if _pil():
        try:
            generate_yt(hook, brand, color, accent, lang, yt_path, stat=stat,
                        bg_image_path=bg_image or "")
            print(f"  [thumb] ✅ designed YT thumbnail → {pathlib.Path(yt_path).name}", flush=True)
            yt_ok = yt_path
        except Exception as e:
            print(f"  [thumb] designed YT failed: {e}", flush=True)

        try:
            generate_ig_cover(hook, brand, color, accent, lang, ig_path, stat=stat,
                              bg_image_path=bg_image or "")
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
