"""Configuration loading: YAML file + CLI overrides + built-in defaults."""

import copy
from pathlib import Path

import yaml

DEFAULTS = {
    "whisper": {
        "model": "large-v3",
        "prompt": "",
        "language": "es",
    },
    "scripts": {
        "directory": None,
        "format": "markdown",
    },
    "chroma": {
        "enabled": True,
        "color": [24, 238, 28],
        "inner_threshold": 40,
        "outer_threshold": 100,
        "blur_radius": 3,
        "morph_close_radius": 2,
        "pre_blur_radius": 1,
        "despill_strength": 0.8,
        "subject_despill_strength": 0.8,
        "s_min": 100,
        "v_min": 120,
    },
    "background": {
        "image": None,
    },
    "skin_correction": {
        "enabled": False,
        "hue_shift": -12,
        "sat_scale": 0.88,
        "sat_clamp": 155,
        "strength": 1.0,
    },
    "overlays": {
        "lists": {
            "enabled": True,
            "llm_provider": "auto",
            "ollama_model": "gemma4",
            "claude_model": "claude-haiku-4-5-20251001",
        },
        "terms": {
            "enabled": True,
            "vocab_file": None,
            "display_duration": 5.0,
        },
        "equations": {
            "enabled": False,
            "specs_file": None,
        },
        "bold_cards": {
            "enabled": True,
        },
    },
    "styling": {
        "font": "auto",
        "accent_colors": [
            [229, 72, 155],
            [39, 194, 224],
            [220, 203, 98],
            [177, 74, 203],
            [43, 188, 199],
        ],
        "panel_bg": [243, 245, 248, 230],
        "panel_radius": 16,
    },
    "bookends": {
        "intro_video": None,
        "closing_image": None,
        "closing_duration": 5.0,
    },
    "audio": {
        "normalize": True,
        "fade_duration": 0.06,
    },
    "transitions": {
        "type": "dissolve",
        "crossfade": 0.20,
    },
    "visual_effects": {
        "ranges": [],
    },
    "retakes": {
        "restart_words": [
            "perdón", "perdon", "dale", "otra vez", "se me fue",
            "me equivoqué", "me equivoque", "no no", "espera",
        ],
        "merge_gap": 5.0,
        "split_gap": 4.0,
        "min_pre_gap_dur": 1.0,
        "max_word_gap": 8.0,
        "match_threshold": 0.55,
        "good_match_threshold": 0.6,
        "pad_start": 0.1,
        "pad_end": 0.25,
    },
    "output": {
        "directory": None,
        "suffix": "_edited",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. override values win."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(path: str | None = None) -> dict:
    """Load config from YAML file, merged over built-in defaults.

    Search order when path is None:
      1. ./creacut.yml
      2. ~/.config/creacut/creacut.yml
    """
    config = copy.deepcopy(DEFAULTS)

    if path is None:
        candidates = [
            Path("creacut.yml"),
            Path.home() / ".config" / "creacut" / "creacut.yml",
        ]
        for candidate in candidates:
            if candidate.exists():
                path = str(candidate)
                break

    if path is not None:
        p = Path(path)
        if p.exists():
            with open(p, encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            config = _deep_merge(config, user_config)

    return config


_CLI_TO_CONFIG = {
    "no_chroma": ("chroma", "enabled", lambda v: not v),
    "chroma_color": ("chroma", "color", None),
    "bg_image": ("background", "image", None),
    "skin_correction": ("skin_correction", "enabled", None),
    "skin_hue_shift": ("skin_correction", "hue_shift", None),
    "skin_sat_scale": ("skin_correction", "sat_scale", None),
    "skin_sat_clamp": ("skin_correction", "sat_clamp", None),
    "no_overlays": ("overlays", "lists", lambda v: {"enabled": not v}),
    "no_bookends": ("bookends", "intro_video", lambda v: None if v else ...),
    "no_normalize": ("audio", "normalize", lambda v: not v),
}


def resolve_config(cli_args: dict, config: dict) -> dict:
    """Merge CLI arguments over config. None values in cli_args are skipped."""
    result = copy.deepcopy(config)

    for cli_key, mapping in _CLI_TO_CONFIG.items():
        value = cli_args.get(cli_key)
        if value is None:
            continue

        section, key, transform = mapping
        if transform is not None:
            transformed = transform(value)
            if isinstance(transformed, dict):
                if section in result and isinstance(result[section], dict):
                    result[section].update(transformed)
            elif transformed is not ...:
                result[section][key] = transformed
        else:
            result[section][key] = value

    return result
