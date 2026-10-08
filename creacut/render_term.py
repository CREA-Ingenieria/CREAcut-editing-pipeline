"""Stage 8c — Render key-term overlay frames with Pillow."""

import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .common import TERM_DISPLAY_DURATION, TermOverlay, find_font

# ── Panel position in the frame ─────────────────────────────────────────────
TERM_X_FRAC = 0.55
TERM_Y_FRAC = 0.78
TERM_W_FRAC = 0.40
TERM_H_FRAC = 0.16

# ── Panel ────────────────────────────────────────────────────────────────────
ACCENT_BAR_W  = 5

# ── Text ─────────────────────────────────────────────────────────────────────
TERM_COLOR    = (26,  29,  33)
DEF_COLOR     = (69,  90,  100)

# ── Typography ───────────────────────────────────────────────────────────────
FONT_SIZE_TERM     = 26
FONT_SIZE_DEF      = 18

# ── Layout ───────────────────────────────────────────────────────────────────
PADDING_X = 20
PADDING_Y = 16

# ── Animation ────────────────────────────────────────────────────────────────
FADE_DURATION = 0.3

FONT_SIZE_MODULE = 13

# ── Phrase card mode (bold overlays with empty definition) ───────────────────
PHRASE_CARD_FONT_SIZES = [22, 19, 16]
PHRASE_CARD_MAX_LINES  = 3


def _module_display_name(slug: str) -> str:
    name = re.sub(r'^\d+-', '', slug).replace('-', ' ')
    return name.title()


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _render_term_panel(
    panel_w: int,
    panel_h: int,
    term: str,
    definition: str,
    fonts: tuple,
    font_path: str,
    bg_color: tuple[int, int, int, int],
    bg_radius: int,
    accent_color: tuple[int, int, int, int],
    module_slug: str = "",
) -> Image.Image:
    font_term, font_def = fonts

    img = Image.new("RGBA", (panel_w, panel_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([0, 0, panel_w, panel_h], radius=bg_radius, fill=bg_color)
    draw.rectangle([0, 0, ACCENT_BAR_W, panel_h], fill=accent_color)

    text_x = PADDING_X + ACCENT_BAR_W + 4
    text_max_w = panel_w - text_x - PADDING_X

    if not definition and not module_slug:
        term_lines = _wrap_text(term, font_term, text_max_w)
        line_h = font_term.size + 4
        total_h = len(term_lines) * line_h - 4
        cy = max(PADDING_Y, (panel_h - total_h) // 2)
        for line in term_lines:
            draw.text((text_x, cy), line, fill=TERM_COLOR, font=font_term)
            cy += line_h
        return img

    cy = PADDING_Y

    if module_slug:
        font_module = ImageFont.truetype(font_path, FONT_SIZE_MODULE)
        label = _module_display_name(module_slug)
        draw.text((text_x, cy), label, fill=DEF_COLOR, font=font_module)
        cy += FONT_SIZE_MODULE + 5

    for line in _wrap_text(term, font_term, text_max_w):
        draw.text((text_x, cy), line, fill=TERM_COLOR, font=font_term)
        cy += font_term.size + 4

    cy += 4

    for line in _wrap_text(definition, font_def, text_max_w)[:3]:
        draw.text((text_x, cy), line, fill=DEF_COLOR, font=font_def)
        cy += font_def.size + 3

    return img


def render_term_frame(
    overlay: TermOverlay,
    video_size: tuple[int, int],
    config: dict,
) -> np.ndarray:
    vw, vh = video_size
    ox = int(vw * TERM_X_FRAC)
    oy = int(vh * TERM_Y_FRAC)
    ow = int(vw * TERM_W_FRAC)
    oh = int(vh * TERM_H_FRAC)

    styling = config.get("styling", {})
    font_path = find_font(styling.get("font"))
    accent_colors = [tuple(c) for c in styling["accent_colors"]]
    accent_color = accent_colors[0] + (255,)
    bg_color = tuple(styling["panel_bg"])
    bg_radius = styling["panel_radius"]

    term_size = FONT_SIZE_TERM
    if not overlay.definition:
        text_max_w = ow - (PADDING_X + ACCENT_BAR_W + 4) - PADDING_X
        for size in PHRASE_CARD_FONT_SIZES:
            f = ImageFont.truetype(font_path, size)
            if len(_wrap_text(overlay.term, f, text_max_w)) <= PHRASE_CARD_MAX_LINES:
                term_size = size
                break

    font_term = ImageFont.truetype(font_path, term_size)
    font_def  = ImageFont.truetype(font_path, FONT_SIZE_DEF)

    panel = _render_term_panel(
        ow, oh, overlay.term, overlay.definition, (font_term, font_def), font_path,
        bg_color, bg_radius, accent_color, overlay.module_slug,
    )
    frame = Image.new("RGBA", (vw, vh), (0, 0, 0, 0))
    frame.alpha_composite(panel, (ox, oy))
    return np.array(frame)


def make_term_frame_function(
    frame: np.ndarray,
    duration: float,
):
    fade = min(FADE_DURATION, duration / 2)
    empty = np.zeros_like(frame)

    def get_frame(t: float) -> np.ndarray:
        if t < fade:
            alpha = t / fade
        elif t > duration - fade:
            alpha = max(0.0, (duration - t) / fade)
        else:
            alpha = 1.0

        if alpha >= 1.0:
            return frame
        if alpha <= 0.0:
            return empty

        blended = frame.copy()
        blended[:, :, 3] = (frame[:, :, 3] * alpha).astype(np.uint8)
        return blended

    return get_frame
