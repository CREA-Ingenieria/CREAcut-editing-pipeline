"""Tests for list detection in script text."""

from creacut.common import GuionSentence, normalize


def _make_sents(texts):
    return [
        GuionSentence(i, 0, t, normalize(t))
        for i, t in enumerate(texts)
    ]


def test_detects_ordinal_list():
    from creacut.detect_lists import detect_lists

    sents = _make_sents([
        "Hay tres aspectos importantes.",
        "La primera es la fuerza.",
        "La segunda es la masa.",
        "La tercera es la aceleración.",
        "Estos conceptos se relacionan.",
    ])
    detections = detect_lists(sents)
    assert len(detections) >= 1
    assert detections[0].trigger_sentence_idx == 0


def test_no_detection_on_plain_text():
    from creacut.detect_lists import detect_lists

    sents = _make_sents([
        "Este es un párrafo simple sin listas.",
        "Otro párrafo también simple.",
    ])
    detections = detect_lists(sents)
    assert len(detections) == 0
