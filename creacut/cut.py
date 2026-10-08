"""Stage 4 — Video cutting and export."""

from pathlib import Path

import numpy as np

from .chroma import make_alpha_extractor, make_chroma_replacer
from .effects import apply_effect_ranges_to_clip


TRANSITION_TYPES = {"cut", "dissolve", "fade_black", "wipe_left", "slide_left"}


def transition_overlap(config: dict) -> float:
    """Return the timeline overlap used by the selected transition."""
    transition = config.get("transitions", {})
    kind = str(transition.get("type", "dissolve"))
    if kind not in TRANSITION_TYPES:
        raise ValueError(f"Tipo de transición no compatible: {kind}")
    if kind == "cut":
        return 0.0
    duration = float(transition.get("crossfade", 0.2))
    if not 0.0 <= duration <= 0.5:
        raise ValueError("transitions.crossfade debe estar entre 0 y 0.5")
    return duration


def _blend_transition(outgoing: np.ndarray, incoming: np.ndarray, progress: float, kind: str) -> np.ndarray:
    p = min(1.0, max(0.0, float(progress)))
    if kind == "dissolve":
        return np.clip(outgoing.astype(np.float32) * (1.0 - p) + incoming.astype(np.float32) * p, 0, 255).astype(np.uint8)
    if kind == "fade_black":
        if p < 0.5:
            return np.clip(outgoing.astype(np.float32) * (1.0 - p * 2.0), 0, 255).astype(np.uint8)
        return np.clip(incoming.astype(np.float32) * ((p - 0.5) * 2.0), 0, 255).astype(np.uint8)
    if kind == "wipe_left":
        boundary = min(outgoing.shape[1], max(0, round(outgoing.shape[1] * p)))
        result = outgoing.copy()
        if boundary:
            result[:, :boundary] = incoming[:, :boundary]
        return result
    if kind == "slide_left":
        width = outgoing.shape[1]
        offset = min(width, max(0, round(width * p)))
        if offset <= 0:
            return outgoing
        if offset >= width:
            return incoming
        result = np.empty_like(outgoing)
        result[:, : width - offset] = outgoing[:, offset:]
        result[:, width - offset :] = incoming[:, :offset]
        return result
    return incoming if p >= 1.0 else outgoing


def _assemble_video(clips: list, kind: str, requested_overlap: float):
    """Join video-only clips and return (clip, starts, boundary overlaps)."""
    from moviepy import VideoClip, concatenate_videoclips

    if len(clips) == 1:
        return clips[0], [0.0], []
    if kind == "cut" or requested_overlap <= 0:
        starts: list[float] = []
        current = 0.0
        for clip in clips:
            starts.append(current)
            current += float(clip.duration)
        return concatenate_videoclips(clips, method="chain"), starts, [0.0] * (len(clips) - 1)

    overlaps = [
        min(requested_overlap, float(clips[index].duration) / 2, float(clips[index + 1].duration) / 2)
        for index in range(len(clips) - 1)
    ]
    starts = [0.0]
    for index in range(1, len(clips)):
        starts.append(starts[-1] + float(clips[index - 1].duration) - overlaps[index - 1])
    total_duration = starts[-1] + float(clips[-1].duration)

    def frame_at(clip, time_s: float):
        return clip.get_frame(min(max(0.0, time_s), max(0.0, float(clip.duration) - 1e-6)))

    def make_frame(time_s: float):
        current_index = 0
        for index, start in enumerate(starts):
            if start <= time_s:
                current_index = index
            else:
                break
        if current_index > 0:
            overlap = overlaps[current_index - 1]
            transition_start = starts[current_index]
            if overlap > 0 and time_s < transition_start + overlap:
                outgoing_index = current_index - 1
                outgoing = frame_at(clips[outgoing_index], time_s - starts[outgoing_index])
                incoming = frame_at(clips[current_index], time_s - transition_start)
                return _blend_transition(
                    outgoing,
                    incoming,
                    (time_s - transition_start) / overlap,
                    kind,
                )
        return frame_at(clips[current_index], time_s - starts[current_index])

    result = VideoClip(frame_function=make_frame, duration=total_duration)
    fps = getattr(clips[0], "fps", None)
    if fps:
        result = result.with_fps(fps)
    return result, starts, overlaps


def build_cut_clip(
    video_path: Path,
    clean_ranges: list[tuple[float, float]],
    config: dict,
    with_speaker_mask: bool = False,
    verbose: bool = False,
):
    """Build the cut + chroma-keyed clip.

    Reads chroma, skin correction, background, and crossfade parameters from
    config. Returns (clip, video_size, video_obj, get_rgba_frame).
    get_rgba_frame is a callable (t: float) -> np.ndarray RGBA when with_speaker_mask=True,
    otherwise None. Used by overlay.py for the animated speaker slide.
    """
    from moviepy import CompositeAudioClip, VideoFileClip
    from moviepy.audio.fx import AudioFadeIn, AudioFadeOut

    chroma_cfg = config["chroma"]
    chroma_enabled = chroma_cfg.get("enabled", True)
    bg_image = config["background"]["image"]
    transition_kind = str(config.get("transitions", {}).get("type", "dissolve"))
    video_xfade_dur = transition_overlap(config)
    skin_enabled = config.get("skin_correction", {}).get("enabled", False)

    if verbose:
        print(f"  Loading {video_path.name}...")
    video = VideoFileClip(str(video_path))

    raw_clips = []
    for i, (s, e) in enumerate(clean_ranges):
        clip = video.subclipped(s, e)
        if verbose:
            print(f"    Clip {i + 1}: {s:.1f}s – {e:.1f}s ({e - s:.1f}s)")
        raw_clips.append(clip)

    if not raw_clips:
        raise RuntimeError("No clean segments — nothing to export.")

    # ── Video timeline: chroma per-clip, then CrossFadeIn on incoming clips ───
    # Audio is stripped here and rebuilt separately so J-cut can offset it
    # independently from the video crossfade window.
    #
    # Chroma is applied to each clip individually BEFORE the dissolve so that
    # blended frames never mix green-screen pixels with subject pixels — this
    # eliminates the green-edge artefact visible at transition boundaries when
    # the speaker's position differs between takes.
    video_only = [c.without_audio() for c in raw_clips]

    # Build chroma replacer early so it can be applied per-clip.
    replacer = None
    if chroma_enabled:
        label = "custom background" if bg_image else "default background"
        if verbose:
            print(f"  Replacing green screen → {label}...")
        replacer = make_chroma_replacer(config)

    display_clips = [c.image_transform(replacer) for c in video_only] if chroma_enabled else video_only
    display_clips = [
        apply_effect_ranges_to_clip(clip, clean_ranges[index][0], config)
        for index, clip in enumerate(display_clips)
    ]

    raw_video_for_mask, clip_t_starts, boundary_overlaps = _assemble_video(
        video_only, transition_kind, video_xfade_dur
    )
    keyed_video, _display_starts, _display_overlaps = _assemble_video(
        display_clips, transition_kind, video_xfade_dur
    )

    # ── Audio timeline ──────────────────────────────────────────────────────────
    # Audio crossfade matches the video crossfade window (transitions.crossfade).
    #
    # Start positions of each clip's VIDEO in the final timeline (xfade-compressed):
    if verbose:
        print(f"  Transition: {transition_kind} ({video_xfade_dur:.2f}s)")
        for i, clip in enumerate(raw_clips):
            xf_info = ""
            if i < len(raw_clips) - 1:
                xf_eff = boundary_overlaps[i]
                if xf_eff < video_xfade_dur:
                    xf_info = f" (xfade reduced: {xf_eff:.3f}s)"
            print(f"    Clip {i}: dur={clip.duration:.2f}s start={clip_t_starts[i]:.3f}s{xf_info}")

    audio_pieces = []
    for i, clip in enumerate(raw_clips):
        if clip.audio is None:
            continue
        audio = clip.audio
        is_first = (i == 0)
        is_last = (i == len(raw_clips) - 1)

        if not is_first:
            fd = min(boundary_overlaps[i - 1], audio.duration / 2)
            if fd > 0:
                audio = audio.with_effects([AudioFadeIn(fd)])
        if not is_last:
            fd = min(boundary_overlaps[i], audio.duration / 2)
            if fd > 0:
                audio = audio.with_effects([AudioFadeOut(fd)])

        audio_start = clip_t_starts[i] if not is_first else 0.0
        audio_pieces.append(audio.with_start(audio_start))

    if audio_pieces:
        composite_audio = CompositeAudioClip(audio_pieces).with_duration(keyed_video.duration)
        final = keyed_video.with_audio(composite_audio)
    else:
        final = keyed_video

    # ── Speaker mask ──────────────────────────────────────────────────────────
    # raw_video_for_mask is the green-screen composite (no chroma applied) used
    # solely so make_alpha_extractor can find pure green pixels at time t.
    get_rgba_frame = None
    if chroma_enabled and with_speaker_mask:
        extractor = make_alpha_extractor(config)
        _raw_for_mask = raw_video_for_mask
        def get_rgba_frame(t: float):  # noqa: E306
            return extractor(_raw_for_mask.get_frame(t))

    # ── Skin correction ───────────────────────────────────────────────────────
    if skin_enabled:
        from .skin import make_skin_corrector
        if verbose:
            print("  Applying skin color correction...")
        corrector = make_skin_corrector(config)
        final = final.image_transform(corrector)

        if get_rgba_frame is not None:
            _orig_get_rgba = get_rgba_frame
            _skin_fn = corrector
            def get_rgba_frame(t: float):
                rgba = _orig_get_rgba(t).copy()
                rgba[:, :, :3] = _skin_fn(rgba[:, :, :3])
                return rgba

    video_size = (final.w, final.h)
    return final, video_size, video, get_rgba_frame


def export_clip(
    clip,
    output_path: Path,
    verbose: bool = False,
) -> float:
    if verbose:
        print(f"  Writing {output_path.name}...")

    clip.write_videofile(
        str(output_path),
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        threads=0,
    )
    return clip.duration
