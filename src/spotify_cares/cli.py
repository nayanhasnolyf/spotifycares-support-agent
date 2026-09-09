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

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

