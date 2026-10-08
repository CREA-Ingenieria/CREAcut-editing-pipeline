"""Stage 8 — Render list overlay frames with Pillow."""

import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .common import ListOverlay, find_font

# ── Panel position in the frame ─────────────────────────────────────────────
OVERLAY_X_FRAC = 0.55
OVERLAY_W_FRAC = 0.40
OVERLAY_Y_FRAC = 0.158   # (1 - 0.684) / 2 — vertical centering
OVERLAY_H_FRAC = 0.684   # 0.76 × 0.9

# ── Panel ────────────────────────────────────────────────────────────────────
ACCENT_BAR_W  = 6

# ── Text ─────────────────────────────────────────────────────────────────────
TITLE_COLOR   = (26,  29,  33)
ITEM_COLOR    = (26,  29,  33)
DESC_COLOR    = (69,  90,  100)
DIVIDER_COLOR = (232, 236, 242)

# ── Item bullets ─────────────────────────────────────────────────────────────
BULLET_RADIUS = 8

# ── Decorative accent-color squares (background cluster) ─────────────────────
ACCENT_SQUARE_ALPHA  = 90
ACCENT_SQUARE_SIZES = [
    (90,  120),
    (120,  90),
    (105,  75),
    ( 83, 113),
    ( 75, 135),
]
ACCENT_SQUARE_RADIUS  = 14
ACCENT_SQUARE_OVERLAP = -8
ACCENT_SQUARE_MARGIN  = 10

# ── Typography ────────────────────────────────────────────────────────────────
FONT_SIZE_TITLE    = 34
FONT_SIZE_ITEM     = 26
FONT_SIZE_DESC     = 19

# ── Layout ────────────────────────────────────────────────────────────────────
PADDING_X    = 28
PADDING_Y    = 26
ITEM_SPACING = 20

# ── Image thumbnails ──────────────────────────────────────────────────────────
IMAGE_MAX_H   = 151
IMAGE_RADIUS  = 10
IMAGE_PAD_TOP = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

_ARTICLE_RE = re.compile(r'^(la|el|los|las|un|una|unos|unas)\s+', re.IGNORECASE)
_PUNCT_RE   = re.compile(r'[^\w\s]')


def _desc_adds_info(label: str, description: str) -> bool:
    """True only when description contains content genuinely distinct from label."""
    if not description:
        return False
    def _norm(s: str) -> str:
        s = _ARTICLE_RE.sub('', s.lower().strip())
        s = _PUNCT_RE.sub('', s)
        return re.sub(r'\s+', ' ', s).strip()
    return _norm(description) != _norm(label)


def _load_and_scale_image(path: str, max_w: int, max_h: int) -> Image.Image | None:
    try:
        img = Image.open(path).convert("RGBA")
        scale = min(max_w / img.width, max_h / img.height, 1.0)
        if scale < 1.0:
            img = img.resize(
                (int(img.width * scale), int(img.height * scale)),
                Image.LANCZOS,
            )
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, img.width, img.height], radius=IMAGE_RADIUS, fill=255,
        )
        img.putalpha(mask)
        return img
    except Exception:
        return None


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


def _measure_item_h(label: str, description: str, font_item, font_desc, text_max_w: int, image_h: int = 0) -> int:
    h = 0
    for _ in _wrap_text(label, font_item, text_max_w):
        h += font_item.size + 4
    if image_h > 0:
        h += image_h + IMAGE_PAD_TOP
    elif _desc_adds_info(label, description):
        for _ in _wrap_text(description, font_desc, text_max_w)[:2]:
            h += font_desc.size + 3
    return h


def _draw_cluster(
    draw: ImageDraw.Draw,
    panel_w: int,
    panel_h: int,
    corner: str,
    square_colors: list[tuple[int, int, int, int]],
) -> None:
    row1 = [(0, ACCENT_SQUARE_SIZES[0]), (1, ACCENT_SQUARE_SIZES[1])]
    row2 = [(2, ACCENT_SQUARE_SIZES[2]), (3, ACCENT_SQUARE_SIZES[3]), (4, ACCENT_SQUARE_SIZES[4])]

    m   = ACCENT_SQUARE_MARGIN
    gap = abs(ACCENT_SQUARE_OVERLAP)

    max_h1 = max(h for _, (w, h) in row1)
    max_h2 = max(h for _, (w, h) in row2)

    if "top" in corner:
        y1 = m
        y2 = y1 + max_h1 - gap
    else:
        y1 = panel_h - m - max_h1
        y2 = y1 - max_h2 + gap

    def place_rtl(row_defs, y):
        x = panel_w - m
        for idx, (w, h) in reversed(row_defs):
            x -= w
            draw.rounded_rectangle(
                [x, y, x + w, y + h],
                radius=ACCENT_SQUARE_RADIUS,
                fill=square_colors[idx],
            )
            x -= gap

    def place_ltr(row_defs, y):
        x = ACCENT_BAR_W + m
        for idx, (w, h) in row_defs:
            draw.rounded_rectangle(
                [x, y, x + w, y + h],
                radius=ACCENT_SQUARE_RADIUS,
                fill=square_colors[idx],
            )
            x += w + gap

    if "right" in corner:
        place_rtl(row1, y1)
        place_rtl(row2, y2)
    else:
        place_ltr(row1, y1)
        place_ltr(row2, y2)


def _render_panel(
    state: int,
    panel_w: int,
    panel_h: int,
    intro: str,
    items,
    fonts: tuple,
    loaded_images: list,
    bg_color: tuple[int, int, int, int],
    bg_radius: int,
    bullet_colors: list[tuple[int, int, int]],
    square_colors: list[tuple[int, int, int, int]],
) -> Image.Image:
    font_title, font_item, font_desc = fonts

    img = Image.new("RGBA", (panel_w, panel_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([0, 0, panel_w, panel_h], radius=bg_radius, fill=bg_color)
    draw.rectangle([0, 0, ACCENT_BAR_W, panel_h], fill=bullet_colors[0] + (255,))

    _draw_cluster(draw, panel_w, panel_h, "top-right", square_colors)

    title_x   = PADDING_X + ACCENT_BAR_W + 4
    title_max_w = panel_w - title_x - PADDING_X
    cy = PADDING_Y

    if intro:
        intro = intro.capitalize()
        for line in _wrap_text(intro, font_title, title_max_w):
            draw.text((title_x, cy), line, fill=TITLE_COLOR, font=font_title)
            cy += font_title.size + 6
        cy += 8
        draw.rectangle(
            [PADDING_X + ACCENT_BAR_W, cy, panel_w - PADDING_X, cy + 1],
            fill=DIVIDER_COLOR,
        )
        cy += 10

    item_x    = PADDING_X + ACCENT_BAR_W + 4
    text_max_w = panel_w - item_x - PADDING_X - BULLET_RADIUS * 2 - 12
    text_x    = item_x + BULLET_RADIUS * 2 + 12

    n = len(items)
    heights = [
        _measure_item_h(it.label, it.description, font_item, font_desc, text_max_w,
                        loaded_images[i].height if loaded_images[i] else 0)
        for i, it in enumerate(items)
    ]
    total_content_h = sum(heights)
    available_h = panel_h - cy - PADDING_Y
    gap = max((available_h - total_content_h) / (n + 1), ITEM_SPACING) if n else 0

    item_y = cy + gap
    for i, item in enumerate(items):
        if i < state:
            bullet_color = bullet_colors[i % len(bullet_colors)] + (255,)
            bullet_cy = item_y + font_item.size // 2
            draw.ellipse(
                [item_x, bullet_cy - BULLET_RADIUS,
                 item_x + BULLET_RADIUS * 2, bullet_cy + BULLET_RADIUS],
                fill=bullet_color,
            )
            iy = item_y
            label = item.label.capitalize()
            for line in _wrap_text(label, font_item, text_max_w):
                draw.text((text_x, iy), line, fill=ITEM_COLOR, font=font_item)
                iy += font_item.size + 4

            if loaded_images[i] is not None:
                thumb = loaded_images[i]
                thumb_x = text_x + (text_max_w - thumb.width) // 2
                img.alpha_composite(thumb, (int(thumb_x), int(iy + IMAGE_PAD_TOP)))
                iy += thumb.height + IMAGE_PAD_TOP
            elif _desc_adds_info(item.label, item.description):
                for line in _wrap_text(item.description, font_desc, text_max_w)[:2]:
                    draw.text((text_x, iy), line, fill=DESC_COLOR, font=font_desc)
                    iy += font_desc.size + 3

        item_y += heights[i] + gap

    return img


# ── Public API ────────────────────────────────────────────────────────────────

def render_overlay_frames(
    overlay: ListOverlay,
    video_size: tuple[int, int],
    config: dict,
) -> tuple[list[np.ndarray], list[float]]:
    vw, vh = video_size
    ox = int(vw * OVERLAY_X_FRAC)
    oy = int(vh * OVERLAY_Y_FRAC)
    ow = int(vw * OVERLAY_W_FRAC)
    oh = int(vh * OVERLAY_H_FRAC)

    styling = config.get("styling", {})
    font_path = find_font(styling.get("font"))
    accent_colors = [tuple(c) for c in styling["accent_colors"]]
    square_colors = [c + (ACCENT_SQUARE_ALPHA,) for c in accent_colors]
    bg_color = tuple(styling["panel_bg"])
    bg_radius = styling["panel_radius"]

    font_title = ImageFont.truetype(font_path, FONT_SIZE_TITLE)
    font_item  = ImageFont.truetype(font_path, FONT_SIZE_ITEM)
    font_desc  = ImageFont.truetype(font_path, FONT_SIZE_DESC)

    fonts = (font_title, font_item, font_desc)
    n = len(overlay.items)
    frames: list[np.ndarray] = []

    text_max_w = ow - (PADDING_X + ACCENT_BAR_W + 4) - PADDING_X - BULLET_RADIUS * 2 - 12
    loaded_images = [
        _load_and_scale_image(it.image_path, text_max_w, IMAGE_MAX_H) if it.image_path else None
        for it in overlay.items
    ]

    for visible in range(n + 1):
        panel = _render_panel(
            visible, ow, oh, overlay.intro, overlay.items, fonts, loaded_images,
            bg_color, bg_radius, accent_colors, square_colors,
        )
        frame = Image.new("RGBA", (vw, vh), (0, 0, 0, 0))
        frame.alpha_composite(panel, (ox, oy))
        frames.append(np.array(frame))

    timestamps = [overlay.cut_start] + overlay.item_timestamps
    return frames, timestamps


def make_frame_function(
    frames: list[np.ndarray],
    timestamps: list[float],
    start_time: float,
):
    def get_frame(t: float) -> np.ndarray:
        absolute_t = start_time + t
        state = 0
        for i, ts in enumerate(timestamps):
            if absolute_t >= ts:
                state = i
        state = min(state, len(frames) - 1)
        return frames[state]

    return get_frame
