"""Stage 8.5 — Skin tone color correction.

Detects skin pixels via YCbCr thresholds and applies selective HSV adjustments
to correct greenish/yellowish casts and over-saturated reds. Frame format: RGB
uint8 (H, W, 3) in and out — same contract as make_chroma_replacer.

Apply after chroma key so the white background doesn't interfere with skin detection.
"""

import cv2
import numpy as np

# YCbCr skin detection thresholds (Kovac et al. / ITU-R BT.601)
_SKIN_Y_MIN = 80
_SKIN_CB_MIN = 77
_SKIN_CB_MAX = 127
_SKIN_CR_MIN = 133
_SKIN_CR_MAX = 173

_MASK_DILATE_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
_MASK_BLUR_SIGMA = 3


def _detect_skin_mask(frame_rgb: np.ndarray) -> np.ndarray:
    """Return a float32 mask [0,1] where 1 = skin pixel."""
    ycbcr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2YCrCb)  # OpenCV order: Y, Cr, Cb
    y, cr, cb = ycbcr[..., 0], ycbcr[..., 1], ycbcr[..., 2]

    skin = (
        (y > _SKIN_Y_MIN)
        & (cb >= _SKIN_CB_MIN) & (cb <= _SKIN_CB_MAX)
        & (cr >= _SKIN_CR_MIN) & (cr <= _SKIN_CR_MAX)
    ).astype(np.uint8)

    skin = cv2.dilate(skin, _MASK_DILATE_KERNEL)
    mask_f = cv2.GaussianBlur(skin.astype(np.float32), (0, 0), sigmaX=_MASK_BLUR_SIGMA)
    return np.clip(mask_f, 0.0, 1.0)


def make_skin_corrector(config: dict):
    """Return a per-frame skin tone corrector (RGB uint8 in/out).

    Reads correction parameters from config["skin_correction"].

    Pipeline per frame:
      1. YCbCr skin detection → soft mask
      2. HSV hue shift on masked pixels (removes green/yellow cast)
      3. Saturation scale + clamp on masked pixels (tames over-red lips)
      4. Blend corrected pixels back using mask * strength
    """
    skin_cfg = config["skin_correction"]
    hue_shift = skin_cfg["hue_shift"]
    sat_scale = skin_cfg["sat_scale"]
    sat_clamp = skin_cfg["sat_clamp"]
    strength = skin_cfg.get("strength", 1.0)

    def correct(frame: np.ndarray) -> np.ndarray:
        mask = _detect_skin_mask(frame)
        if mask.max() == 0.0:
            return frame

        hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV).astype(np.float32)

        h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]

        # Hue shift with circular wraparound (OpenCV H: 0-179)
        h_corr = (h + hue_shift) % 180.0

        # Saturation: scale then clamp
        s_corr = np.minimum(s * sat_scale, float(sat_clamp))

        # Rebuild corrected HSV and convert to RGB
        hsv_corr = np.stack([h_corr, s_corr, v], axis=-1)
        corrected = cv2.cvtColor(hsv_corr.astype(np.uint8), cv2.COLOR_HSV2RGB)

        # Blend: only affect skin pixels, scaled by strength
        blend = mask[..., np.newaxis] * strength
        result = (frame.astype(np.float32) * (1.0 - blend) + corrected.astype(np.float32) * blend)
        return np.clip(result, 0, 255).astype(np.uint8)

    return correct
