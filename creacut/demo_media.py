"""Small deterministic media fixture for trying the local CREAcut editor.

The fixture is generated without Whisper, network access, or an ``ffmpeg``
command on ``PATH``.  ``moviepy`` already installs ``imageio-ffmpeg``; that
package supplies the exact FFmpeg executable used here.
"""

from __future__ import annotations

import math
import os
import subprocess
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


DEMO_DURATION_S = 12.0
DEMO_WIDTH = 640
DEMO_HEIGHT = 360
DEMO_FPS = 24


class DemoMediaError(RuntimeError):
    """The bundled FFmpeg executable could not create the demo media."""


_SECTIONS = (
    (0.0, 4.0, "TOMA A", "Primera alternativa", (24, 104, 164)),
    (4.0, 8.0, "TOMA B", "Recomendada por CREAcut", (222, 112, 45)),
    (8.0, 12.0, "FINAL", "Segunda oración", (38, 145, 93)),
)


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    )
    for name in candidates:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            pass
    # Pillow 10+ supports a scaled embedded fallback font.
    return ImageFont.load_default(size=size)


_FONT_SMALL = _load_font(18)
_FONT_MEDIUM = _load_font(25, bold=True)
_FONT_LARGE = _load_font(64, bold=True)
_FONT_CLOCK = _load_font(31, bold=True)


def _centered_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    *,
    fill: tuple[int, int, int],
) -> None:
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    draw.text(
        (xy[0] - width / 2, xy[1] - height / 2 - bounds[1]),
        text,
        font=font,
        fill=fill,
    )


def _section_at(time_s: float) -> tuple[float, float, str, str, tuple[int, int, int]]:
    for section in _SECTIONS:
        if time_s < section[1]:
            return section
    return _SECTIONS[-1]


def _render_frame(time_s: float) -> bytes:
    start_s, end_s, title, subtitle, color = _section_at(time_s)
    image = Image.new("RGB", (DEMO_WIDTH, DEMO_HEIGHT), color)
    draw = ImageDraw.Draw(image)

    # Layered bands make scene changes obvious even when text is not readable.
    draw.rectangle((0, 0, DEMO_WIDTH, 62), fill=(15, 23, 37))
    draw.rectangle((0, DEMO_HEIGHT - 72, DEMO_WIDTH, DEMO_HEIGHT), fill=(15, 23, 37))
    draw.text((22, 19), "CREAcut · DEMO LOCAL", font=_FONT_MEDIUM, fill=(243, 246, 250))

    pulse = (math.cos(time_s * math.tau) + 1.0) / 2.0
    radius = int(9 + pulse * 7)
    draw.ellipse(
        (DEMO_WIDTH - 35 - radius, 31 - radius, DEMO_WIDTH - 35 + radius, 31 + radius),
        fill=(255, 235, 110),
        outline=(255, 255, 255),
        width=2,
    )

    _centered_text(draw, (DEMO_WIDTH // 2, 151), title, _FONT_LARGE, fill=(255, 255, 255))
    _centered_text(draw, (DEMO_WIDTH // 2, 211), subtitle, _FONT_MEDIUM, fill=(245, 247, 250))
    _centered_text(
        draw,
        (DEMO_WIDTH // 2, 258),
        f"FUENTE  {time_s:05.2f} s",
        _FONT_CLOCK,
        fill=(255, 245, 177),
    )

    # Three-block source timeline with a frame-accurate playhead.
    left, right, top, bottom = 28, DEMO_WIDTH - 28, DEMO_HEIGHT - 47, DEMO_HEIGHT - 25
    span = right - left
    for index, section in enumerate(_SECTIONS):
        x0 = left + round(span * section[0] / DEMO_DURATION_S)
        x1 = left + round(span * section[1] / DEMO_DURATION_S)
        draw.rectangle((x0, top, x1, bottom), fill=section[4], outline=(232, 236, 241))
        label = ("A", "B", "F")[index]
        _centered_text(draw, ((x0 + x1) // 2, (top + bottom) // 2), label, _FONT_SMALL, fill=(255, 255, 255))
    playhead_x = left + round(span * min(time_s, DEMO_DURATION_S) / DEMO_DURATION_S)
    draw.line((playhead_x, top - 7, playhead_x, bottom + 7), fill=(255, 239, 72), width=4)

    section_progress = (time_s - start_s) / (end_s - start_s)
    draw.rounded_rectangle((175, 279, 465, 291), radius=6, fill=(12, 18, 27))
    draw.rounded_rectangle(
        (175, 279, 175 + round(290 * section_progress), 291),
        radius=6,
        fill=(255, 242, 152),
    )
    return image.tobytes()


def create_demo_video(
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Create the 12-second H.264/AAC media used by the editor demo.

    The final file is installed atomically, so an encoding failure never
    leaves a partially-written file at ``output_path``.
    """

    destination = Path(output_path).expanduser().resolve()
    if destination.exists() and not overwrite:
        raise FileExistsError(f"El video demo ya existe: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        import imageio_ffmpeg
    except ImportError as exc:  # pragma: no cover - moviepy supplies it normally
        raise DemoMediaError(
            "Falta imageio-ffmpeg. Instala el proyecto con: python -m pip install -e ."
        ) from exc

    ffmpeg_executable = imageio_ffmpeg.get_ffmpeg_exe()
    temporary = destination.with_name(
        f".{destination.stem}.{uuid.uuid4().hex}.tmp{destination.suffix or '.mp4'}"
    )
    # A short 880 Hz click at every full second.  The pulsing yellow marker in
    # the picture follows the same clock, which makes A/V sync easy to inspect.
    audio_source = (
        "aevalsrc=0.10*sin(2*PI*880*t)*"
        "lt(mod(t\\,1)\\,0.09):sample_rate=48000:duration=12"
    )
    command = [
        ffmpeg_executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{DEMO_WIDTH}x{DEMO_HEIGHT}",
        "-framerate",
        str(DEMO_FPS),
        "-i",
        "pipe:0",
        "-f",
        "lavfi",
        "-i",
        audio_source,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-ar",
        "48000",
        "-t",
        str(DEMO_DURATION_S),
        "-movflags",
        "+faststart",
        str(temporary),
    ]

    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        assert process.stdin is not None
        frame_count = round(DEMO_DURATION_S * DEMO_FPS)
        try:
            for frame_index in range(frame_count):
                process.stdin.write(_render_frame(frame_index / DEMO_FPS))
        except BrokenPipeError:
            # The diagnostic from FFmpeg below is more useful than EPIPE.
            pass
        finally:
            process.stdin.close()
        stderr = process.stderr.read() if process.stderr is not None else b""
        return_code = process.wait()
        if return_code != 0:
            diagnostic = stderr.decode("utf-8", errors="replace").strip()
            raise DemoMediaError(
                f"FFmpeg no pudo crear el video demo (código {return_code}): "
                f"{diagnostic or 'sin diagnóstico'}"
            )
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise DemoMediaError("FFmpeg terminó sin producir un video demo válido")
        os.replace(temporary, destination)
        return destination
    except OSError as exc:
        raise DemoMediaError(f"No se pudo ejecutar FFmpeg para crear el demo: {exc}") from exc
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        temporary.unlink(missing_ok=True)


__all__ = [
    "DEMO_DURATION_S",
    "DEMO_FPS",
    "DEMO_HEIGHT",
    "DEMO_WIDTH",
    "DemoMediaError",
    "create_demo_video",
]
