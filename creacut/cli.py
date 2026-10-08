"""Command-line interface for CREAcut."""

import argparse
import sys

from .config import load_config, resolve_config
from .pipeline import process_video, render_project


def _render_project_main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="creacut render-project",
        description="Renderiza un proyecto CREAcut aprobado sin volver a analizar Whisper.",
    )
    parser.add_argument("project", help="Ruta al archivo .creacut.json")
    parser.add_argument("--output", "-o", help="MP4 final de salida")
    parser.add_argument("--config", "-c", dest="config_path", help="Reemplaza la configuración guardada")
    parser.add_argument("--dry-run", action="store_true", help="Muestra los rangos efectivos sin renderizar")
    parser.add_argument("--allow-source-mismatch", action="store_true", help="Permite renderizar aunque tamaño/fecha de la fuente difieran")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)
    config = load_config(args.config_path) if args.config_path else None
    try:
        result = render_project(
            args.project,
            output=args.output,
            config=config,
            dry_run=args.dry_run,
            verbose=args.verbose,
            allow_source_mismatch=args.allow_source_mismatch,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.dry_run and not args.verbose:
        print(f"[render-project dry-run] {len(result)} rango(s) efectivos")


def main() -> None:
    # Keep the historical ``creacut <video>`` interface exactly as it was;
    # project rendering is an explicit command so the two workflows never
    # compete for positional arguments.
    if len(sys.argv) > 1 and sys.argv[1] == "render-project":
        _render_project_main(sys.argv[2:])
        return
    p = argparse.ArgumentParser(
        description="CREAcut — Automated video editing pipeline.",
        epilog="Provide a raw video and its script to produce an edited final version.",
    )
    p.add_argument("video_path", help="Path to the raw .mp4 recording")
    p.add_argument("--script", "-s", help="Path to the script/guion file (.md)")
    p.add_argument("--output", "-o", help="Output file path")
    p.add_argument("--config", "-c", dest="config_path",
                   help="Path to creacut.yml config file")
    p.add_argument("--dry-run", action="store_true",
                   help="Show alignment without exporting video")
    p.add_argument("--no-chroma", action="store_true",
                   help="Skip green screen replacement")
    p.add_argument("--no-overlays", action="store_true",
                   help="Skip all overlay composition")
    p.add_argument("--no-bookends", action="store_true",
                   help="Skip intro/outro bookends")
    p.add_argument("--no-normalize", action="store_true",
                   help="Skip EBU R128 audio normalization")
    p.add_argument("--chroma-color", nargs=3, type=int,
                   metavar=("R", "G", "B"),
                   help="Chroma key color (default: 24 238 28)")
    p.add_argument("--bg-image", metavar="PATH",
                   help="Background image for chroma replacement")
    p.add_argument("--skin-correction", action="store_true",
                   help="Apply skin tone color correction")
    p.add_argument("--equation-specs", metavar="PATH",
                   help="Path to equation overlay specs JSON")
    p.add_argument("--vocab", metavar="PATH",
                   help="Path to vocabulary terms JSON")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--json", dest="json_output",
                   help="Export alignment data as JSON")
    p.add_argument("--project-output", metavar="PATH",
                   help="Save the editable CREAcut project as JSON")
    p.add_argument("--project-only", action="store_true",
                   help="Generate and save an editable project without rendering video")

    args = p.parse_args()

    if args.project_only and not args.project_output:
        p.error("--project-only requires --project-output")

    # Load config
    config = load_config(args.config_path)

    # CLI overrides
    cli_overrides = {
        "no_chroma": args.no_chroma or None,
        "chroma_color": args.chroma_color,
        "bg_image": args.bg_image,
        "skin_correction": args.skin_correction or None,
        "no_overlays": args.no_overlays or None,
        "no_bookends": args.no_bookends or None,
        "no_normalize": args.no_normalize or None,
    }
    # Handle vocab and equation-specs CLI flags
    if args.vocab:
        config["overlays"]["terms"]["vocab_file"] = args.vocab
    if args.equation_specs:
        config["overlays"]["equations"]["specs_file"] = args.equation_specs
        config["overlays"]["equations"]["enabled"] = True

    config = resolve_config(cli_overrides, config)

    process_video(
        video_path=args.video_path,
        script=args.script,
        output=args.output,
        config=config,
        dry_run=args.dry_run,
        verbose=args.verbose,
        json_output=args.json_output,
        project_output=args.project_output,
        project_only=args.project_only,
    )
