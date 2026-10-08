"""Shared fixtures for CREAcut tests."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sample_script(tmp_dir):
    """Create a minimal Markdown script file."""
    content = (
        "---\ntitle: Sample Script\n---\n"
        "Welcome to this lesson. Today we will learn about testing.\n\n"
        "The first concept is unit testing. It verifies individual components.\n\n"
        "The second concept is integration testing. It checks how parts work together.\n"
    )
    path = tmp_dir / "sample-script.md"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def sample_segments():
    """Simulated Whisper transcription segments, one sentence per segment
    (matching typical Whisper VAD-based segmentation granularity)."""
    return [
        {
            "start": 0.0, "end": 1.2,
            "text": " Welcome to this lesson.",
            "no_speech_prob": 0.05,
            "words": [
                {"word": " Welcome", "start": 0.0, "end": 0.5},
                {"word": " to", "start": 0.5, "end": 0.6},
                {"word": " this", "start": 0.6, "end": 0.8},
                {"word": " lesson.", "start": 0.8, "end": 1.2},
            ],
        },
        {
            "start": 1.5, "end": 3.0,
            "text": " Today we will learn about testing.",
            "no_speech_prob": 0.05,
            "words": [
                {"word": " Today", "start": 1.5, "end": 1.8},
                {"word": " we", "start": 1.8, "end": 1.9},
                {"word": " will", "start": 1.9, "end": 2.1},
                {"word": " learn", "start": 2.1, "end": 2.4},
                {"word": " about", "start": 2.4, "end": 2.6},
                {"word": " testing.", "start": 2.6, "end": 3.0},
            ],
        },
        {
            "start": 5.0, "end": 6.3,
            "text": " The first concept is unit testing.",
            "no_speech_prob": 0.03,
            "words": [
                {"word": " The", "start": 5.0, "end": 5.1},
                {"word": " first", "start": 5.1, "end": 5.3},
                {"word": " concept", "start": 5.3, "end": 5.6},
                {"word": " is", "start": 5.6, "end": 5.7},
                {"word": " unit", "start": 5.7, "end": 5.9},
                {"word": " testing.", "start": 5.9, "end": 6.3},
            ],
        },
        {
            "start": 6.5, "end": 9.0,
            "text": " It verifies individual components.",
            "no_speech_prob": 0.03,
            "words": [
                {"word": " It", "start": 6.5, "end": 6.6},
                {"word": " verifies", "start": 6.6, "end": 7.0},
                {"word": " individual", "start": 7.0, "end": 7.5},
                {"word": " components.", "start": 7.5, "end": 8.0},
            ],
        },
        {
            "start": 10.0, "end": 11.7,
            "text": " The second concept is integration testing.",
            "no_speech_prob": 0.04,
            "words": [
                {"word": " The", "start": 10.0, "end": 10.1},
                {"word": " second", "start": 10.1, "end": 10.4},
                {"word": " concept", "start": 10.4, "end": 10.7},
                {"word": " is", "start": 10.7, "end": 10.8},
                {"word": " integration", "start": 10.8, "end": 11.3},
                {"word": " testing.", "start": 11.3, "end": 11.7},
            ],
        },
        {
            "start": 12.0, "end": 14.0,
            "text": " It checks how parts work together.",
            "no_speech_prob": 0.04,
            "words": [
                {"word": " It", "start": 12.0, "end": 12.1},
                {"word": " checks", "start": 12.1, "end": 12.4},
                {"word": " how", "start": 12.4, "end": 12.6},
                {"word": " parts", "start": 12.6, "end": 12.9},
                {"word": " work", "start": 12.9, "end": 13.2},
                {"word": " together.", "start": 13.2, "end": 13.6},
            ],
        },
    ]
