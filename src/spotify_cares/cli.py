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
        "--acknowledge-prior-version-pilot", action="store_true",
        help="explicitly accept a complete older pilot without refreshing any label versions",
    )
    freeze_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"configuration file (default: {DEFAULT_CONFIG})",
    )
    groq_parser = commands.add_parser("check-groq", help="check authenticated model listing; no customer messages")
    groq_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    groq_parser.add_argument("--model")
    for command in ("machine-annotate", "validate-machine-annotations", "combine-machine-annotations"):
        machine_parser = commands.add_parser(command, help="frozen-policy machine labels, never golden")
        machine_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        machine_parser.add_argument("--queue", choices=("training", "development"), required=True)
        machine_parser.add_argument("--model", help="override annotation.machine_model from project configuration")
        machine_parser.add_argument("--provider", choices=("gemini", "groq"), help="override annotation.machine_provider")
        machine_parser.add_argument("--fallback-provider", choices=("gemini", "groq"), help="fallback provider if primary fails")
        machine_parser.add_argument("--fallback-model", help="override model for fallback provider")
        machine_parser.add_argument("--prompt", type=Path, help="override the configured provider prompt")
        if command == "machine-annotate":
            machine_parser.add_argument("--selection", type=Path, help="pinned queue/run/example IDs; resumes cannot extend this selection")
            machine_parser.add_argument("--limit", type=int, help="maximum attempts this invocation; rerun to resume")
            machine_parser.add_argument("--retry-unknown-quota", action="store_true",
                                        help="explicitly retry a saved ambiguous 429 after checking quota; no automatic unknown-limit retries")
    for name in ("baseline-demo", "baseline-inspect"):
        baseline_parser = commands.add_parser(name, help="training-only baselines; no evaluation")
        baseline_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        baseline_parser.add_argument("--settings", type=Path, default=Path("configs/baselines.yaml"))
        if name == "baseline-demo":
            baseline_parser.add_argument("--message", required=True)
            baseline_parser.add_argument("--context", action="append", default=[])
            baseline_parser.add_argument("--baseline", choices=("trivial", "tfidf"), default="tfidf")
            baseline_parser.add_argument("--output", type=Path, help="new local JSONL file under artifacts; never overwrite")
    agent_parser = commands.add_parser("agent-demo", help="provisional semantic agent; sending disabled")
    agent_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    agent_parser.add_argument("--baselines", type=Path, default=Path("configs/baselines.yaml"))
    agent_parser.add_argument("--settings", type=Path, default=Path("configs/agent.yaml"))
    agent_parser.add_argument("--message", required=True)
    agent_parser.add_argument("--context", action="append", default=[])
    agent_parser.add_argument("--output", type=Path, help="new ignored artifacts JSONL; no overwrite")
    
    evaluate_parser = commands.add_parser("evaluate", help="evaluate systems against human labels")
    evaluate_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    evaluate_parser.add_argument("--baselines", type=Path, default=Path("configs/baselines.yaml"))
    evaluate_parser.add_argument("--settings", type=Path, default=Path("configs/agent.yaml"))
    evaluate_parser.add_argument("--systems", type=str, default="trivial,tfidf,agent", help="comma-separated systems to evaluate")
    evaluate_parser.add_argument("--queue", choices=("development", "golden"), default="development")
    evaluate_parser.add_argument("--live", action="store_true", help="allow live inference/API calls on cache miss")
    evaluate_parser.add_argument("--fallback-provider", choices=("gemini", "groq"), help="fallback provider for agent evaluation")
    evaluate_parser.add_argument("--fallback-model", help="fallback model for agent evaluation")
    evaluate_parser.add_argument("--golden-confirmed", action="store_true", help="explicitly unlock golden queue evaluation")
    evaluate_parser.add_argument("--output", type=Path, default=Path("artifacts/evaluation/report.json"), help="report output path")
    
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "agent-demo":
        import json
        from spotify_cares.annotation import AnnotationError
        from spotify_cares.config import load_config
        from spotify_cares.baselines import load_settings
        from spotify_cares.agent import load_agent_settings, run_agent
        try:
            config = load_config(args.config)
            if args.output and (not args.output.resolve().is_relative_to(config.artifacts.directory.resolve()) or args.output.exists()):
                raise AnnotationError("output must be a new file under ignored artifacts")
            if not args.message.strip():
                raise AnnotationError("message must not be empty")
            result = run_agent(config, load_settings(args.baselines), load_agent_settings(args.settings), args.message, args.context)
            if args.output:
                args.output.parent.mkdir(parents=True,exist_ok=True)
                with args.output.open("x",encoding="utf-8") as handle:
                    handle.write(json.dumps(result,ensure_ascii=False)+"\n")
            print(json.dumps(result,indent=2,ensure_ascii=False))
            return 1 if result["fallback"] else 0
        except (AnnotationError, ValueError, OSError) as error:
            print(f"blocked: {error}")
            return 2

    if args.command == "evaluate":
        import json
        from spotify_cares.annotation import AnnotationError
        from spotify_cares.config import load_config
        from spotify_cares.baselines import load_settings
        from spotify_cares.agent import load_agent_settings
        from spotify_cares.evaluation import run_evaluation
        try:
            config = load_config(args.config)
            systems = [s.strip() for s in args.systems.split(",") if s.strip()]
            agent_settings = load_agent_settings(args.settings)
            if args.fallback_provider:
                agent_settings.fallback_provider = args.fallback_provider
            if args.fallback_model:
                agent_settings.fallback_model = args.fallback_model
            report = run_evaluation(
                config, load_settings(args.baselines), agent_settings,
                args.queue, systems, args.live, args.golden_confirmed
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 0
        except (AnnotationError, ValueError, OSError) as error:
            print(f"blocked: {error}")
            return 2

    if args.command in ("baseline-demo", "baseline-inspect"):
        import json
        from spotify_cares.annotation import AnnotationError
        from spotify_cares.config import load_config
        from spotify_cares.baselines import load_settings, load_training, run_demo
        try:
            config, settings = load_config(args.config), load_settings(args.settings)
            if args.command == "baseline-inspect":
                result = load_training(config, settings)[3]
            else:
                if args.output and not args.output.resolve().is_relative_to(config.artifacts.directory.resolve()):
                    raise AnnotationError("demo output must stay under ignored artifacts directory")
                result = run_demo(config, settings, args.message, args.baseline, args.context)
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    with args.output.open("x", encoding="utf-8") as handle:
                        handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        except (AnnotationError, ValueError, OSError) as error:
            print(f"blocked: {error}")
            return 2

    if args.command == "check-groq":
        import json
        from spotify_cares.annotation import AnnotationError
        from spotify_cares.config import load_config
        from spotify_cares.groq_annotation import check_groq
        try:
            print(json.dumps(check_groq(load_config(args.config), args.model), indent=2))
        except AnnotationError as error:
            print(f"blocked: {error}")
            return 2
        return 0

    if args.command in ("machine-annotate", "validate-machine-annotations", "combine-machine-annotations"):
        import json
        from spotify_cares.annotation import AnnotationError
        from spotify_cares.config import load_config
        from spotify_cares.machine_annotation import machine_annotate, combined_machine_manifest

        try:
            operation = machine_annotate if args.command == "machine-annotate" else combined_machine_manifest
            options = {"limit": args.limit, "retry_unknown_quota": args.retry_unknown_quota,
                       "selection_path": args.selection,
                       "fallback_provider_name": args.fallback_provider,
                       "fallback_model": args.fallback_model} if args.command == "machine-annotate" else {}
            if args.command == "validate-machine-annotations":
                options["write"] = False
            report = operation(load_config(args.config), args.queue, model=args.model,
                               prompt_path=args.prompt, provider_name=args.provider, **options)
        except AnnotationError as error:
            print(f"blocked: {error}")
            return 2
        print(json.dumps(report, indent=2))
        return 0 if report["complete"] else 1

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
        from spotify_cares.annotation import load_guide_state, current_contract, training_pilot_status
        from spotify_cares.config import load_config

        config = load_config(args.config)
        state = load_guide_state(config)
        contract = current_contract(config)
        print(f"status: {state['status']}")
        print(f"active taxonomy version: {contract['taxonomy_version']}")
        print(f"active guide version: {contract['guide_version']}")
        print(f"active taxonomy SHA-256: {contract['taxonomy_sha256']}")
        print(f"active guide SHA-256: {contract['guide_sha256']}")
        print(f"checkpoint matches active files: {all(state.get(k) == v for k, v in contract.items())}")
        pilot = training_pilot_status(config)
        print(f"pilot: current={pilot['complete_current']}, stale={pilot['stale']}, missing={pilot['missing']}, incomplete={pilot['incomplete']}")
        return 0

    if args.command == "freeze-guide":
        from spotify_cares.annotation import freeze_guide
        from spotify_cares.config import load_config

        state = freeze_guide(
            load_config(args.config),
            annotator_id=args.annotator_id,
            confirm_taxonomy_version=args.confirm_taxonomy_version,
            confirm_guide_version=args.confirm_guide_version,
            acknowledge_prior_version_pilot=args.acknowledge_prior_version_pilot,
        )
        print(f"status: {state['status']}")
        print("development and golden annotation: unlocked")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
