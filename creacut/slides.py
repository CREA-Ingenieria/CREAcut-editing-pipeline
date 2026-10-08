"""Slide-deck import and persisted manifest support.

This module intentionally stops at ingestion.  It turns a PPTX, PDF, or image
directory into stable PNG assets next to a CREAcut project, but does not yet
place a slide on the video timeline or render it over the keyed speaker.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Mapping

from PIL import Image


SLIDES_EXTENSION_KEY = "creacut.slides"
SLIDES_STATE_VERSION = 1
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


class SlidesStateError(ValueError):
    """The persisted slide manifest is malformed."""


class SlideImportError(RuntimeError):
    """A source deck could not be converted into local slide images."""


def _string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise SlidesStateError(f"{path}: expected a {'string' if allow_empty else 'non-empty string'}")
    return value


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SlidesStateError(f"{path}: expected an integer >= {minimum}")
    return value


def _positive_int(value: Any, path: str) -> int:
    return _integer(value, path, minimum=1)


def _relative_to_project(path: Path, project_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def resolve_project_path(value: str, project_path: str | Path) -> Path:
    """Resolve a persisted project-relative path without changing the payload."""
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (Path(project_path).expanduser().resolve().parent / candidate).resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _natural_key(path: Path) -> tuple[Any, ...]:
    return tuple(int(value) if value.isdigit() else value.casefold() for value in re.split(r"(\d+)", path.name))


def _image_paths(directory: Path) -> list[Path]:
    return sorted(
        (item for item in directory.iterdir() if item.is_file() and item.suffix.casefold() in _IMAGE_SUFFIXES),
        key=_natural_key,
    )


def _asset_root(project_path: Path, source_sha256: str) -> Path:
    name = project_path.name
    stem = name[:-len(".creacut.json")] if name.casefold().endswith(".creacut.json") else project_path.stem
    return project_path.parent / f"{stem}.creacut-assets" / "slides" / source_sha256[:16]


@dataclass(frozen=True)
class SlideDeck:
    source_path: str
    source_sha256: str
    source_kind: str
    renderer: str
    asset_root: str
    imported_at_utc: str

    def validate(self, path: str = "slides.deck") -> None:
        _string(self.source_path, f"{path}.source_path")
        source_hash = _string(self.source_sha256, f"{path}.source_sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
            raise SlidesStateError(f"{path}.source_sha256: expected a SHA-256 hex digest")
        if self.source_kind not in {"pptx", "pdf", "images"}:
            raise SlidesStateError(f"{path}.source_kind: unsupported source type")
        _string(self.renderer, f"{path}.renderer")
        _string(self.asset_root, f"{path}.asset_root")
        _string(self.imported_at_utc, f"{path}.imported_at_utc")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "source_kind": self.source_kind,
            "renderer": self.renderer,
            "asset_root": self.asset_root,
            "imported_at_utc": self.imported_at_utc,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str = "slides.deck") -> "SlideDeck":
        if not isinstance(data, Mapping):
            raise SlidesStateError(f"{path}: expected an object")
        result = cls(
            source_path=_string(data.get("source_path"), f"{path}.source_path"),
            source_sha256=_string(data.get("source_sha256"), f"{path}.source_sha256"),
            source_kind=_string(data.get("source_kind"), f"{path}.source_kind"),
            renderer=_string(data.get("renderer"), f"{path}.renderer"),
            asset_root=_string(data.get("asset_root"), f"{path}.asset_root"),
            imported_at_utc=_string(data.get("imported_at_utc"), f"{path}.imported_at_utc"),
        )
        result.validate(path)
        return result


@dataclass(frozen=True)
class SlidePage:
    id: str
    index: int
    image_path: str
    thumbnail_path: str
    sha256: str
    width: int
    height: int
    text: str = ""
    # The recommendation is deliberately separate from `start_s`/`end_s`.
    # An imported deck must never start rendering merely because an algorithm
    # found a plausible sentence; the user accepts each cue (or all of them)
    # in the editor.
    recommended_start_s: float | None = None
    recommended_end_s: float | None = None
    recommendation_score: float = 0.0
    recommendation_reason: str = "Sin recomendación todavía"
    # "unscored" until an analysis pass has run at least once for this page;
    # "lexical-match" when the transcript overlap was strong enough to trust;
    # "ordered-fallback" when it wasn't and the cue came from slide order and
    # video duration instead. Never overwritten outside recommend_slide_pages.
    recommendation_mode: str = "unscored"
    start_s: float | None = None
    end_s: float | None = None
    enabled: bool = False
    # Normalised output rectangle and a normalised crop from the keyed camera
    # frame.  They are recomputed for every slide, so placement is genuinely
    # content-dependent instead of being a fixed left/right preset.
    x: float = 0.62
    y: float = 0.22
    speaker_width: float = 0.32
    height_fraction: float = 0.70
    crop_x: float = 0.15
    crop_y: float = 0.03
    crop_width: float = 0.70
    crop_height: float = 0.94

    def validate(self, path: str = "slides.pages[]") -> None:
        _string(self.id, f"{path}.id")
        _integer(self.index, f"{path}.index")
        _string(self.image_path, f"{path}.image_path")
        _string(self.thumbnail_path, f"{path}.thumbnail_path")
        source_hash = _string(self.sha256, f"{path}.sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
            raise SlidesStateError(f"{path}.sha256: expected a SHA-256 hex digest")
        _positive_int(self.width, f"{path}.width")
        _positive_int(self.height, f"{path}.height")
        _string(self.text, f"{path}.text", allow_empty=True)
        for key, value in (
            ("recommended_start_s", self.recommended_start_s),
            ("recommended_end_s", self.recommended_end_s),
            ("start_s", self.start_s),
            ("end_s", self.end_s),
        ):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
                raise SlidesStateError(f"{path}.{key}: expected a non-negative number or null")
        if self.recommended_start_s is not None and self.recommended_end_s is not None and self.recommended_end_s <= self.recommended_start_s:
            raise SlidesStateError(f"{path}.recommended_end_s: must be after recommended_start_s")
        if self.start_s is not None and self.end_s is not None and self.end_s <= self.start_s:
            raise SlidesStateError(f"{path}.end_s: must be after start_s")
        if self.enabled and (self.start_s is None or self.end_s is None):
            raise SlidesStateError(f"{path}: an enabled slide needs start_s and end_s")
        if isinstance(self.recommendation_score, bool) or not isinstance(self.recommendation_score, (int, float)) or not 0.0 <= self.recommendation_score <= 1.0:
            raise SlidesStateError(f"{path}.recommendation_score: expected a number between 0 and 1")
        _string(self.recommendation_reason, f"{path}.recommendation_reason", allow_empty=True)
        if self.recommendation_mode not in ("unscored", "lexical-match", "ordered-fallback"):
            raise SlidesStateError(f"{path}.recommendation_mode: expected unscored, lexical-match or ordered-fallback")
        if not isinstance(self.enabled, bool):
            raise SlidesStateError(f"{path}.enabled: expected a boolean")
        for key, value in (
            ("speaker_width", self.speaker_width), ("height_fraction", self.height_fraction),
            ("crop_x", self.crop_x), ("crop_y", self.crop_y), ("crop_width", self.crop_width), ("crop_height", self.crop_height),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
                raise SlidesStateError(f"{path}.{key}: expected a fraction between 0 and 1")
        # x/y are deliberately allowed a wider range than 0..1: the editor
        # lets the presenter be dragged so its placement box reaches past any
        # edge of the slide (like positioning an image in a document
        # editor). Preview and render clip the visible intersection without
        # changing this stored position or size. -1..1 bounds the origin,
        # not the far edge of the presenter's box.
        for key, value in (("x", self.x), ("y", self.y)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not -1.0 <= value <= 1.0:
                raise SlidesStateError(f"{path}.{key}: expected a fraction between -1 and 1")
        if self.speaker_width <= 0 or self.height_fraction <= 0:
            raise SlidesStateError(f"{path}: speaker rectangle must have a positive size")
        if self.crop_width <= 0 or self.crop_height <= 0 or self.crop_x + self.crop_width > 1.0 or self.crop_y + self.crop_height > 1.0:
            raise SlidesStateError(f"{path}: speaker crop must remain inside the camera frame")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "index": self.index,
            "image_path": self.image_path,
            "thumbnail_path": self.thumbnail_path,
            "sha256": self.sha256,
            "speaker_width": self.speaker_width,
            "height": self.height,
            "text": self.text,
            "recommended_start_s": self.recommended_start_s,
            "recommended_end_s": self.recommended_end_s,
            "recommendation_score": self.recommendation_score,
            "recommendation_reason": self.recommendation_reason,
            "recommendation_mode": self.recommendation_mode,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "enabled": self.enabled,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height_fraction": self.height_fraction,
            "crop_x": self.crop_x,
            "crop_y": self.crop_y,
            "crop_width": self.crop_width,
            "crop_height": self.crop_height,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str) -> "SlidePage":
        if not isinstance(data, Mapping):
            raise SlidesStateError(f"{path}: expected an object")
        result = cls(
            id=_string(data.get("id"), f"{path}.id"),
            index=_integer(data.get("index"), f"{path}.index"),
            image_path=_string(data.get("image_path"), f"{path}.image_path"),
            thumbnail_path=_string(data.get("thumbnail_path"), f"{path}.thumbnail_path"),
            sha256=_string(data.get("sha256"), f"{path}.sha256"),
            width=_positive_int(data.get("width"), f"{path}.width"),
            height=_positive_int(data.get("height"), f"{path}.height"),
            text=_string(data.get("text", ""), f"{path}.text", allow_empty=True),
            recommended_start_s=data.get("recommended_start_s"),
            recommended_end_s=data.get("recommended_end_s"),
            recommendation_score=data.get("recommendation_score", 0.0),
            recommendation_reason=_string(data.get("recommendation_reason", "Sin recomendación todavía"), f"{path}.recommendation_reason", allow_empty=True),
            recommendation_mode=data.get("recommendation_mode", "unscored"),
            start_s=data.get("start_s"),
            end_s=data.get("end_s"),
            enabled=data.get("enabled", False),
            x=data.get("x", 0.62),
            y=data.get("y", 0.22),
            speaker_width=data.get("speaker_width", 0.32),
            height_fraction=data.get("height_fraction", 0.70),
            crop_x=data.get("crop_x", 0.15),
            crop_y=data.get("crop_y", 0.03),
            crop_width=data.get("crop_width", 0.70),
            crop_height=data.get("crop_height", 0.94),
        )
        result.validate(path)
        return result


@dataclass(frozen=True)
class SlideTrackState:
    deck: SlideDeck
    pages: tuple[SlidePage, ...]
    version: int = SLIDES_STATE_VERSION

    def validate(self, path: str = "slides") -> None:
        if self.version != SLIDES_STATE_VERSION:
            raise SlidesStateError(f"{path}.version: unsupported version {self.version}")
        if not isinstance(self.deck, SlideDeck):
            raise SlidesStateError(f"{path}.deck: expected SlideDeck")
        self.deck.validate(f"{path}.deck")
        if not isinstance(self.pages, tuple) or not self.pages:
            raise SlidesStateError(f"{path}.pages: expected a non-empty immutable array")
        ids: set[str] = set()
        for expected_index, page in enumerate(self.pages):
            page_path = f"{path}.pages[{expected_index}]"
            if not isinstance(page, SlidePage):
                raise SlidesStateError(f"{page_path}: expected SlidePage")
            page.validate(page_path)
            if page.index != expected_index:
                raise SlidesStateError(f"{page_path}.index: expected {expected_index}")
            if page.id in ids:
                raise SlidesStateError(f"{page_path}.id: duplicate slide id")
            ids.add(page.id)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "version": self.version,
            "deck": self.deck.to_dict(),
            "pages": [page.to_dict() for page in self.pages],
        }

    def with_pages(self, pages: list[SlidePage] | tuple[SlidePage, ...]) -> "SlideTrackState":
        result = replace(self, pages=tuple(pages))
        result.validate()
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SlideTrackState":
        if not isinstance(data, Mapping):
            raise SlidesStateError("slides: expected an object")
        version = data.get("version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise SlidesStateError("slides.version: expected an integer")
        raw_pages = data.get("pages")
        if not isinstance(raw_pages, list):
            raise SlidesStateError("slides.pages: expected an array")
        result = cls(
            version=version,
            deck=SlideDeck.from_dict(data.get("deck")),
            pages=tuple(SlidePage.from_dict(item, f"slides.pages[{index}]") for index, item in enumerate(raw_pages)),
        )
        result.validate()
        return result

    def view(self, project_path: str | Path) -> dict[str, Any]:
        """Return paths resolved for Electron; persistence stays relative."""
        self.validate()
        return {
            "sourcePath": str(resolve_project_path(self.deck.source_path, project_path)),
            "sourceKind": self.deck.source_kind,
            "renderer": self.deck.renderer,
            "importedAtUtc": self.deck.imported_at_utc,
            "pages": [
                {
                    "id": page.id,
                    "index": page.index,
                    "imagePath": str(resolve_project_path(page.image_path, project_path)),
                    "thumbnailPath": str(resolve_project_path(page.thumbnail_path, project_path)),
                    "width": page.width,
                    "height": page.height,
                    "text": page.text,
                    "recommendedStartS": page.recommended_start_s,
                    "recommendedEndS": page.recommended_end_s,
                    "recommendationScore": page.recommendation_score,
                    "recommendationReason": page.recommendation_reason,
                    "recommendationMode": page.recommendation_mode,
                    "startS": page.start_s,
                    "endS": page.end_s,
                    "enabled": page.enabled,
                    "x": page.x,
                    "y": page.y,
                    "speakerWidth": page.speaker_width,
                    "heightFraction": page.height_fraction,
                    "cropX": page.crop_x,
                    "cropY": page.crop_y,
                    "cropWidth": page.crop_width,
                    "cropHeight": page.crop_height,
                }
                for page in self.pages
            ],
        }


def _directory_digest(directory: Path, images: list[Path]) -> str:
    digest = hashlib.sha256()
    for image in images:
        digest.update(image.name.encode("utf-8"))
        digest.update(_sha256_file(image).encode("ascii"))
    return digest.hexdigest()


def _copy_images(source_images: list[Path], image_dir: Path) -> None:
    image_dir.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(source_images, start=1):
        destination = image_dir / f"slide-{index:04d}.png"
        with Image.open(source) as image:
            image.convert("RGB").save(destination, format="PNG", optimize=True)


def _render_pdf(source: Path, image_dir: Path) -> list[str]:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise SlideImportError(
            "Para importar PDF instala las dependencias del proyecto: pip install -r requirements.txt"
        ) from exc

    image_dir.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(str(source))
    texts: list[str] = []
    if len(document) == 0:
        raise SlideImportError("El PDF no contiene páginas")
    for index in range(len(document)):
        page = document[index]
        bitmap = page.render(scale=2.0, rev_byteorder=True)
        image = bitmap.to_pil().convert("RGB")
        image.save(image_dir / f"slide-{index + 1:04d}.png", format="PNG", optimize=True)
        try:
            texts.append(page.get_textpage().get_text_range().strip())
        except Exception:
            texts.append("")
    return texts


def _powerpoint_export(source: Path, image_dir: Path) -> list[Path]:
    if sys.platform != "win32":
        raise SlideImportError("La exportación directa con PowerPoint solo está disponible en Windows")
    try:
        from win32com.client import dynamic
    except ImportError as exc:
        raise SlideImportError(
            "No se encontró pywin32. Instala las dependencias de diapositivas o usa un PDF."
        ) from exc

    image_dir.mkdir(parents=True, exist_ok=True)
    application = None
    presentation = None
    try:
        application = dynamic.Dispatch("PowerPoint.Application")
        presentation = application.Presentations.Open(str(source), True, False, False)
        presentation.Export(str(image_dir), "PNG", 1920, 1080)
    except Exception as exc:
        raise SlideImportError(f"PowerPoint no pudo exportar {source.name}: {exc}") from exc
    finally:
        if presentation is not None:
            try:
                presentation.Close()
            except Exception:
                pass
        if application is not None:
            try:
                application.Quit()
            except Exception:
                pass
    images = _image_paths(image_dir)
    if not images:
        raise SlideImportError("PowerPoint no generó imágenes de diapositivas")
    return images


def _find_soffice() -> str | None:
    configured = shutil.which("soffice") or shutil.which("libreoffice")
    if configured:
        return configured
    if sys.platform == "win32":
        for candidate in (
            Path("C:/Program Files/LibreOffice/program/soffice.exe"),
            Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
        ):
            if candidate.is_file():
                return str(candidate)
    return None


def _libreoffice_export(source: Path, work_dir: Path, image_dir: Path) -> list[str]:
    soffice = _find_soffice()
    if not soffice:
        raise SlideImportError(
            "No se encontró PowerPoint utilizable ni LibreOffice. Instala LibreOffice o importa un PDF."
        )
    pdf_dir = work_dir / "pdf"
    profile_dir = work_dir / "libreoffice-profile"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)
    command = [
        soffice,
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(pdf_dir),
        str(source),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    except subprocess.TimeoutExpired as exc:
        raise SlideImportError("LibreOffice tardó más de dos minutos al convertir las diapositivas") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise SlideImportError(f"LibreOffice no pudo convertir {source.name}: {detail or 'sin detalle'}")
    pdf_path = pdf_dir / f"{source.stem}.pdf"
    if not pdf_path.is_file():
        candidates = sorted(pdf_dir.glob("*.pdf"), key=_natural_key)
        if len(candidates) != 1:
            raise SlideImportError("LibreOffice no produjo un PDF identificable")
        pdf_path = candidates[0]
    return _render_pdf(pdf_path, image_dir)


def _extract_pptx_text(source: Path, expected_pages: int) -> list[str]:
    """Best-effort text metadata. Rendering never depends on this optional step."""
    try:
        from pptx import Presentation
    except ImportError:
        return [""] * expected_pages
    try:
        presentation = Presentation(str(source))
        result: list[str] = []
        for slide in presentation.slides:
            pieces = [shape.text.strip() for shape in slide.shapes if getattr(shape, "has_text_frame", False) and shape.text.strip()]
            result.append("\n".join(pieces))
        return (result + [""] * expected_pages)[:expected_pages]
    except Exception:
        return [""] * expected_pages


def _keywords(text: str) -> set[str]:
    """Small deterministic tokenizer used for explainable timing proposals."""
    return {
        token.casefold()
        for token in re.findall(r"[\wáéíóúüñ]{3,}", text, flags=re.IGNORECASE)
        if token.casefold() not in {"para", "como", "este", "esta", "sobre", "entre", "desde", "también", "porque"}
    }


def _speaker_crop(frame, config: Mapping[str, Any]) -> tuple[float, float, float, float, bool]:
    """Return a safe normalised speaker crop from the chroma alpha mask.

    Green-screen alpha is more dependable in CREAcut recordings than a generic
    person detector and works without downloading a model.  The boolean tells
    the caller whether a real silhouette was found; a conservative centre crop
    remains available for recordings without usable chroma.
    """
    import cv2
    import numpy as np

    try:
        from .chroma import make_alpha_extractor

        alpha = make_alpha_extractor(dict(config))(frame)[..., 3]
        mask = (alpha > 64).astype(np.uint8)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            raise ValueError("sin contornos")
        contour = max(contours, key=cv2.contourArea)
        x, y, width, height = cv2.boundingRect(contour)
        frame_h, frame_w = frame.shape[:2]
        if width * height < frame_w * frame_h * 0.015 or width * height > frame_w * frame_h * 0.92:
            raise ValueError("contorno no fiable")
        margin_x = max(4, round(width * 0.10))
        margin_y = max(4, round(height * 0.06))
        left = max(0, x - margin_x)
        top = max(0, y - margin_y)
        right = min(frame_w, x + width + margin_x)
        bottom = min(frame_h, y + height + margin_y)
        return left / frame_w, top / frame_h, (right - left) / frame_w, (bottom - top) / frame_h, True
    except Exception:
        return 0.15, 0.03, 0.70, 0.94, False


def _recommend_layout(image_path: Path, frame, config: Mapping[str, Any]) -> dict[str, float]:
    """Choose the least busy lower region of this particular slide.

    Canny edge density is a useful content-agnostic proxy for text, charts and
    photographs.  Evaluating left/right and three speaker sizes per slide
    yields variable positions and proportions instead of a global preset.
    """
    import cv2
    import numpy as np

    with Image.open(image_path) as source:
        slide = np.array(source.convert("RGB"))
    height_px, width_px = slide.shape[:2]
    edges = cv2.Canny(cv2.cvtColor(slide, cv2.COLOR_RGB2GRAY), 72, 164)
    integral = cv2.integral(edges.astype(np.float32) / 255.0)
    crop_x, crop_y, crop_width, crop_height, detected = _speaker_crop(frame, config)
    crop_aspect = (crop_width * frame.shape[1]) / max(1.0, crop_height * frame.shape[0])

    def density(x: float, y: float, width: float, height: float) -> float:
        left = max(0, min(width_px - 1, round(x * width_px)))
        top = max(0, min(height_px - 1, round(y * height_px)))
        right = max(left + 1, min(width_px, round((x + width) * width_px)))
        bottom = max(top + 1, min(height_px, round((y + height) * height_px)))
        total = integral[bottom, right] - integral[top, right] - integral[bottom, left] + integral[top, left]
        return float(total / max(1, (right - left) * (bottom - top)))

    candidates: list[tuple[float, float, float, float, float]] = []
    for height_fraction in (0.46, 0.58, 0.70):
        width_fraction = min(0.44, max(0.18, height_fraction * crop_aspect * height_px / width_px))
        y = 0.97 - height_fraction
        for x in (0.03, 0.97 - width_fraction):
            # Prefer the less occupied side, but retain a small preference for
            # a larger presenter when both areas are equally empty.
            score = density(x, y, width_fraction, height_fraction) - height_fraction * 0.035
            candidates.append((score, x, y, width_fraction, height_fraction))
    _, x, y, width, height_fraction = min(candidates, key=lambda item: item[0])
    return {
        "x": round(x, 4), "y": round(y, 4), "speaker_width": round(width, 4), "height_fraction": round(height_fraction, 4),
        "crop_x": round(crop_x, 4), "crop_y": round(crop_y, 4), "crop_width": round(crop_width, 4), "crop_height": round(crop_height, 4),
        "detected": 1.0 if detected else 0.0,
    }


def recommend_slide_pages(
    state: SlideTrackState,
    *,
    project_path: str | Path,
    source_video: str | Path,
    transcript_segments: list[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> SlideTrackState:
    """Propose source-time cues and a variable speaker layout for each page.

    This is intentionally deterministic and local: text overlap chooses the
    most relevant transcript segment, chronological fallback fills sparse
    slides, and OpenCV analyses each rasterised slide independently.
    """
    import cv2

    state.validate()
    transcript = [
        item for item in transcript_segments
        if isinstance(item, Mapping) and isinstance(item.get("start"), (int, float)) and isinstance(item.get("end"), (int, float))
    ]
    if not transcript:
        raise SlideImportError("No hay transcripción con tiempos para recomendar diapositivas")
    capture = cv2.VideoCapture(str(Path(source_video).expanduser().resolve()))
    if not capture.isOpened():
        raise SlideImportError("OpenCV no pudo abrir el video fuente para analizar al presentador")
    try:
        proposals: list[tuple[float, float, str, str, dict[str, float]]] = []
        floor = 0
        for page_index, page in enumerate(state.pages):
            terms = _keywords(page.text)
            ranked: list[tuple[float, int]] = []
            for index in range(floor, len(transcript)):
                spoken = _keywords(str(transcript[index].get("text", "")))
                overlap = len(terms & spoken)
                score = overlap / max(1, len(terms)) if terms else 0.0
                ranked.append((score, index))
            score, selected_index = max(ranked, default=(0.0, min(len(transcript) - 1, page_index)))
            if score < 0.08:
                selected_index = min(len(transcript) - 1, max(floor, round(page_index * len(transcript) / max(1, len(state.pages)))))
                score = 0.18
                mode = "ordered-fallback"
                reason = (
                    "No se encontró suficiente coincidencia entre el texto de esta "
                    "diapositiva y la transcripción. El intervalo fue recomendado "
                    "utilizando el orden de las diapositivas y la duración del video."
                )
            else:
                mode = "lexical-match"
                reason = f"Confianza {'alta' if score >= 0.35 else 'media' if score >= 0.18 else 'baja'} · coincidencia semántica ({round(score * 100)} %)"
            floor = min(len(transcript) - 1, selected_index + 1)
            start = float(transcript[selected_index]["start"])
            capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start) * 1000.0)
            ok, bgr = capture.read()
            if not ok:
                raise SlideImportError(f"OpenCV no pudo leer el fotograma en {start:.2f} s")
            frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            image_path = resolve_project_path(page.image_path, project_path)
            proposals.append((start, score, mode, reason, _recommend_layout(image_path, frame, config)))
    finally:
        capture.release()
    pages: list[SlidePage] = []
    for index, page in enumerate(state.pages):
        start, score, mode, reason, layout = proposals[index]
        next_start = proposals[index + 1][0] if index + 1 < len(proposals) else float(transcript[-1]["end"])
        recommended_end = max(start + 1.5, next_start - 0.08)
        if page.enabled:
            # Re-analysis may improve the explanation, but never overwrites a
            # user-approved timing or manual position.
            pages.append(replace(
                page,
                recommended_start_s=round(start, 3),
                recommended_end_s=round(recommended_end, 3),
                recommendation_score=round(score, 3),
                recommendation_mode=mode,
                recommendation_reason=reason,
            ))
            continue
        pages.append(replace(
            page,
            recommended_start_s=round(start, 3),
            recommended_end_s=round(recommended_end, 3),
            recommendation_score=round(score, 3),
            recommendation_mode=mode,
            recommendation_reason=reason + ("; silueta de chroma detectada" if layout.pop("detected") else "; recorte conservador"),
            start_s=round(start, 3),
            end_s=round(recommended_end, 3),
            **layout,
        ))
    return state.with_pages(pages)


def accept_slide_recommendations(state: SlideTrackState) -> SlideTrackState:
    """Enable every page that has a valid proposal; explicit user action only."""
    pages = [
        replace(page, enabled=True)
        if page.recommended_start_s is not None and page.recommended_end_s is not None
        else page
        for page in state.pages
    ]
    return state.with_pages(pages)


def _clamp_fraction(value: Any, default: float, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(minimum, min(maximum, float(value)))


def _sanitize_page_geometry(page: SlidePage) -> SlidePage:
    """Clamp placement/crop fractions back into a valid, self-consistent range.

    `SlideTrackState.validate()` re-checks *every* page on *every* write, so
    a single page left outside range (stray float drift from UI drag math, an
    old bug, a hand-edited project file) would otherwise permanently block
    editing any slide, not just the corrupted one. Called on every page in
    `update_slide_page` so a corrupt deck self-heals the moment the user
    makes their next edit, instead of getting permanently stuck.

    x/y intentionally allow -1..1 (not just 0..1) -- see the matching comment
    in `SlidePage.validate()`.
    """
    x = _clamp_fraction(page.x, 0.62, minimum=-1.0)
    y = _clamp_fraction(page.y, 0.22, minimum=-1.0)
    speaker_width = _clamp_fraction(page.speaker_width, 0.32, minimum=0.02)
    height_fraction = _clamp_fraction(page.height_fraction, 0.70, minimum=0.02)
    crop_x = _clamp_fraction(page.crop_x, 0.15)
    crop_y = _clamp_fraction(page.crop_y, 0.03)
    crop_width = _clamp_fraction(page.crop_width, 0.70, minimum=0.02)
    crop_height = _clamp_fraction(page.crop_height, 0.94, minimum=0.02)
    if crop_x + crop_width > 1.0:
        crop_x = max(0.0, 1.0 - crop_width)
    if crop_y + crop_height > 1.0:
        crop_y = max(0.0, 1.0 - crop_height)
    return replace(
        page,
        x=x, y=y, speaker_width=speaker_width, height_fraction=height_fraction,
        crop_x=crop_x, crop_y=crop_y, crop_width=crop_width, crop_height=crop_height,
    )


def update_slide_page(state: SlideTrackState, page_id: str, patch: Mapping[str, Any]) -> SlideTrackState:
    """Apply a deliberately small, validated manual cue/layout edit."""
    allowed = {"start_s", "end_s", "enabled", "x", "y", "speaker_width", "height_fraction"}
    unknown = set(patch) - allowed
    if unknown:
        raise SlidesStateError(f"slide update has unsupported fields: {', '.join(sorted(unknown))}")
    pages: list[SlidePage] = []
    found = False
    for page in state.pages:
        if page.id != page_id:
            pages.append(_sanitize_page_geometry(page))
            continue
        found = True
        values = dict(patch)
        if values.get("enabled") is True:
            values.setdefault("start_s", page.start_s if page.start_s is not None else page.recommended_start_s)
            values.setdefault("end_s", page.end_s if page.end_s is not None else page.recommended_end_s)
        pages.append(_sanitize_page_geometry(replace(page, **values)))
    if not found:
        raise SlidesStateError(f"No existe la diapositiva {page_id}")
    selected = next(page for page in pages if page.id == page_id)
    selected.validate()
    if ({"start_s", "end_s"} & patch.keys() or patch.get("enabled") is True) and selected.start_s is not None and selected.end_s is not None:
        adjusted: list[SlidePage] = []
        for page in pages:
            if page.id == page_id or page.start_s is None or page.end_s is None or page.end_s <= selected.start_s or page.start_s >= selected.end_s:
                adjusted.append(page)
                continue
            left = selected.start_s - page.start_s
            right = page.end_s - selected.end_s
            # A page has one cue; retain its larger remaining side. Fully
            # covered pages stay in the deck, unplaced, and can be undone.
            if max(left, right) < 0.001:
                adjusted.append(replace(page, start_s=None, end_s=None, enabled=False))
            elif left >= right:
                adjusted.append(replace(page, end_s=selected.start_s))
            else:
                adjusted.append(replace(page, start_s=selected.end_s))
        pages = adjusted
    return state.with_pages(pages)


def _build_state(
    *,
    source: Path,
    source_sha256: str,
    source_kind: str,
    renderer: str,
    project_path: Path,
    asset_root: Path,
    images: list[Path],
    texts: list[str],
) -> SlideTrackState:
    project_dir = project_path.parent
    thumbnails_dir = asset_root / "thumbnails"
    thumbnails_dir.mkdir(parents=True, exist_ok=True)
    pages: list[SlidePage] = []
    for index, image_path in enumerate(images):
        thumbnail = thumbnails_dir / f"slide-{index + 1:04d}.png"
        with Image.open(image_path) as image:
            preview = image.convert("RGB")
            preview.thumbnail((480, 270), Image.Resampling.LANCZOS)
            preview.save(thumbnail, format="PNG", optimize=True)
        with Image.open(image_path) as image:
            width, height = image.size
        pages.append(
            SlidePage(
                id=f"slide-{index + 1}",
                index=index,
                image_path=_relative_to_project(image_path, project_dir),
                thumbnail_path=_relative_to_project(thumbnail, project_dir),
                sha256=_sha256_file(image_path),
                width=width,
                height=height,
                text=texts[index] if index < len(texts) else "",
            )
        )
    state = SlideTrackState(
        deck=SlideDeck(
            source_path=_relative_to_project(source, project_dir),
            source_sha256=source_sha256,
            source_kind=source_kind,
            renderer=renderer,
            asset_root=_relative_to_project(asset_root, project_dir),
            imported_at_utc=datetime.now(timezone.utc).isoformat(),
        ),
        pages=tuple(pages),
    )
    state.validate()
    return state


def import_slide_source(source_path: str | Path, project_path: str | Path) -> SlideTrackState:
    """Import slides into project-owned PNG assets without modifying the source."""
    source = Path(source_path).expanduser().resolve()
    project = Path(project_path).expanduser().resolve()
    if not project.is_file():
        raise SlideImportError(f"No se encontró el proyecto CREAcut: {project}")
    if not source.exists():
        raise SlideImportError(f"No se encontró la fuente de diapositivas: {source}")

    if source.is_dir():
        source_kind = "images"
        source_images = _image_paths(source)
        if not source_images:
            raise SlideImportError("La carpeta no contiene imágenes compatibles")
        source_sha256 = _directory_digest(source, source_images)
    elif source.suffix.casefold() == ".pdf":
        source_kind = "pdf"
        source_images = []
        source_sha256 = _sha256_file(source)
    elif source.suffix.casefold() == ".pptx":
        source_kind = "pptx"
        source_images = []
        source_sha256 = _sha256_file(source)
    else:
        raise SlideImportError("Selecciona un archivo PPTX, un PDF o una carpeta de imágenes")

    # Every import gets its own immutable render directory.  This avoids a
    # partial PowerPoint export or a changed page count mixing with PNGs from
    # an older import of the same source; the originals and previous imports
    # are never deleted as a side effect of importing.
    import_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    asset_root = _asset_root(project, source_sha256) / "renders" / import_id
    image_dir = asset_root / "images"
    if source_kind == "images":
        _copy_images(source_images, image_dir)
        images = _image_paths(image_dir)
        texts = [""] * len(images)
        renderer = "image-copy"
    elif source_kind == "pdf":
        texts = _render_pdf(source, image_dir)
        images = _image_paths(image_dir)
        renderer = "pypdfium2"
    else:
        try:
            images = _powerpoint_export(source, image_dir)
            texts = _extract_pptx_text(source, len(images))
            renderer = "powerpoint"
        except SlideImportError as powerpoint_error:
            # LibreOffice is the portable fallback.  Preserve the PowerPoint
            # reason if the fallback is unavailable too.
            try:
                texts = _libreoffice_export(source, asset_root, image_dir)
                images = _image_paths(image_dir)
                renderer = "libreoffice+pypdfium2"
            except SlideImportError as libreoffice_error:
                raise SlideImportError(f"{powerpoint_error} {libreoffice_error}") from libreoffice_error

    if not images:
        raise SlideImportError("No se generaron imágenes de diapositivas")
    return _build_state(
        source=source,
        source_sha256=source_sha256,
        source_kind=source_kind,
        renderer=renderer,
        project_path=project,
        asset_root=asset_root,
        images=images,
        texts=texts,
    )
