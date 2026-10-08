"""Shared types, constants, and text helpers for the CREAcut pipeline."""

import re
from dataclasses import dataclass, field
from pathlib import Path


# ── Font resolution ────────────────────────────────────────────────────────

_PACKAGE_DIR = Path(__file__).resolve().parent
_ASSETS_DIR = _PACKAGE_DIR.parent / "assets"
_BUNDLED_FONT = _ASSETS_DIR / "fonts" / "Inter-Variable.ttf"


def find_font(preferred: str | None = None) -> str:
    """Resolve a font path. 'auto' or None returns the bundled Inter font."""
    if preferred and preferred != "auto":
        p = Path(preferred)
        if p.exists():
            return str(p)
        raise FileNotFoundError(f"Font not found: {preferred}")

    if _BUNDLED_FONT.exists():
        return str(_BUNDLED_FONT)

    # Fallback: try common system font paths
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),      # Linux
        Path("/System/Library/Fonts/Helvetica.ttc"),                    # macOS
        Path("C:/Windows/Fonts/arial.ttf"),                             # Windows
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    raise FileNotFoundError(
        "No font found. Install Inter-Variable.ttf in assets/fonts/ "
        "or set styling.font in creacut.yml"
    )


# ── Script discovery ───────────────────────────────────────────────────────

def find_script_files(directory: str, glob_pattern: str = "**/*.md") -> list[Path]:
    """Find script files in a directory. Returns sorted list of paths."""
    d = Path(directory)
    if not d.is_dir():
        return []
    return sorted(d.glob(glob_pattern))


# ── Text helpers ───────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


# ── Script parsing ─────────────────────────────────────────────────────────

def parse_guion(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    if len(parts) < 3:
        return []
    body = parts[2].strip()
    paragraphs = []
    for line in body.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("!"):
            line = line[1:].strip()
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        paragraphs.append(line)
    return paragraphs


def guion_sentences(paragraphs: list[str]) -> list["GuionSentence"]:
    result = []
    for p_idx, para in enumerate(paragraphs):
        for s_idx, sent in enumerate(split_sentences(para)):
            result.append(GuionSentence(p_idx, s_idx, sent, normalize(sent)))
    return result


# ── Dataclasses ────────────────────────────────────────────────────────────

TERM_DISPLAY_DURATION = 5.0


@dataclass
class GuionSentence:
    paragraph_idx: int
    sentence_idx: int
    text: str
    normalized: str


@dataclass
class MatchCandidate:
    sentence: GuionSentence
    start: float
    end: float
    score: float
    # Optional diagnostic metadata.  Existing callers can continue constructing
    # MatchCandidate with the original four fields.
    # Diagnostic fields are excluded from equality so the legacy four-field
    # value contract remains intact for existing callers and tests.
    transcript_text: str = field(default="", compare=False)
    segment_start_idx: int | None = field(default=None, compare=False)
    segment_end_idx: int | None = field(default=None, compare=False)
    refinements: tuple[str, ...] = field(default_factory=tuple, compare=False)


@dataclass
class CutSentence:
    text: str
    cut_start: float
    cut_end: float
    paragraph_idx: int
    sentence_idx: int
    raw_start: float = 0.0
    raw_end: float = 0.0


@dataclass
class ListDetection:
    trigger_sentence_idx: int
    end_sentence_idx: int
    marker_type: str
    num_items_hint: int | None
    item_sentence_indices: list[int] = field(default_factory=list)


@dataclass
class ListItem:
    label: str
    description: str
    sentence_idx: int
    image_path: str = ""


@dataclass
class ListOverlay:
    intro: str
    items: list[ListItem]
    cut_start: float
    cut_end: float
    item_timestamps: list[float]


@dataclass
class TermDetection:
    term: str
    definition: str
    sentence_idx: int


@dataclass
class TermOverlay:
    term: str
    definition: str
    cut_start: float
    cut_end: float
    module_slug: str = ""


@dataclass
class EquationStep:
    latex: str
    keyword: str


@dataclass
class EquationOverlay:
    id: str
    title: str
    steps: list[EquationStep]
    paragraph_idx: int
    cut_start: float
    cut_end: float
    step_timestamps: list[float] = field(default_factory=list)
