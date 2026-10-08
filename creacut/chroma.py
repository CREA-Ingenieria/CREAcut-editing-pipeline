"""Stage 8 — Green screen replacement with HSV keying, edge smoothing, and spill suppression."""

import cv2
import numpy as np

# HSV distance weights (OpenCV H: 0-179 circular, S: 0-255, V: 0-255)
_H_WEIGHT = 2.0   # hue carries the most color identity; max circular dist = 90
_S_WEIGHT = 1.0   # saturation separates green from white/gray shadows
_V_WEIGHT = 0.2   # brightness barely matters — dark green shadows still key


def _rgb_to_hsv_scalar(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    pixel = np.array([[rgb]], dtype=np.uint8)
    hsv = cv2.cvtColor(pixel, cv2.COLOR_RGB2HSV)[0, 0]
    return float(hsv[0]), float(hsv[1]), float(hsv[2])


def _make_keyer(
    color: tuple[int, int, int],
    inner: int,
    outer: int,
    blur_radius: int,
    despill_strength: float,
    subject_despill_strength: float,
    s_min: int,
    v_min: int,
    morph_close_radius: int,
    pre_blur_radius: int,
):
    """Return key_frame(frame) → (alpha float32 H×W, frame_f float32 H×W×3).

    Shared keying logic used by both make_chroma_replacer and make_alpha_extractor.
    Steps 1-3: HSV distance keying, morphological close, Gaussian blur, spill suppression.
    """
    target_h, target_s, target_v = _rgb_to_hsv_scalar(color)
    span = float(outer - inner)
    blur_k = 2 * blur_radius + 1 if blur_radius > 0 else 0
    pre_blur_k = 2 * pre_blur_radius + 1 if pre_blur_radius > 0 else 0
    _morph_kernel = (
        cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (2 * morph_close_radius + 1, 2 * morph_close_radius + 1),
        )
        if morph_close_radius > 0
        else None
    )

    def key_frame(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        # 1. HSV-space weighted distance
        work = cv2.GaussianBlur(frame, (pre_blur_k, pre_blur_k), 0) if pre_blur_k > 0 else frame
        hsv = cv2.cvtColor(work, cv2.COLOR_RGB2HSV).astype(np.float32)
        dH = np.abs(hsv[..., 0] - target_h)
        dH = np.minimum(dH, 180.0 - dH)          # circular Hue wraparound
        dist = np.sqrt(
            (dH * _H_WEIGHT) ** 2
            + ((hsv[..., 1] - target_s) * _S_WEIGHT) ** 2
            + ((hsv[..., 2] - target_v) * _V_WEIGHT) ** 2
        )
        not_green_screen = (hsv[..., 1] < s_min) | (hsv[..., 2] < v_min)
        dist = np.where(not_green_screen, outer + 1.0, dist)

        # alpha=0 → background, alpha=1 → subject
        alpha = np.clip((dist - inner) / span, 0.0, 1.0)

        # 2a. Morphological close on raw alpha
        if _morph_kernel is not None:
            alpha_u8 = (alpha * 255).astype(np.uint8)
            alpha_u8 = cv2.morphologyEx(alpha_u8, cv2.MORPH_CLOSE, _morph_kernel)
            alpha = alpha_u8.astype(np.float32) / 255.0

        # 2b. Gaussian blur on alpha mask
        if blur_k > 0:
            alpha = cv2.GaussianBlur(alpha, (blur_k, blur_k), 0)
            alpha = np.where(dist >= outer, 1.0, alpha)

        # 3. Green spill suppression
        frame_f = frame.astype(np.float32)
        spill = np.maximum(0.0, frame_f[..., 1] - np.maximum(frame_f[..., 0], frame_f[..., 2]))
        frame_f[..., 1] -= despill_strength * spill * (1.0 - alpha)
        frame_f[..., 1] -= subject_despill_strength * spill * alpha
        np.clip(frame_f, 0.0, 255.0, out=frame_f)

        return alpha, frame_f

    return key_frame


def make_chroma_replacer(config: dict):
    """Return a per-frame green-screen replacer (RGB output).

    Reads chroma parameters from config["chroma"] and the background image
    path from config["background"]["image"].

    Pipeline per frame:
      1. HSV weighted distance   → soft alpha mask
      2. Gaussian blur on alpha  → smooth edges, reduces aliasing
      3. Spill suppression       → removes green cast from subject edges/interior
      4. Blend original + background (config background image, or white if none)
    """
    chroma_cfg = config["chroma"]
    chroma_color = tuple(chroma_cfg["color"])
    inner = chroma_cfg["inner_threshold"]
    outer = chroma_cfg["outer_threshold"]
    blur_radius = chroma_cfg["blur_radius"]
    morph_close_radius = chroma_cfg.get("morph_close_radius", 2)
    pre_blur_radius = chroma_cfg.get("pre_blur_radius", 1)
    despill_strength = chroma_cfg["despill_strength"]
    subject_despill_strength = chroma_cfg.get("subject_despill_strength", 0.8)
    s_min = chroma_cfg.get("s_min", 100)
    v_min = chroma_cfg.get("v_min", 120)
    bg_path = config.get("background", {}).get("image")

    key_frame = _make_keyer(chroma_color, inner, outer, blur_radius, despill_strength,
                             subject_despill_strength, s_min, v_min,
                             morph_close_radius, pre_blur_radius)

    if bg_path is not None:
        _bg = cv2.imread(bg_path)
        if _bg is None:
            raise FileNotFoundError(f"Background image not found: {bg_path}")
        bg_img: np.ndarray | None = cv2.cvtColor(_bg, cv2.COLOR_BGR2RGB).astype(np.float32)
    else:
        bg_img = None

    def replace(frame: np.ndarray) -> np.ndarray:
        alpha, frame_f = key_frame(frame)
        a = alpha[..., np.newaxis]
        if bg_img is not None:
            bg = cv2.resize(bg_img, (frame.shape[1], frame.shape[0])) if bg_img.shape[:2] != frame.shape[:2] else bg_img
        else:
            bg = np.full_like(frame_f, 255.0)
        return (frame_f * a + bg * (1.0 - a)).astype(np.uint8)

    return replace


def make_alpha_extractor(config: dict):
    """Return a per-frame RGBA extractor (speaker silhouette with transparency).

    Reads chroma parameters from config["chroma"]. Same keying pipeline as
    make_chroma_replacer but outputs RGBA instead of blending with a background.
    Use for free-position compositing in overlay.py.
    alpha=0 → fully transparent (background), alpha=255 → fully opaque (subject).
    """
    chroma_cfg = config["chroma"]
    chroma_color = tuple(chroma_cfg["color"])
    inner = chroma_cfg["inner_threshold"]
    outer = chroma_cfg["outer_threshold"]
    blur_radius = chroma_cfg["blur_radius"]
    morph_close_radius = chroma_cfg.get("morph_close_radius", 2)
    pre_blur_radius = chroma_cfg.get("pre_blur_radius", 1)
    despill_strength = chroma_cfg["despill_strength"]
    subject_despill_strength = chroma_cfg.get("subject_despill_strength", 0.8)
    s_min = chroma_cfg.get("s_min", 100)
    v_min = chroma_cfg.get("v_min", 120)

    key_frame = _make_keyer(chroma_color, inner, outer, blur_radius, despill_strength,
                             subject_despill_strength, s_min, v_min,
                             morph_close_radius, pre_blur_radius)

    def extract(frame: np.ndarray) -> np.ndarray:
        alpha, frame_f = key_frame(frame)
        alpha_u8 = (alpha * 255).astype(np.uint8)
        return np.dstack([frame_f.astype(np.uint8), alpha_u8])  # (H, W, 4) RGBA

    return extract


def extract_raw_frame(video_path: str, time_s: float) -> np.ndarray:
    """Return the single raw RGB frame (H, W, 3, uint8) at time_s from video_path.

    Used by the desktop editor's static-frame background preview (see
    creacut/ui/qt.py). Deliberately separate from cut.py's clip-building path:
    this only needs one decoded frame, not a full VideoFileClip render graph.
    """
    from moviepy import VideoFileClip  # lazy: keep moviepy off the import path

    with VideoFileClip(str(video_path)) as clip:
        t = min(max(0.0, time_s), max(0.0, clip.duration - 1e-3))
        return clip.get_frame(t)
