"""Integration contract for the self-contained editor demo video."""

from __future__ import annotations

from pathlib import Path

import imageio_ffmpeg
import pytest

from creacut.demo_media import (
    DEMO_DURATION_S,
    DEMO_FPS,
    DEMO_HEIGHT,
    DEMO_WIDTH,
    create_demo_video,
)


def test_create_demo_video_uses_bundled_ffmpeg_without_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "creacut-demo.mp4"
    monkeypatch.setenv("PATH", "")

    result = create_demo_video(output)

    assert result == output.resolve()
    assert output.stat().st_size > 0
    reader = imageio_ffmpeg.read_frames(str(output), pix_fmt="rgb24")
    try:
        metadata = next(reader)
    finally:
        reader.close()
    assert metadata["codec"] == "h264"
    assert metadata["audio_codec"] == "aac"
    assert metadata["pix_fmt"].startswith("yuv420p")
    assert metadata["size"] == (DEMO_WIDTH, DEMO_HEIGHT)
    assert metadata["fps"] == pytest.approx(DEMO_FPS)
    assert metadata["duration"] == pytest.approx(DEMO_DURATION_S, abs=0.05)

    with pytest.raises(FileExistsError, match="ya existe"):
        create_demo_video(output)


def test_create_demo_video_overwrites_only_when_requested(tmp_path: Path) -> None:
    output = tmp_path / "creacut-demo.mp4"
    output.write_bytes(b"not a video")

    result = create_demo_video(output, overwrite=True)

    assert result == output.resolve()
    assert output.read_bytes()[4:8] == b"ftyp"
