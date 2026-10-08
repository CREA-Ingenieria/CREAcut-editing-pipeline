"""Stage 8e — Render equation overlay frames with matplotlib + Pillow."""

import json
import re
from io import BytesIO
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .common import CutSentence, EquationOverlay, EquationStep, find_font

# ── Panel position in the frame ─────────────────────────────────────────────
EQ_X_FRAC = 0.55
EQ_W_FRAC = 0.40
EQ_Y_FRAC = 0.30
EQ_H_FRAC = 0.40

# ── Panel styling (shares identity with render_list.py) ──────────────────────
ACCENT_BAR_W  = 6

# ── Text ─────────────────────────────────────────────────────────────────────
TITLE_COLOR   = (26, 29, 33)
DIVIDER_COLOR = (232, 236, 242)

# ── Decorative accent-color squares ──────────────────────────────────────────
ACCENT_SQUARE_ALPHA  = 90
ACCENT_SQUARE_SIZES = [
    (90, 120), (120, 90), (105, 75), (83, 113), (75, 135),
]
ACCENT_SQUARE_RADIUS  = 14
ACCENT_SQUARE_OVERLAP = -8
ACCENT_SQUARE_MARGIN  = 10

# ── Typography ───────────────────────────────────────────────────────────────
FONT_SIZE_TITLE    = 30

# ── Layout ───────────────────────────────────────────────────────────────────
PADDING_X = 28
PADDING_Y = 26

# ── LaTeX rendering ──────────────────────────────────────────────────────────
LATEX_FONTSIZE = 48
LATEX_DPI      = 150
LATEX_COLOR    = "#1A1D21"

# ── Keyword matching ─────────────────────────────────────────────────────────
KEYWORD_OFFSET_S = -0.2


# ── LaTeX → PIL Image ────────────────────────────────────────────────────────

def render_latex_to_image(
    latex_str: str,
    fontsize: int = LATEX_FONTSIZE,
    dpi: int = LATEX_DPI,
    color: str = LATEX_COLOR,
) -> Image.Image:
    fig = plt.figure(figsize=(0.01, 0.01), dpi=dpi)
    fig.patch.set_alpha(0.0)
    fig.text(
        0.5, 0.5, f"${latex_str}$",
        fontsize=fontsize, color=color, ha="center", va="center",
    )
    buf = BytesIO()
    fig.savefig(
        buf, format="png", dpi=dpi, transparent=True,
        bbox_inches="tight", pad_inches=0.05,
    )
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


# ── Accent-color cluster (same logic as render_list.py) ──────────────────────

def _draw_cluster(
    draw: ImageDraw.Draw,
    panel_w: int,
    panel_h: int,
    corner: str,
    square_colors: list[tuple[int, int, int, int]],
) -> None:
    row1 = [(0, ACCENT_SQUARE_SIZES[0]), (1, ACCENT_SQUARE_SIZES[1])]
    row2 = [(2, ACCENT_SQUARE_SIZES[2]), (3, ACCENT_SQUARE_SIZES[3]), (4, ACCENT_SQUARE_SIZES[4])]
    m = ACCENT_SQUARE_MARGIN
    gap = abs(ACCENT_SQUARE_OVERLAP)
    max_h1 = max(h for _, (_, h) in row1)
    max_h2 = max(h for _, (_, h) in row2)

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
                radius=ACCENT_SQUARE_RADIUS, fill=square_colors[idx],
            )
            x -= gap

    def place_ltr(row_defs, y):
        x = ACCENT_BAR_W + m
        for idx, (w, h) in row_defs:
            draw.rounded_rectangle(
                [x, y, x + w, y + h],
                radius=ACCENT_SQUARE_RADIUS, fill=square_colors[idx],
            )
            x += w + gap

    if "right" in corner:
        place_rtl(row1, y1)
        place_rtl(row2, y2)
    else:
        place_ltr(row1, y1)
        place_ltr(row2, y2)


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
    return lines or [text]


# ── Panel rendering ──────────────────────────────────────────────────────────

def _render_equation_panel(
    step_idx: int,
    panel_w: int,
    panel_h: int,
    title: str,
    latex_images: list[Image.Image],
    font_title,
    bg_color: tuple[int, int, int, int],
    bg_radius: int,
    accent_color: tuple[int, int, int, int],
    square_colors: list[tuple[int, int, int, int]],
) -> Image.Image:
    img = Image.new("RGBA", (panel_w, panel_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([0, 0, panel_w, panel_h], radius=bg_radius, fill=bg_color)
    draw.rectangle([0, 0, ACCENT_BAR_W, panel_h], fill=accent_color)
    _draw_cluster(draw, panel_w, panel_h, "top-right", square_colors)

    title_x = PADDING_X + ACCENT_BAR_W + 4
    title_max_w = panel_w - title_x - PADDING_X
    cy = PADDING_Y

    for line in _wrap_text(title, font_title, title_max_w):
        draw.text((title_x, cy), line, fill=TITLE_COLOR, font=font_title)
        cy += font_title.size + 6
    cy += 8

    draw.rectangle(
        [PADDING_X + ACCENT_BAR_W, cy, panel_w - PADDING_X, cy + 1],
        fill=DIVIDER_COLOR,
    )
    cy += 10

    if 0 <= step_idx < len(latex_images):
        eq_img = latex_images[step_idx]
        content_x = PADDING_X + ACCENT_BAR_W
        available_w = panel_w - content_x - PADDING_X
        available_h = panel_h - cy - PADDING_Y

        scale = min(available_w / eq_img.width, available_h / eq_img.height, 1.0)
        if scale < 1.0:
            eq_img = eq_img.resize(
                (int(eq_img.width * scale), int(eq_img.height * scale)),
                Image.LANCZOS,
            )

        eq_x = content_x + (available_w - eq_img.width) // 2
        eq_y = cy + (available_h - eq_img.height) // 2
        img.alpha_composite(eq_img, (eq_x, eq_y))

    return img


# ── Public API ───────────────────────────────────────────────────────────────

def render_equation_frames(
    overlay: EquationOverlay,
    video_size: tuple[int, int],
    config: dict,
) -> tuple[list[np.ndarray], list[float]]:
    vw, vh = video_size
    ox = int(vw * EQ_X_FRAC)
    oy = int(vh * EQ_Y_FRAC)
    ow = int(vw * EQ_W_FRAC)
    oh = int(vh * EQ_H_FRAC)

    styling = config.get("styling", {})
    font_path = find_font(styling.get("font"))
    accent_colors = [tuple(c) for c in styling["accent_colors"]]
    square_colors = [c + (ACCENT_SQUARE_ALPHA,) for c in accent_colors]
    accent_color = accent_colors[0] + (255,)
    bg_color = tuple(styling["panel_bg"])
    bg_radius = styling["panel_radius"]

    font_title = ImageFont.truetype(font_path, FONT_SIZE_TITLE)

    latex_images = [render_latex_to_image(step.latex) for step in overlay.steps]

    frames: list[np.ndarray] = []
    for step_idx in range(len(overlay.steps)):
        panel = _render_equation_panel(
            step_idx, ow, oh, overlay.title, latex_images, font_title,
            bg_color, bg_radius, accent_color, square_colors,
        )
        frame = Image.new("RGBA", (vw, vh), (0, 0, 0, 0))
        frame.alpha_composite(panel, (ox, oy))
        frames.append(np.array(frame))

    return frames, overlay.step_timestamps


def make_equation_frame_function(
    frames: list[np.ndarray],
    timestamps: list[float],
    start_time: float,
):
    def get_frame(t: float) -> np.ndarray:
        absolute_t = start_time + t
        current_step = 0
        for i, ts in enumerate(timestamps):
            if absolute_t >= ts:
                current_step = i
        return frames[min(current_step, len(frames) - 1)]

    return get_frame


# ── Keyword resolution ───────────────────────────────────────────────────────

def resolve_equation_keywords(
    whisper_segments: list[dict],
    raw_start: float,
    raw_end: float,
    steps: list[EquationStep],
    offset_s: float = KEYWORD_OFFSET_S,
) -> list[float]:
    words_in_range = []
    for seg in whisper_segments:
        for w in seg.get("words", []):
            if raw_start <= w["start"] <= raw_end:
                words_in_range.append(w)

    consumed: set[int] = set()
    step_timestamps: list[float] = []

    for step in steps:
        keyword = step.keyword.lower()
        found_ts = None
        for i, w in enumerate(words_in_range):
            if i in consumed:
                continue
            word_text = re.sub(r"[^\w]", "", w["word"].lower().strip())
            if keyword in word_text:
                found_ts = max(0.0, w["start"] + offset_s)
                consumed.add(i)
                break

        if found_ts is not None:
            step_timestamps.append(found_ts)
        else:
            prev_ts = step_timestamps[-1] if step_timestamps else raw_start
            remaining = len(steps) - len(step_timestamps)
            gap = (raw_end - prev_ts) / (remaining + 1)
            step_timestamps.append(prev_ts + gap)

    return step_timestamps


# ── Overlay builder ──────────────────────────────────────────────────────────

def build_equation_overlays(
    spec_path: str | Path,
    whisper_segments: list[dict],
    cut_sentences: list[CutSentence],
    verbose: bool = False,
) -> list[EquationOverlay]:
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)

    offset_s = spec.get("keyword_offset_s", KEYWORD_OFFSET_S)
    overlays: list[EquationOverlay] = []

    for eq in spec["equations"]:
        para_idx = eq["paragraph_idx"]
        para_sents = [cs for cs in cut_sentences if cs.paragraph_idx == para_idx]
        if not para_sents:
            if verbose:
                print(f"    {eq['id']}: no cut_sentences for paragraph {para_idx}, skipping")
            continue

        cut_start = min(cs.cut_start for cs in para_sents)
        cut_end = max(cs.cut_end for cs in para_sents)
        raw_start = min(cs.raw_start for cs in para_sents)
        raw_end = max(cs.raw_end for cs in para_sents)

        steps = [EquationStep(latex=s["latex"], keyword=s["keyword"])
                 for s in eq["steps"]]

        raw_timestamps = resolve_equation_keywords(
            whisper_segments, raw_start, raw_end, steps, offset_s,
        )

        step_timestamps: list[float] = []
        for raw_ts in raw_timestamps:
            best_cut_ts = cut_start
            for cs in para_sents:
                if cs.raw_start <= raw_ts <= cs.raw_end and cs.raw_end > cs.raw_start:
                    frac = (raw_ts - cs.raw_start) / (cs.raw_end - cs.raw_start)
                    best_cut_ts = cs.cut_start + frac * (cs.cut_end - cs.cut_start)
                    break
            step_timestamps.append(best_cut_ts)

        overlay = EquationOverlay(
            id=eq["id"],
            title=eq["title"],
            steps=steps,
            paragraph_idx=para_idx,
            cut_start=cut_start,
            cut_end=cut_end,
            step_timestamps=step_timestamps,
        )
        overlays.append(overlay)

        if verbose:
            print(f"    {eq['id']}: {cut_start:.1f}s–{cut_end:.1f}s, "
                  f"{len(steps)} steps, timestamps={[f'{t:.1f}' for t in step_timestamps]}")

    return overlays
