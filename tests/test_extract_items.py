"""Tests for extract_items: regex fallback and helper functions."""

from creacut.config import DEFAULTS


def test_raw_to_cut_maps_correctly():
    from creacut.extract_items import raw_to_cut

    clean_ranges = [(2.0, 5.0), (10.0, 15.0)]
    # t=3.0 is 1.0s into first range → cut time 1.0
    assert raw_to_cut(3.0, clean_ranges) == 1.0
    # t=12.0 is 2.0s into second range, after 3.0s of first range → cut time 5.0
    assert raw_to_cut(12.0, clean_ranges) == 5.0


def test_raw_to_cut_returns_none_for_excluded():
    from creacut.extract_items import raw_to_cut

    clean_ranges = [(2.0, 5.0), (10.0, 15.0)]
    assert raw_to_cut(7.0, clean_ranges) is None


def test_regex_fallback_extracts_ordinals():
    from creacut.extract_items import _try_regex

    excerpt = (
        "Hay tres aspectos: La primera es la observación directa. "
        "La segunda es la experimentación controlada. "
        "La tercera es el análisis de datos."
    )
    result = _try_regex(excerpt, verbose=False)
    assert result is not None
    assert len(result["items"]) == 3
