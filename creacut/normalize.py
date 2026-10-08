"""Stage 11 — EBU R128 audio loudness normalization via FFmpeg loudnorm."""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .media import ffmpeg_executable


def _get_audio_sample_rate(input_path: Path) -> str:
    """Return the sample rate of the first audio stream, e.g. '44100'."""
    r = subprocess.run(
        [
            ffmpeg_executable(), "-hide_banner", "-i",
            str(input_path),
        ],
        capture_output=True,
        text=True,
    )
    match = re.search(r"Audio:.*?\b(\d{4,6}) Hz\b", r.stderr or "", re.DOTALL)
    return match.group(1) if match else "44100"


def normalize_audio(
    input_path: Path,
    target_lufs: float = -16.0,
    true_peak: float = -2.0,
    lra: float = 11.0,
    verbose: bool = False,
) -> Path:
    """Two-pass EBU R128 loudness normalization on a video file.

    Pass 1 measures integrated loudness of the full file; Pass 2 applies a
    linear gain correction using the measured values (-c:v copy skips video
    re-encode). Overwrites the input file in-place via a temp file.

    Returns the (same) input_path on success.
    If the audio track is silent or unmeasurable, returns input_path unchanged.
    """
    input_path = Path(input_path)

    # Read original sample rate to prevent loudnorm from upsampling to 96 kHz.
    sample_rate = _get_audio_sample_rate(input_path)

    filter_base = f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}"

    # ── Pass 1: measure ──────────────────────────────────────────────────────
    if verbose:
        print("  [normalize] Pass 1: measuring loudness…")

    p1 = subprocess.run(
        [
            ffmpeg_executable(), "-hide_banner", "-y",
            "-i", str(input_path),
            "-af", f"{filter_base}:print_format=json",
            "-f", "null", os.devnull,
        ],
        capture_output=True,
        text=True,
    )

    measured = _parse_loudnorm_json(p1.stderr)
    if measured is None:
        print("  [normalize] Warning: could not parse loudnorm output — skipping normalization")
        return input_path

    if verbose:
        print(
            f"  [normalize] Measured: I={measured['input_i']} LUFS  "
            f"TP={measured['input_tp']} dBTP  LRA={measured['input_lra']} LU"
        )

    # ── Pass 2: apply ────────────────────────────────────────────────────────
    filter_p2 = (
        f"{filter_base}"
        f":measured_I={measured['input_i']}"
        f":measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}"
        f":measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}"
        f":linear=true"
    )

    suffix = input_path.suffix
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=input_path.parent)
    os.close(tmp_fd)

    if verbose:
        print(f"  [normalize] Pass 2: applying normalization → {Path(tmp_path).name}")

    p2 = subprocess.run(
        [
            ffmpeg_executable(), "-hide_banner", "-y",
            "-i", str(input_path),
            "-af", filter_p2,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", sample_rate,
            tmp_path,
        ],
        capture_output=not verbose,
        text=True,
    )

    if p2.returncode != 0:
        os.unlink(tmp_path)
        stderr = p2.stderr if hasattr(p2, "stderr") and p2.stderr else ""
        print(f"  [normalize] Warning: FFmpeg pass 2 failed — skipping normalization\n{stderr[:400]}")
        return input_path

    os.replace(tmp_path, input_path)

    if verbose:
        print(f"  [normalize] ✓ Normalized to {target_lufs} LUFS")

    return input_path


def _parse_loudnorm_json(stderr: str) -> dict | None:
    """Extract the JSON block that loudnorm prints to stderr."""
    match = re.search(r"\{[^{}]+\}", stderr, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    required = {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}
    if not required.issubset(data.keys()):
        return None
    # Reject unmeasured / silence
    try:
        if float(data["input_i"]) < -70:
            return None
    except (ValueError, TypeError):
        return None
    return data
