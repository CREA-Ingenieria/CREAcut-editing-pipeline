"""Tests for common module: text helpers, guion parsing, font resolution."""

import tempfile
from pathlib import Path


def test_normalize_strips_punctuation_and_lowercases():
    from creacut.common import normalize

    assert normalize("¡Hola, Mundo!") == "hola mundo"
    assert normalize("  Hello   World  ") == "hello world"


def test_split_sentences():
    from creacut.common import split_sentences

    result = split_sentences("First sentence. Second one! Third?")
    assert result == ["First sentence.", "Second one!", "Third?"]


def test_split_sentences_empty():
    from creacut.common import split_sentences

    assert split_sentences("") == []


def test_parse_guion_markdown_with_frontmatter():
    from creacut.common import parse_guion

    content = "---\ntitle: Test\n---\nFirst paragraph.\n\nSecond paragraph.\n"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        f.flush()
        result = parse_guion(Path(f.name))

    assert len(result) == 2
    assert result[0] == "First paragraph."
    assert result[1] == "Second paragraph."
    Path(f.name).unlink()


def test_parse_guion_strips_bold_markers():
    from creacut.common import parse_guion

    content = "---\ntitle: Test\n---\nThis has **bold text** in it.\n"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        f.flush()
        result = parse_guion(Path(f.name))

    assert result[0] == "This has bold text in it."
    Path(f.name).unlink()


def test_parse_guion_strips_stage_directions():
    from creacut.common import parse_guion

    content = "---\ntitle: Test\n---\n!Stage direction\nNarration line.\n"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        f.flush()
        result = parse_guion(Path(f.name))

    assert result[0] == "Stage direction"
    assert result[1] == "Narration line."
    Path(f.name).unlink()


def test_guion_sentences():
    from creacut.common import guion_sentences

    paragraphs = ["First sentence. Second sentence.", "Third one."]
    result = guion_sentences(paragraphs)
    assert len(result) == 3
    assert result[0].text == "First sentence."
    assert result[0].paragraph_idx == 0
    assert result[0].sentence_idx == 0
    assert result[1].text == "Second sentence."
    assert result[2].paragraph_idx == 1


def test_find_font_returns_bundled_for_auto():
    from creacut.common import find_font

    font_path = find_font("auto")
    assert font_path is not None
    assert Path(font_path).name == "Inter-Variable.ttf"


def test_find_font_returns_explicit_path():
    from creacut.common import find_font

    with tempfile.NamedTemporaryFile(suffix=".ttf", delete=False) as f:
        f.write(b"fake font")
        result = find_font(f.name)

    assert result == f.name
    Path(f.name).unlink()
