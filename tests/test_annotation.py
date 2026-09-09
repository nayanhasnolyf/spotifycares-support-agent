"""Synthetic-fixture tests for the local human-annotation workflow."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from spotify_cares.annotation import (
    AnnotationError,
    AnnotationStore,
    annotation_paths,
    current_contract,
    freeze_guide,
    get_annotation_view,
    reveal_reference,
    sample_golden_queue,
    sample_uniform_queue,
    save_expected_guidance,
    save_initial_judgment,
    sha256_file,
    skip_example,
    validate_annotation_outputs,
    validate_queue_membership,
)
from spotify_cares.config import AppConfig, load_config
from spotify_cares.preprocessing import OUTPUT_FILES


def _synthetic_pool(prefix: str, count: int) -> pd.DataFrame:
    messages = (
        "help",
        "Someone hacked my account?? What should I do?",
        "I want a refund for a double charge",
        "Why does playback stop? Can I fix it?",
        "The synthetic app crashes on a test device",
    )
    return pd.DataFrame(
        [
            {
                "example_id": f"{prefix}_{index}",
                "combined_group_id": f"group_{prefix}_{index}",
                "thread_id": f"thread_{prefix}_{index}",
                "customer_text_redacted": messages[index % len(messages)],
                "context_tweet_ids": [] if index % 2 == 0 else [f"context_{prefix}_{index}"],
                "context_author_ids": [] if index % 2 == 0 else ["SyntheticCustomer"],
                "context_inbound": [] if index % 2 == 0 else [True],
                "context_created_at_utc": [] if index % 2 == 0 else ["2020-01-01T00:00:00Z"],
                "context_texts_redacted": [] if index % 2 == 0 else ["Synthetic earlier message"],
                "quality_flags": ["synthetic_fixture"] if index == 0 else [],
            }
            for index in range(count)
        ]
    )


def _queue(name: str, pool: pd.DataFrame, strata: list[str] | None = None) -> pd.DataFrame:
    selected = pool.reset_index(drop=True)
    strata = strata or ["random"] * len(selected)
    return pd.DataFrame(
        {
            "queue_name": [name] * len(selected),
            "queue_position": range(1, len(selected) + 1),
            "example_id": selected["example_id"],
            "thread_id": selected["thread_id"],
            "combined_group_id": selected["combined_group_id"],
            "sampling_stratum": strata,
            "selection_rule": ["synthetic fixture"] * len(selected),
            "candidate_pool_sha256": ["0" * 64] * len(selected),
            "seed": [42] * len(selected),
        }
    )


def _write_pool_and_references(split_dir: Path, split: str, pool: pd.DataFrame) -> None:
    pool.to_parquet(split_dir / OUTPUT_FILES[f"{split}_inputs"], index=False)
    references = pd.DataFrame(
        {
            "example_id": pool["example_id"],
            "reference_reply_ids": [[f"reply_{value}"] for value in pool["example_id"]],
            "reference_reply_texts_redacted": [["Synthetic historical reply"] for _ in range(len(pool))],
            "reference_status": ["available"] * len(pool),
        }
    )
    references.to_parquet(split_dir / OUTPUT_FILES[f"{split}_references"], index=False)


@pytest.fixture()
def annotation_config(tmp_path: Path) -> AppConfig:
    """Build isolated files containing only clearly synthetic examples."""

    base = load_config(Path("configs/project.yaml"))
    taxonomy_path = tmp_path / "taxonomy.yaml"
    guide_path = tmp_path / "guide.md"
    taxonomy_path.write_text(Path("configs/taxonomy.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    guide_path.write_text("# Synthetic test guide\n", encoding="utf-8")
    split_dir = tmp_path / "splits"
    output_dir = tmp_path / "annotation"
    split_dir.mkdir()

    train = _synthetic_pool("train", 2)
    development = _synthetic_pool("development", 1)
    golden = _synthetic_pool("golden", 2)
    _write_pool_and_references(split_dir, "train", train)
    _write_pool_and_references(split_dir, "development", development)
    _write_pool_and_references(split_dir, "test_candidate", golden)

    settings = base.annotation.model_copy(
        update={
            "taxonomy_path": taxonomy_path,
            "guide_path": guide_path,
            "split_dir": split_dir,
            "output_dir": output_dir,
            "training_queue_size": 2,
            "development_queue_size": 1,
            "golden_random_size": 1,
            "golden_challenge_size": 1,
            "training_pilot_size": 1,
        }
    )
    config = base.model_copy(update={"annotation": settings})
    paths = annotation_paths(output_dir)
    paths.queues.mkdir(parents=True)
    paths.labels.mkdir(parents=True)
    paths.audit.mkdir(parents=True)
    queue_specs = (
        ("training", train, "train", None),
        ("development", development, "development", None),
        ("golden", golden, "test_candidate", ["random", "challenge:very_short_message"]),
    )
    for queue_name, pool, split, strata in queue_specs:
        queue = _queue(queue_name, pool, strata)
        queue["candidate_pool_sha256"] = sha256_file(
            split_dir / OUTPUT_FILES[f"{split}_inputs"]
        )
        queue.to_parquet(paths.queues / f"{queue_name}.parquet", index=False)
    paths.state.parent.mkdir(parents=True)
    paths.state.write_text(
        json.dumps({"status": "proposed", **current_contract(config)}), encoding="utf-8"
    )
    paths.manifest.write_text("{}", encoding="utf-8")
    return config


def _save_valid(config: AppConfig, example_id: str = "train_0"):
    return save_initial_judgment(
        config,
        queue_name="training",
        example_id=example_id,
        primary_intent="other_or_unclear",
        should_escalate="no",
        escalation_reason_code=None,
        escalation_explanation=None,
        risk_flags=(),
        ambiguity="clear",
        annotation_notes="Synthetic fixture judgment",
        annotator_id="tester",
    )


def test_save_and_resume_without_data_loss(annotation_config: AppConfig):
    saved = _save_valid(annotation_config)
    resumed = AnnotationStore(annotation_config, "training").load()["train_0"]
    assert resumed == saved
    assert resumed.status == "judgment_saved"


def test_edit_after_reveal_preserves_audit_trail(annotation_config: AppConfig):
    _save_valid(annotation_config)
    reveal_reference(annotation_config, "training", "train_0")
    save_initial_judgment(
        annotation_config,
        queue_name="training",
        example_id="train_0",
        primary_intent="account_access_and_profile",
        should_escalate="yes",
        escalation_reason_code="security_or_account_compromise",
        escalation_explanation="Synthetic security condition requires a human.",
        risk_flags=("security_or_compromise",),
        ambiguity="clear",
        annotation_notes="Revised synthetic judgment",
        annotator_id="tester",
    )
    audit = annotation_paths(annotation_config.annotation.output_dir).audit / "training.jsonl"
    events = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["event"] == "judgment_edited"
    assert events[-1]["reference_was_revealed_before_edit"] is True
    assert events[-1]["before"]["primary_intent"] == "other_or_unclear"


def test_skipped_example_remains_incomplete(annotation_config: AppConfig):
    skipped = skip_example(annotation_config, "training", "train_1", "tester", "return later")
    assert skipped.status == "skipped"
    report = validate_annotation_outputs(annotation_config)
    assert report["annotations"]["training"]["skipped_incomplete"] == 1
    assert report["human_annotations"] != "complete"


def test_invalid_label_is_rejected(annotation_config: AppConfig):
    with pytest.raises(AnnotationError, match="invalid intent"):
        save_initial_judgment(
            annotation_config,
            queue_name="training",
            example_id="train_0",
            primary_intent="invented_label",
            should_escalate="no",
            escalation_reason_code=None,
            escalation_explanation=None,
            risk_flags=(),
            ambiguity="clear",
            annotation_notes="Synthetic fixture",
            annotator_id="tester",
        )


def test_escalation_requires_a_reason_and_explanation(annotation_config: AppConfig):
    with pytest.raises(ValueError, match="escalation_reason_code"):
        save_initial_judgment(
            annotation_config,
            queue_name="training",
            example_id="train_0",
            primary_intent="account_access_and_profile",
            should_escalate="yes",
            escalation_reason_code=None,
            escalation_explanation=None,
            risk_flags=("security_or_compromise",),
            ambiguity="clear",
            annotation_notes="Synthetic fixture",
            annotator_id="tester",
        )


def test_duplicate_annotation_records_are_rejected(annotation_config: AppConfig):
    _save_valid(annotation_config)
    path = annotation_paths(annotation_config.annotation.output_dir).labels / "training.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    pd.concat([frame, frame], ignore_index=True).to_csv(path, index=False)
    with pytest.raises(AnnotationError, match="duplicate annotation records"):
        AnnotationStore(annotation_config, "training").load()


def test_reference_hidden_until_initial_judgment_saved(annotation_config: AppConfig):
    view = get_annotation_view(annotation_config, "training", "train_0")
    assert view["reference_revealed"] is False
    assert "historical_reference" not in view
    with pytest.raises(AnnotationError, match="save the initial"):
        reveal_reference(annotation_config, "training", "train_0")
    _save_valid(annotation_config)
    reveal_reference(annotation_config, "training", "train_0")
    revealed = get_annotation_view(annotation_config, "training", "train_0")
    assert revealed["reference_revealed"] is True
    assert revealed["historical_reference"]["reply_texts_redacted"] == ["Synthetic historical reply"]


def test_completion_requires_nonempty_expected_guidance(annotation_config: AppConfig):
    _save_valid(annotation_config)
    reveal_reference(annotation_config, "training", "train_0")
    with pytest.raises(ValueError, match="expected_reply_guidance"):
        save_expected_guidance(annotation_config, "training", "train_0", "")


def test_golden_view_excludes_model_suggestions(annotation_config: AppConfig):
    split_path = annotation_config.annotation.split_dir / OUTPUT_FILES["test_candidate_inputs"]
    frame = pd.read_parquet(split_path)
    frame["model_prediction"] = "must never be shown"
    frame["model_confidence"] = 0.99
    frame.to_parquet(split_path, index=False)
    freeze_guide(
        annotation_config,
        annotator_id="tester",
        confirm_taxonomy_version="spotify-intents-v0.1-proposed",
        confirm_guide_version="spotify-annotation-v0.1-proposed",
    )
    view = get_annotation_view(annotation_config, "golden", "golden_0")
    assert "model_prediction" not in view
    assert "model_confidence" not in view


def test_guide_freeze_gates_development_and_golden(annotation_config: AppConfig):
    with pytest.raises(AnnotationError, match="locked"):
        AnnotationStore(annotation_config, "development")
    state = freeze_guide(
        annotation_config,
        annotator_id="tester",
        confirm_taxonomy_version="spotify-intents-v0.1-proposed",
        confirm_guide_version="spotify-annotation-v0.1-proposed",
    )
    assert state["status"] == "frozen"
    assert AnnotationStore(annotation_config, "development").load() == {}


def test_sampling_is_deterministic_and_golden_groups_are_separate():
    pool = _synthetic_pool("candidate", 80)
    first = sample_uniform_queue(
        pool, queue_name="development", size=20, seed=42, pool_hash="a" * 64
    )
    second = sample_uniform_queue(
        pool, queue_name="development", size=20, seed=42, pool_hash="a" * 64
    )
    pd.testing.assert_frame_equal(first, second)
    golden_a = sample_golden_queue(
        pool, random_size=15, challenge_size=10, seed=42, pool_hash="b" * 64
    )
    golden_b = sample_golden_queue(
        pool, random_size=15, challenge_size=10, seed=42, pool_hash="b" * 64
    )
    pd.testing.assert_frame_equal(golden_a, golden_b)
    assert golden_a["thread_id"].is_unique
    assert golden_a["combined_group_id"].is_unique
    assert (golden_a["sampling_stratum"] == "random").sum() == 15
    assert golden_a["sampling_stratum"].str.startswith("challenge:").sum() == 10


def test_incorrect_split_membership_is_rejected():
    pools = {
        "train": _synthetic_pool("train", 1),
        "development": _synthetic_pool("development", 1),
        "test_candidate": _synthetic_pool("golden", 1),
    }
    queues = {
        "training": _queue("training", pools["development"]),
        "development": _queue("development", pools["development"]),
        "golden": _queue("golden", pools["test_candidate"]),
    }
    with pytest.raises(AnnotationError, match="not in train"):
        validate_queue_membership(queues, pools)


def test_stale_guide_versions_are_flagged(annotation_config: AppConfig):
    _save_valid(annotation_config)
    annotation_config.annotation.guide_path.write_text(
        "# Changed synthetic test guide\n", encoding="utf-8"
    )
    report = validate_annotation_outputs(annotation_config)
    assert report["annotations"]["training"]["stale_requires_human_review"] == 1
