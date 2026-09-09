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
    prepare_annotations_parser = commands.add_parser(
        "prepare-annotations", help="prepare deterministic local human-annotation queues"
    )
    prepare_annotations_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"configuration file (default: {DEFAULT_CONFIG})",
    )
    validate_annotations_parser = commands.add_parser(
        "validate-annotations", help="validate queues and locally saved human annotations"
    )
    validate_annotations_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"configuration file (default: {DEFAULT_CONFIG})",
    )
    extend_training_parser = commands.add_parser(
        "extend-training-queue",
        help="append a reproducible training-only annotation batch",
    )
    extend_training_parser.add_argument("--name", required=True, dest="batch_name")
    extend_training_parser.add_argument("--size", required=True, type=int)
    extend_training_parser.add_argument(
        "--coverage-bucket",
        help="optional observable proxy bucket; this is not an intent label",
    )
    extend_training_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"configuration file (default: {DEFAULT_CONFIG})",
    )
    status_parser = commands.add_parser(
        "guide-status", help="show the local annotation-guide checkpoint state"
    )
    status_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"configuration file (default: {DEFAULT_CONFIG})",
    )
    freeze_parser = commands.add_parser(
        "freeze-guide", help="freeze the reviewed guide and unlock development/golden"
    )
    freeze_parser.add_argument("--annotator-id", required=True)
    freeze_parser.add_argument("--confirm-taxonomy-version", required=True)
    freeze_parser.add_argument("--confirm-guide-version", required=True)
    freeze_parser.add_argument(
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

    if args.command == "prepare-annotations":
        from spotify_cares.annotation import prepare_annotation_queues
        from spotify_cares.config import load_config

        config = load_config(args.config)
        manifest = prepare_annotation_queues(config)
        sizes = manifest["queue_validation"]["queue_sizes"]
        print(f"training queue: {sizes['training']}")
        print(f"development queue: {sizes['development']}")
        print(f"golden queue: {sizes['golden']}")
        print(f"guide state: {manifest['status']['guide']}")
        print(f"manifest: {config.annotation.output_dir / 'annotation_manifest.json'}")
        return 0

    if args.command == "validate-annotations":
        from spotify_cares.annotation import validate_annotation_outputs
        from spotify_cares.config import load_config

        config = load_config(args.config)
        report = validate_annotation_outputs(config)
        print(f"tooling: {report['tooling']}")
        print(f"queues: {report['queues']}")
        print(f"guide: {report['guide']}")
        for name, counts in report["annotations"].items():
            print(
                f"{name}: complete={counts['complete']}/{counts['expected']}, "
                f"saved={counts['judgment_saved']}, skipped={counts['skipped_incomplete']}, "
                f"missing={counts['missing']}, stale={counts['stale_requires_human_review']}"
            )
        return 0

    if args.command == "extend-training-queue":
        from spotify_cares.annotation import extend_training_queue
        from spotify_cares.config import load_config

        result = extend_training_queue(
            load_config(args.config),
            batch_name=args.batch_name,
            size=args.size,
            coverage_bucket=args.coverage_bucket,
        )
        print(f"training batch: {result['batch_name']}")
        print(f"examples appended: {result['size']}")
        print(
            f"queue positions: {result['first_queue_position']}-"
            f"{result['last_queue_position']}"
        )
        return 0

    if args.command == "guide-status":
        from spotify_cares.annotation import load_guide_state
        from spotify_cares.config import load_config

        state = load_guide_state(load_config(args.config))
        print(f"status: {state['status']}")
        print(f"taxonomy version: {state['taxonomy_version']}")
        print(f"guide version: {state['guide_version']}")
        return 0

    if args.command == "freeze-guide":
        from spotify_cares.annotation import freeze_guide
        from spotify_cares.config import load_config

        state = freeze_guide(
            load_config(args.config),
            annotator_id=args.annotator_id,
            confirm_taxonomy_version=args.confirm_taxonomy_version,
            confirm_guide_version=args.confirm_guide_version,
        )
        print(f"status: {state['status']}")
        print("development and golden annotation: unlocked")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
