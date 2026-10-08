"""Tests for config loading, defaults, and merge logic."""

import tempfile
from pathlib import Path

import yaml


def test_defaults_has_all_sections():
    from creacut.config import DEFAULTS

    expected_sections = [
        "whisper", "scripts", "chroma", "background", "skin_correction",
        "overlays", "styling", "bookends", "audio", "transitions", "retakes",
        "output",
    ]
    for section in expected_sections:
        assert section in DEFAULTS, f"Missing section: {section}"


def test_load_config_returns_defaults_when_no_file():
    from creacut.config import DEFAULTS, load_config

    config = load_config(None)
    assert config == DEFAULTS


def test_load_config_merges_yaml_over_defaults():
    from creacut.config import load_config

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yml", delete=False
    ) as f:
        yaml.dump({"whisper": {"model": "tiny", "language": "en"}}, f)
        f.flush()
        config = load_config(f.name)

    assert config["whisper"]["model"] == "tiny"
    assert config["whisper"]["language"] == "en"
    # Other defaults preserved
    assert "chroma" in config
    assert config["chroma"]["enabled"] is True

    Path(f.name).unlink()


def test_resolve_config_cli_overrides_yaml():
    from creacut.config import resolve_config

    config = {"chroma": {"enabled": True, "color": [24, 238, 28]}}
    cli = {"chroma_color": [0, 255, 0], "no_chroma": True}
    resolved = resolve_config(cli, config)

    assert resolved["chroma"]["enabled"] is False
    assert resolved["chroma"]["color"] == [0, 255, 0]


def test_resolve_config_none_cli_values_ignored():
    from creacut.config import resolve_config

    config = {"chroma": {"enabled": True, "color": [24, 238, 28]}}
    cli = {"chroma_color": None, "no_chroma": None}
    resolved = resolve_config(cli, config)

    assert resolved["chroma"]["enabled"] is True
    assert resolved["chroma"]["color"] == [24, 238, 28]
