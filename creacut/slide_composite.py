"""Render approved raster-slide cues behind a repositioned keyed presenter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .cut import transition_overlap
from .slides import SlidePage, SlideTrackState, resolve_project_path


@dataclass(frozen=True)
class RenderSlideCue:
    page: SlidePage
    image_path: Path
    start_s: float
    end_s: float


def _edit_cues(
    state: SlideTrackState,
    *,
    project_path: str | Path,
    ranges: list[tuple[float, float]],
    config: dict[str, Any],
) -> list[RenderSlideCue]:
    """Map approved source-time cues to the actual crossfaded edit timeline."""
    overlap_request = transition_overlap(config)
    starts: list[float] = []
    current = 0.0
    for index, (range_start, range_end) in enumerate(ranges):
        starts.append(current)
        duration = range_end - range_start
        if index + 1 < len(ranges):
            next_duration = ranges[index + 1][1] - ranges[index + 1][0]
            current += duration - min(overlap_request, duration / 2, next_duration / 2)
    result: list[RenderSlideCue] = []
    for page in state.pages:
        if not page.enabled or page.start_s is None or page.end_s is None:
            continue
        image_path = resolve_project_path(page.image_path, project_path)
        if not image_path.is_file():
            raise FileNotFoundError(f"No se encontró el PNG de la diapositiva {page.id}: {image_path}")
        for index, (range_start, range_end) in enumerate(ranges):
            source_start = max(page.start_s, range_start)
            source_end = min(page.end_s, range_end)
            if source_end <= source_start:
                continue
            result.append(RenderSlideCue(
                page=page,
                image_path=image_path,
                start_s=starts[index] + source_start - range_start,
                end_s=starts[index] + source_end - range_start,
            ))
    return sorted(result, key=lambda cue: (cue.start_s, cue.page.index))


def _alpha_blend(background: np.ndarray, foreground: np.ndarray, x: int, y: int) -> None:
    """Clip the visible intersection without moving or resizing the subject."""
    height, width = foreground.shape[:2]
    if width <= 0 or height <= 0:
        return
    left, top = max(0, x), max(0, y)
    right, bottom = min(background.shape[1], x + width), min(background.shape[0], y + height)
    if right <= left or bottom <= top:
        return
    visible = foreground[top - y:bottom - y, left - x:right - x]
    target = background[top:bottom, left:right]
    alpha = visible[..., 3:4].astype(np.float32) / 255.0
    target[:] = (visible[..., :3].astype(np.float32) * alpha + target.astype(np.float32) * (1.0 - alpha)).astype(np.uint8)


def load_slide_background(image_path: Path, vw: int, vh: int) -> np.ndarray:
    """Load a deck page PNG resized to the output frame -- the shared primitive
    behind both the full render (composite_slides) and the editor's single-
    frame preview, so the two never drift apart."""
    with Image.open(image_path) as source:
        image = np.array(source.convert("RGB"))
    return cv2.resize(image, (vw, vh), interpolation=cv2.INTER_AREA if image.shape[1] >= vw else cv2.INTER_LANCZOS4)


def _fit_speaker(
    page: SlidePage, rgba_frame: np.ndarray, target_w: int, target_h: int
) -> tuple[np.ndarray | None, int, int]:
    """Fit the saved camera crop into the placement box without reframing.

    The crop, scale and offsets depend only on saved geometry and frame
    dimensions, never on the changing alpha silhouette. Natural gestures
    must not cause the presenter layer to zoom or move inside its box.

    Returns ``(fitted_rgba, offset_x, offset_y)`` where the offsets are
    relative to the box's own top-left corner -- or ``(None, 0, 0)`` if
    nothing usable was found. Shared by ``_place_speaker`` (bakes it onto a
    frame at the box's placed position) and ``render_presenter_cutout`` (puts
    it in its own transparent canvas for the editor's drag preview).
    """
    source_h, source_w = rgba_frame.shape[:2]
    left = max(0, min(source_w - 1, round(page.crop_x * source_w)))
    top = max(0, min(source_h - 1, round(page.crop_y * source_h)))
    right = max(left + 1, min(source_w, round((page.crop_x + page.crop_width) * source_w)))
    bottom = max(top + 1, min(source_h, round((page.crop_y + page.crop_height) * source_h)))
    crop = rgba_frame[top:bottom, left:right]

    # Preserve transparent margins: removing them per frame changes the
    # scale/anchor whenever a hand moves or the chroma mask changes.
    crop_h, crop_w = crop.shape[:2]
    if crop_w <= 0 or crop_h <= 0:
        return None, 0, 0

    # Fit the fixed crop with one uniform scale, preserving its aspect ratio.
    scale = min(target_w / crop_w, target_h / crop_h)
    fitted_w = max(1, round(crop_w * scale))
    fitted_h = max(1, round(crop_h * scale))
    speaker = cv2.resize(crop, (fitted_w, fitted_h), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LANCZOS4)
    offset_x = max(0, (target_w - fitted_w) // 2)
    offset_y = max(0, target_h - fitted_h)  # anchored to the bottom of the box
    return speaker, offset_x, offset_y


def _place_speaker(canvas: np.ndarray, page: SlidePage, rgba_frame: np.ndarray, vw: int, vh: int) -> None:
    """Fit the keyed presenter into ``page``'s placement box and alpha-blend
    it onto ``canvas`` at that box's position."""
    target_w = max(2, min(vw, round(page.speaker_width * vw)))
    target_h = max(2, min(vh, round(page.height_fraction * vh)))
    speaker, offset_x, offset_y = _fit_speaker(page, rgba_frame, target_w, target_h)
    if speaker is None:
        return
    box_x = page.x * vw
    box_y = page.y * vh
    x = round(box_x + offset_x)
    y = round(box_y + offset_y)
    _alpha_blend(canvas, speaker, x, y)


def render_presenter_cutout(page: SlidePage, rgba_frame: np.ndarray, video_size: tuple[int, int]) -> np.ndarray:
    """Return a transparent RGBA canvas, sized to ``page``'s nominal
    placement box, with the fitted presenter composited inside it.

    Used by the editor's drag-to-reposition preview: unlike the baked frame
    ``composite_slides`` produces at render time, this depends only on the
    crop/fit fields (not on ``page.x``/``page.y``), so the frontend can move
    the presenter live with the cursor by repositioning this one image via
    CSS, without asking Python to recomposite on every pointer move.
    """
    vw, vh = int(video_size[0]), int(video_size[1])
    target_w = max(2, min(vw, round(page.speaker_width * vw)))
    target_h = max(2, min(vh, round(page.height_fraction * vh)))
    canvas = np.zeros((target_h, target_w, 4), dtype=np.uint8)
    speaker, offset_x, offset_y = _fit_speaker(page, rgba_frame, target_w, target_h)
    if speaker is not None:
        canvas[offset_y:offset_y + speaker.shape[0], offset_x:offset_x + speaker.shape[1]] = speaker
    return canvas


def composite_slides(
    clip,
    *,
    state: SlideTrackState,
    project_path: str | Path,
    ranges: list[tuple[float, float]],
    video_size: tuple[int, int],
    config: dict[str, Any],
    get_rgba_frame,
    verbose: bool = False,
):
    """Place the keyed presenter over accepted slides.

    Only consecutive slide backgrounds dissolve. A slide active at the
    beginning is shown in full on frame zero, without the pipeline frame.

    The output is entirely raster based: each imported deck page is already a
    PNG, and the speaker comes from CREAcut's alpha key rather than a second
    video layer.  Audio is copied untouched from ``clip``.
    """
    if get_rgba_frame is None:
        raise ValueError("Las diapositivas requieren chroma habilitado para recortar al presentador")
    cues = _edit_cues(state, project_path=project_path, ranges=ranges, config=config)
    if not cues:
        return clip
    from moviepy import VideoClip

    vw, vh = (int(video_size[0]), int(video_size[1]))
    image_cache: dict[Path, np.ndarray] = {}
    transition_s = 0.32

    def slide_image(cue: RenderSlideCue) -> np.ndarray:
        cached = image_cache.get(cue.image_path)
        if cached is not None:
            return cached
        rendered = load_slide_background(cue.image_path, vw, vh)
        image_cache[cue.image_path] = rendered
        return rendered

    def draw_speaker(canvas: np.ndarray, page: SlidePage, time_s: float) -> None:
        _place_speaker(canvas, page, get_rgba_frame(time_s), vw, vh)

    def frame_at(time_s: float) -> np.ndarray:
        active_index = next((index for index in range(len(cues) - 1, -1, -1) if cues[index].start_s <= time_s < cues[index].end_s), None)
        if active_index is None:
            return clip.get_frame(time_s)
        cue = cues[active_index]
        canvas = slide_image(cue).copy()
        previous = cues[active_index - 1] if active_index else None
        if (
            previous is not None
            and previous.page.id != cue.page.id
            and previous.end_s >= cue.start_s
            and cue.start_s > 0.0
            and time_s - cue.start_s < transition_s
        ):
            progress = max(0.0, min(1.0, (time_s - cue.start_s) / transition_s))
            canvas = (slide_image(previous).astype(np.float32) * (1.0 - progress) + canvas.astype(np.float32) * progress).astype(np.uint8)
        # Never blend clip.get_frame here: it already contains the presenter
        # at the pipeline position, producing a second, displaced silhouette.
        draw_speaker(canvas, cue.page, time_s)
        return canvas

    if verbose:
        print(f"  Diapositivas aprobadas: {len(cues)} ventana(s), transición {transition_s:.2f}s")
    result = VideoClip(frame_function=frame_at, duration=clip.duration).with_fps(clip.fps)
    return result.with_audio(clip.audio) if clip.audio is not None else result
