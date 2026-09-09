"""Command-line entry point for reproducible project workflows."""

import argparse
from pathlib import Path
from typing import Sequence

from spotify_cares import __version__


DEFAULT_CONFIG = Path("configs/project.yaml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spotify-cares",
        description="SpotifyCares support-agent project tools.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command")

    config_parser = commands.add_parser(
        "config", help="validate and summarize the project configuration"
    )
    config_parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"configuration file (default: {DEFAULT_CONFIG})",
    )
    extract_parser = commands.add_parser(
        "extract", help="extract and reconstruct SpotifyCares conversations"
    )
    extract_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"configuration file (default: {DEFAULT_CONFIG})",
    )
    extract_parser.add_argument(
        "--chunk-size",
        type=int,
        help="CSV records per chunk (overrides project configuration)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "config":
        from spotify_cares.config import load_config

        config = load_config(args.path)
        print(f"brand: {config.project.brand}")
        print(f"dataset: {config.data.source}")
        print(f"seed: {config.project.random_seed}")
        return 0

    if args.command == "extract":
        from spotify_cares.config import load_config
        from spotify_cares.extraction import extract_spotify_conversations

        config = load_config(args.config)
        settings = config.extraction
        chunk_size = args.chunk_size or settings.chunk_size
        result = extract_spotify_conversations(
            settings.input_path,
            settings.output_dir,
            settings.temp_database,
            support_author_id=config.data.support_author_id,
            source_name=config.data.source,
            chunk_size=chunk_size,
            audit_example_count=settings.audit_example_count,
        )
        counts = result.audit["counts"]
        print(f"rows scanned: {counts['total_rows_scanned']}")
        print(f"relevant tweets: {counts['relevant_tweets']}")
        print(f"eligible examples: {counts['eligible_customer_examples']}")
        print(f"audit: {result.output_paths['audit']}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
