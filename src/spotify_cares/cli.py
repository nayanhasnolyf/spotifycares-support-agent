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
    preprocess_parser = commands.add_parser(
        "preprocess", help="redact, group, and split extracted examples"
    )
    preprocess_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"configuration file (default: {DEFAULT_CONFIG})",
    )
    validate_parser = commands.add_parser(
        "validate-splits", help="validate saved pools for leakage"
    )
    validate_parser.add_argument(
        "--config",
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

    if args.command == "preprocess":
        from spotify_cares.config import load_config
        from spotify_cares.preprocessing import PREPROCESSING_VERSION, preprocess_and_split

        config = load_config(args.config)
        settings = config.preprocessing
        if settings.version != PREPROCESSING_VERSION:
            parser.error(
                f"configured preprocessing version {settings.version!r} does not match "
                f"implementation {PREPROCESSING_VERSION!r}"
            )
        result = preprocess_and_split(
            settings.examples_path,
            settings.relevant_tweets_path,
            settings.conversations_path,
            settings.output_dir,
            support_author_id=config.data.support_author_id,
            seed=config.project.random_seed,
            train_fraction=settings.train_fraction,
            development_fraction=settings.development_fraction,
            test_fraction=settings.test_fraction,
            near_duplicate_threshold=settings.near_duplicate_threshold,
            near_duplicate_min_chars=settings.near_duplicate_min_chars,
            shingle_size=settings.shingle_size,
            candidate_keys=settings.candidate_keys,
            max_block_size=settings.max_block_size,
            discovery_sample_size=settings.discovery_sample_size,
            safe_domains=settings.safe_url_domains,
        )
        counts = result.manifest["counts"]
        print(f"train: {counts['train']}")
        print(f"development: {counts['development']}")
        print(f"test candidates: {counts['test_candidate']}")
        print(f"quarantined: {counts['quarantined']}")
        print(f"manifest: {result.output_paths['manifest']}")
        return 0

    if args.command == "validate-splits":
        from spotify_cares.config import load_config
        from spotify_cares.preprocessing import validate_split_outputs

        config = load_config(args.config)
        checks = validate_split_outputs(
            config.preprocessing.output_dir,
            config.preprocessing.relevant_tweets_path,
        )
        print(f"leakage checks passed: {len(checks)}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
