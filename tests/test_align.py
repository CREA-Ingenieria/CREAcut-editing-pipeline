"""Tests for alignment and range processing."""

from creacut.common import GuionSentence, normalize
from creacut.config import DEFAULTS


def test_merge_ranges_combines_close_segments():
    from creacut.align import merge_ranges

    ranges = [(0.0, 5.0), (6.0, 10.0), (20.0, 25.0)]
    result = merge_ranges(ranges, DEFAULTS)
    # Gap 5→6 = 1s < merge_gap(5.0), so merged
    assert result[0] == (0.0, 10.0)
    # Gap 10→20 = 10s > merge_gap, so separate
    assert result[1] == (20.0, 25.0)


def test_pad_ranges_adds_padding():
    from creacut.align import pad_ranges

    ranges = [(5.0, 10.0)]
    result = pad_ranges(ranges, 20.0, DEFAULTS)
    assert result[0][0] < 5.0  # padded start
    assert result[0][1] > 10.0  # padded end


def test_pad_ranges_clamps_to_zero():
    from creacut.align import pad_ranges

    ranges = [(0.05, 5.0)]
    result = pad_ranges(ranges, 10.0, DEFAULTS)
    assert result[0][0] >= 0.0


def test_find_matches_returns_candidates(sample_segments):
    from creacut.align import find_matches

    sent = GuionSentence(0, 0, "Welcome to this lesson.", normalize("Welcome to this lesson."))
    matches = find_matches(sent, sample_segments, DEFAULTS)
    assert len(matches) >= 1
    assert matches[0].score > 0.3
