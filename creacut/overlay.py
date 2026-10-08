"""Stage 8b — Composite list and term overlays onto the final video with animated speaker slide."""

import numpy as np
from PIL import Image

from .common import EquationOverlay, ListOverlay, TermOverlay
from .render_list import OVERLAY_X_FRAC, make_frame_function, render_overlay_frames
from .render_term import make_term_frame_function, render_term_frame

SLIDE_DURATION = 0.4   # seconds for slide-in and slide-out transitions
SLIDE_OFFSET_X = 480   # pixels to shift speaker left (no scaling, translation only)


def _load_bg(bg_image_path: str | None, vw: int, vh: int) -> np.ndarray:
    """Load background image resized to video dimensions, RGB uint8."""
    try:
        img = Image.open(bg_image_path).convert("RGB").resize((vw, vh), Image.LANCZOS)
        return np.array(img)
    except Exception:
        return np.full((vh, vw, 3), 255, dtype=np.uint8)


def _alpha_blend(dst: np.ndarray, src_rgba: np.ndarray,
                 dst_x: int, src_x: int, width: int):
    """Alpha-blend src_rgba[:, src_x:src_x+width] onto dst[:, dst_x:dst_x+width] in-place."""
    s = src_rgba[:, src_x:src_x + width, :]
    alpha = s[:, :, 3:4].astype(np.float32) * (1.0 / 255.0)
    dst_slice = dst[:, dst_x:dst_x + width, :]
    dst[:, dst_x:dst_x + width, :] = (
        s[:, :, :3].astype(np.float32) * alpha
        + dst_slice.astype(np.float32) * (1.0 - alpha)
    ).astype(np.uint8)


def _make_slide_frame_fn(
    get_rgba_frame,
    bg_arr: np.ndarray,
    overlay_frame_fn,
    vw: int,
    vh: int,
    cut_start: float,
    duration: float,
    slide_dur: float,
    slide_offset_x: int,
):
    """Return get_frame(t) for the combined speaker+overlay VideoClip.

    At t=0:          speaker centered, overlay off-screen right.
    At t=slide_dur:  speaker shifted left by slide_offset_x, overlay at natural position.
    At t=duration-slide_dur to t=duration: both reverse back.

    The clip returns RGB (H, W, 3) — fully opaque, covers the base clip.
    """
    panel_ox = int(vw * OVERLAY_X_FRAC)
    overlay_slide_amount = vw - panel_ox

    effective_slide = min(slide_dur, duration / 2)

    def _smoothstep(p: float) -> float:
        return p * p * p * (p * (6.0 * p - 15.0) + 10.0)

    def _interp(t_rel: float) -> float:
        if t_rel < effective_slide:
            return _smoothstep(t_rel / effective_slide)
        elif t_rel < duration - effective_slide:
            return 1.0
        else:
            remaining = duration - t_rel
            return _smoothstep(max(remaining, 0.0) / effective_slide)

    def get_frame(t: float) -> np.ndarray:
        p = _interp(t)
        result = bg_arr.copy()

        # Speaker: RGBA shifted left by slide_offset_x * p pixels
        spk_rgba = get_rgba_frame(cut_start + t)
        shift = int(slide_offset_x * p)
        vis_w = vw - shift
        if vis_w > 0:
            _alpha_blend(result, spk_rgba, dst_x=0, src_x=shift, width=vis_w)

        # Overlay panel: shifted right by (1-p) * overlay_slide_amount
        if overlay_frame_fn is not None:
            ov_arr = overlay_frame_fn(t)
            shift_x = int((1.0 - p) * overlay_slide_amount)
            vis_w_ov = vw - shift_x
            if vis_w_ov > 0:
                _alpha_blend(result, ov_arr, dst_x=shift_x, src_x=0, width=vis_w_ov)

        return result

    return get_frame


def composite_overlays(
    clip,
    overlays: list[ListOverlay],
    video_size: tuple[int, int],
    config: dict,
    get_rgba_frame=None,
    verbose: bool = False,
):
    if not overlays:
        return clip

    from moviepy import CompositeVideoClip, VideoClip

    vw, vh = video_size
    bg_image_path = config.get("background", {}).get("image")
    bg_arr = _load_bg(bg_image_path, vw, vh) if get_rgba_frame is not None else None

    overlay_windows = []
    overlay_clips = []

    for i, ov in enumerate(overlays):
        frames, timestamps = render_overlay_frames(ov, video_size, config)
        duration = ov.cut_end - ov.cut_start
        if duration <= 0 or not frames:
            continue

        frame_fn = make_frame_function(frames, timestamps, ov.cut_start)

        if get_rgba_frame is not None:
            slide_fn = _make_slide_frame_fn(
                get_rgba_frame, bg_arr, frame_fn, vw, vh,
                ov.cut_start, duration, SLIDE_DURATION, SLIDE_OFFSET_X,
            )
            overlay_windows.append((ov.cut_start, ov.cut_end, slide_fn))
        else:
            ov_clip = (
                VideoClip(frame_fn, duration=duration)
                .with_start(ov.cut_start)
                .with_position((0, 0))
            )
            overlay_clips.append(ov_clip)

        if verbose:
            slide_note = " + slide" if get_rgba_frame is not None else ""
            print(f"    Overlay {i + 1}: {ov.cut_start:.1f}s–{ov.cut_end:.1f}s "
                  f"({len(ov.items)} items{slide_note})")

    # Slide path: dispatch between overlay windows and the main clip directly,
    # bypassing CompositeVideoClip to avoid rendering the main clip during overlay
    # windows (where its output would be fully overwritten and discarded).
    if get_rgba_frame is not None and overlay_windows:
        def dispatch_frame(t):
            for start, end, slide_fn in overlay_windows:
                if start <= t < end:
                    return slide_fn(t - start)
            return clip.get_frame(t)

        final = VideoClip(dispatch_frame, duration=clip.duration)
        final = final.with_fps(clip.fps)
        if clip.audio is not None:
            final = final.with_audio(clip.audio)
        return final

    if not overlay_clips:
        return clip

    final = CompositeVideoClip(
        [clip] + overlay_clips,
        size=video_size,
        use_bgclip=True,
    )
    final = final.with_duration(clip.duration)
    if clip.audio is not None:
        final = final.with_audio(clip.audio)
    return final


def composite_equations(
    clip,
    eq_overlays: list[EquationOverlay],
    video_size: tuple[int, int],
    config: dict,
    get_rgba_frame=None,
    verbose: bool = False,
):
    if not eq_overlays:
        return clip

    from moviepy import VideoClip
    from .render_equation import make_equation_frame_function, render_equation_frames

    vw, vh = video_size
    bg_image_path = config.get("background", {}).get("image")
    bg_arr = _load_bg(bg_image_path, vw, vh) if get_rgba_frame is not None else None

    overlay_windows = []

    for i, eq_ov in enumerate(eq_overlays):
        frames, timestamps = render_equation_frames(eq_ov, video_size, config)
        duration = eq_ov.cut_end - eq_ov.cut_start
        if duration <= 0 or not frames:
            continue

        frame_fn = make_equation_frame_function(frames, timestamps, eq_ov.cut_start)

        if get_rgba_frame is not None:
            slide_fn = _make_slide_frame_fn(
                get_rgba_frame, bg_arr, frame_fn, vw, vh,
                eq_ov.cut_start, duration, SLIDE_DURATION, SLIDE_OFFSET_X,
            )
            overlay_windows.append((eq_ov.cut_start, eq_ov.cut_end, slide_fn))

        if verbose:
            print(f"    Equation {i + 1} ({eq_ov.id}): {eq_ov.cut_start:.1f}s–{eq_ov.cut_end:.1f}s "
                  f"({len(eq_ov.steps)} steps)")

    if get_rgba_frame is not None and overlay_windows:
        def dispatch_frame(t):
            for start, end, slide_fn in overlay_windows:
                if start <= t < end:
                    return slide_fn(t - start)
            return clip.get_frame(t)

        final = VideoClip(dispatch_frame, duration=clip.duration)
        final = final.with_fps(clip.fps)
        if clip.audio is not None:
            final = final.with_audio(clip.audio)
        return final

    return clip


def composite_terms(
    clip,
    term_overlays: list[TermOverlay],
    video_size: tuple[int, int],
    config: dict,
    verbose: bool = False,
):
    if not term_overlays:
        return clip

    from moviepy import CompositeVideoClip, VideoClip

    term_clips = []
    for i, tov in enumerate(term_overlays):
        duration = tov.cut_end - tov.cut_start
        if duration <= 0:
            continue

        frame = render_term_frame(tov, video_size, config)
        frame_fn = make_term_frame_function(frame, duration)

        term_clip = (
            VideoClip(frame_fn, duration=duration)
            .with_start(tov.cut_start)
            .with_position((0, 0))
        )
        term_clips.append(term_clip)

        if verbose:
            print(f"    Term {i + 1}: \"{tov.term}\" at {tov.cut_start:.1f}s–{tov.cut_end:.1f}s")

    if not term_clips:
        return clip

    final = CompositeVideoClip(
        [clip] + term_clips,
        size=video_size,
        use_bgclip=True,
    )
    final = final.with_duration(clip.duration)
    if clip.audio is not None:
        final = final.with_audio(clip.audio)
    return final
