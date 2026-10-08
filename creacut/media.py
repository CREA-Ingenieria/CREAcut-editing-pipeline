"""Small, optional media probes shared by project generation and rendering."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


_DURATION_RE = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)")


def ffmpeg_executable() -> str:
    """Return the bundled FFmpeg when available, otherwise the system command."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return "ffmpeg"


def probe_media_duration(path: str | Path) -> float | None:
    """Return a finite container duration without making FFmpeg a hard dependency.

    ``imageio-ffmpeg`` supplies a bundled executable in normal installations.
    A failure to inspect media is intentionally non-fatal: project-only
    analysis must still work in offline and test environments.
    """
    source = Path(path)
    try:
        executable = ffmpeg_executable()
        completed = subprocess.run(
            [executable, "-hide_banner", "-i", str(source)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False,
        )
        match = _DURATION_RE.search(completed.stderr or "")
        if match is not None:
            hours, minutes, seconds = match.groups()
            duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            return duration if duration > 0.0 else None
    except (OSError, subprocess.SubprocessError, ImportError, ValueError):
        pass

    # OpenCV is already a core dependency and gives a practical fallback for
    # common constant-frame-rate camera files.
    try:
        import cv2

        capture = cv2.VideoCapture(str(source))
        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            frame_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0.0 else 0.0
            return duration if duration > 0.0 else None
        finally:
            capture.release()
    except Exception:  # Media probing must never block project creation.
        return None
