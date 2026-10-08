"""Stage 10 — Wrap edited video with intro/outro bookends."""

from pathlib import Path


def wrap_with_bookends(
    clip,
    config: dict,
    verbose: bool = False,
):
    """Prepend intro video and append closing image card to the edited clip.

    Bookend paths are read from config["bookends"]: intro_video, closing_image,
    closing_duration. Either asset may be None (or missing on disk), in which
    case that bookend is skipped. If neither is available, the clip is
    returned unchanged.

    Returns (bookended_clip, intro_video) — intro_video is the loaded intro
    VideoFileClip (or None if no intro was added). Caller must call
    intro_video.close() after export to release the file handle.
    """
    bookend_cfg = config.get("bookends", {})
    intro_path = bookend_cfg.get("intro_video")
    closing_path = bookend_cfg.get("closing_image")
    closing_duration = bookend_cfg.get("closing_duration", 5.0)

    from moviepy import ImageClip, VideoFileClip, concatenate_videoclips

    target_w, target_h = clip.size
    target_fps = clip.fps

    parts = []
    intro_video = None

    # ── Intro ───────────────────────────────────────────────────────────────
    if intro_path and Path(intro_path).exists():
        if verbose:
            print(f"  Loading intro: {Path(intro_path).name}")
        intro = VideoFileClip(str(intro_path))

        if (intro.w, intro.h) != (target_w, target_h):
            if verbose:
                print(f"    Resizing intro {intro.w}x{intro.h} → {target_w}x{target_h}")
            intro = intro.resized(new_size=(target_w, target_h))

        if intro.fps != target_fps:
            intro = intro.with_fps(target_fps)

        parts.append(intro)
        intro_video = intro

    parts.append(clip)

    # ── Closing ─────────────────────────────────────────────────────────────
    if closing_path and Path(closing_path).exists():
        if verbose:
            print(f"  Creating closing card: {closing_duration}s from {Path(closing_path).name}")
        closing = (
            ImageClip(str(closing_path), duration=closing_duration)
            .with_fps(target_fps)
        )

        if (closing.w, closing.h) != (target_w, target_h):
            if verbose:
                print(f"    Resizing closing {closing.w}x{closing.h} → {target_w}x{target_h}")
            closing = closing.resized(new_size=(target_w, target_h))

        parts.append(closing)

    if len(parts) == 1:
        return clip, None

    if verbose:
        durations = " + ".join(f"{p.duration:.1f}s" for p in parts)
        print(f"  Concatenating: {durations}")

    final = concatenate_videoclips(
        parts,
        method="compose",
        bg_color=(0, 0, 0),
    )

    return final, intro_video
