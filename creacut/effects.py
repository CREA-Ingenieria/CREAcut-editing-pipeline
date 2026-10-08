"""Time-bounded visual filters shared by preview and final rendering."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np


VISUAL_EFFECT_KINDS = {
    "cinematic",
    "warm",
    "cool",
    "black_white",
    "vintage",
    "vivid",
}


def visual_effect_ranges(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return validated source-time ranges in stable project order."""
    raw = config.get("visual_effects", {}).get("ranges", [])
    if not isinstance(raw, list):
        raise ValueError("visual_effects.ranges debe ser una lista")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"visual_effects.ranges[{index}] debe ser un objeto")
        effect_id = str(item.get("id", "")).strip()
        kind = str(item.get("kind", "")).strip()
        start = item.get("start_s")
        end = item.get("end_s")
        if not effect_id or effect_id in seen:
            raise ValueError(f"visual_effects.ranges[{index}].id no es válido o está repetido")
        if kind not in VISUAL_EFFECT_KINDS:
            raise ValueError(f"Efecto visual no compatible: {kind}")
        if isinstance(start, bool) or not isinstance(start, (int, float)):
            raise ValueError(f"visual_effects.ranges[{index}].start_s debe ser numérico")
        if isinstance(end, bool) or not isinstance(end, (int, float)):
            raise ValueError(f"visual_effects.ranges[{index}].end_s debe ser numérico")
        start_s = float(start)
        end_s = float(end)
        if start_s < 0 or end_s <= start_s:
            raise ValueError(f"visual_effects.ranges[{index}] tiene un intervalo inválido")
        seen.add(effect_id)
        result.append({"id": effect_id, "kind": kind, "start_s": start_s, "end_s": end_s})
    return result


def _contrast_brightness(frame: np.ndarray, contrast: float, brightness: float) -> np.ndarray:
    value = frame.astype(np.float32) * contrast * brightness
    value += (1.0 - contrast) * 127.5
    return np.clip(value, 0, 255).astype(np.uint8)


def _hsv(frame: np.ndarray, *, hue_degrees: float = 0.0, saturation: float = 1.0) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[:, :, 0] = (hsv[:, :, 0] + hue_degrees / 2.0) % 180.0
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)


def apply_visual_effect(frame: np.ndarray, kind: str) -> np.ndarray:
    """Apply one deterministic preset to an RGB uint8 frame."""
    if kind == "cinematic":
        return _hsv(_contrast_brightness(frame, 1.15, 0.96), hue_degrees=4, saturation=0.82)
    if kind == "warm":
        return _hsv(frame, hue_degrees=-8, saturation=1.20)
    if kind == "cool":
        return _hsv(frame, hue_degrees=12, saturation=0.90)
    if kind == "black_white":
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        return _contrast_brightness(cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB), 1.08, 1.0)
    if kind == "vintage":
        rgb = frame.astype(np.float32)
        matrix = np.array(
            [[0.393, 0.769, 0.189], [0.349, 0.686, 0.168], [0.272, 0.534, 0.131]],
            dtype=np.float32,
        )
        sepia = np.clip(rgb @ matrix.T, 0, 255).astype(np.uint8)
        return _contrast_brightness(sepia, 0.92, 0.96)
    if kind == "vivid":
        return _hsv(_contrast_brightness(frame, 1.08, 1.0), saturation=1.45)
    raise ValueError(f"Efecto visual no compatible: {kind}")


def apply_effects_at_source_time(
    frame: np.ndarray,
    source_time_s: float,
    ranges: list[dict[str, Any]],
) -> np.ndarray:
    result = frame
    for item in ranges:
        if item["start_s"] <= source_time_s < item["end_s"]:
            result = apply_visual_effect(result, item["kind"])
    return result


def apply_effect_ranges_to_clip(clip, source_start_s: float, config: dict[str, Any]):
    """Apply source-time effect ranges to a MoviePy clip without changing duration."""
    ranges = visual_effect_ranges(config)
    if not ranges:
        return clip

    def transform(get_frame, local_time_s: float):
        return apply_effects_at_source_time(
            get_frame(local_time_s),
            source_start_s + float(local_time_s),
            ranges,
        )

    return clip.transform(transform)
