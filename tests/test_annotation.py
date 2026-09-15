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
    extend_training_queue,
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
            "retained_machine_runs": [],
            "excluded_machine_runs": {},
            "machine_record_exclusions_path": None,
            "groq_prompt_path": Path("configs/machine_annotation_prompt.txt"),
            "groq_prompt_profile": "full",
            "groq_max_completion_tokens": 2048,
            "machine_decision_schema": "full-v1",
            "machine_rate": base.annotation.machine_rate.model_copy(update={"request_interval_seconds": 0}),
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


def _complete_pilot(config: AppConfig) -> None:
    _save_valid(config)
    reveal_reference(config, "training", "train_0")
    save_expected_guidance(
        config,
        "training",
        "train_0",
        "Give a concise synthetic next step.",
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
    _complete_pilot(annotation_config)
    freeze_guide(
        annotation_config,
        annotator_id="tester",
        confirm_taxonomy_version=current_contract(annotation_config)["taxonomy_version"],
        confirm_guide_version=current_contract(annotation_config)["guide_version"],
    )
    view = get_annotation_view(annotation_config, "golden", "golden_0")
    assert "model_prediction" not in view
    assert "model_confidence" not in view


def test_guide_freeze_gates_development_and_golden(annotation_config: AppConfig):
    with pytest.raises(AnnotationError, match="locked"):
        AnnotationStore(annotation_config, "development")
    with pytest.raises(AnnotationError, match="training pilot is not ready"):
        freeze_guide(
            annotation_config,
            annotator_id="tester",
            confirm_taxonomy_version=current_contract(annotation_config)["taxonomy_version"],
            confirm_guide_version=current_contract(annotation_config)["guide_version"],
        )
    _complete_pilot(annotation_config)
    state = freeze_guide(
        annotation_config,
        annotator_id="tester",
        confirm_taxonomy_version=current_contract(annotation_config)["taxonomy_version"],
        confirm_guide_version=current_contract(annotation_config)["guide_version"],
    )
    assert state["status"] == "frozen"
    assert AnnotationStore(annotation_config, "development").load() == {}


def test_training_extension_appends_without_replacing_initial_queue(
    annotation_config: AppConfig, monkeypatch: pytest.MonkeyPatch
):
    import spotify_cares.annotation as annotation_module

    split_dir = annotation_config.annotation.split_dir
    larger_train = _synthetic_pool("train", 12)
    _write_pool_and_references(split_dir, "train", larger_train)
    train_hash = sha256_file(split_dir / OUTPUT_FILES["train_inputs"])
    queue_path = annotation_paths(annotation_config.annotation.output_dir).queues / "training.parquet"
    initial = pd.read_parquet(queue_path)
    initial["candidate_pool_sha256"] = train_hash
    initial.to_parquet(queue_path, index=False)
    monkeypatch.setattr(
        annotation_module,
        "verify_preprocessing_prerequisites",
        lambda config: {"manifest": {"output_sha256": {"train_inputs": train_hash}}},
    )

    result = extend_training_queue(
        annotation_config,
        batch_name="synthetic_more",
        size=3,
    )
    extended = pd.read_parquet(queue_path)
    assert result["first_queue_position"] == 3
    assert list(extended.iloc[:2]["example_id"]) == list(initial["example_id"])
    assert len(extended) == 5
    assert set(extended.iloc[2:]["example_id"]).issubset(set(larger_train["example_id"]))


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


def _synthetic_review_selection(config: AppConfig, examples=None) -> Path:
    path = config.annotation.output_dir / "coverage_review.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "queue_name": "training",
        "name": "Synthetic coverage review",
        "source_queue_sha256": "0" * 64,
        "purpose": "Synthetic navigation fixture only",
        "examples": examples or [
            {"original_position": 2, "example_id": "train_1"},
            {"original_position": 1, "example_id": "train_0"},
        ],
    }), encoding="utf-8")
    return path


def test_review_view_preserves_queue_order_and_rejects_retargeting(annotation_config):
    from spotify_cares.review_navigation import coverage_review_view

    path = _synthetic_review_selection(annotation_config)
    queue_path = annotation_paths(annotation_config.annotation.output_dir).queues / "training.parquet"
    queue = pd.read_parquet(queue_path)
    original = queue.copy(deep=True)
    result = coverage_review_view(queue, path)
    assert result.example_id.tolist() == ["train_0", "train_1"]
    pd.testing.assert_frame_equal(queue, original)
    changed = queue.copy()
    changed.loc[0, "example_id"] = "replacement"
    with pytest.raises(AnnotationError, match="missing or its original position changed"):
        coverage_review_view(changed, path)
    changed = queue.copy()
    changed["queue_name"] = "golden"
    with pytest.raises(AnnotationError, match="only for the training"):
        coverage_review_view(changed, path)
    _synthetic_review_selection(annotation_config, [
        {"original_position": 1, "example_id": "train_0"},
        {"original_position": 2, "example_id": "train_0"},
    ])
    with pytest.raises(AnnotationError, match="duplicate IDs"):
        coverage_review_view(queue, path)


def test_coverage_app_navigation_saves_original_record(annotation_config, monkeypatch):
    """Exercise selection, blank fields, save, and back/next with synthetic data."""
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    import spotify_cares.config as config_module

    monkeypatch.setattr(config_module, "load_config", lambda _: annotation_config)
    _synthetic_review_selection(annotation_config)
    paths = annotation_paths(annotation_config.annotation.output_dir)
    queue_hash = sha256_file(paths.queues / "training.parquet")
    app = AppTest.from_file(Path("app/annotation_app.py").resolve()).run(timeout=15)
    assert not app.exception

    def widget(kind, label):
        return next(item for item in getattr(app, kind) if item.label == label)

    widget("radio", "Training view").set_value("Coverage review").run()
    assert not app.exception
    widget("selectbox", "Coverage review example").select("train_1").run()
    assert "Original training position 2" in app.subheader[0].value
    assert widget("selectbox", "Primary intent").value is None
    assert widget("radio", "Should a human handle this case under the written policy?").value is None
    assert widget("radio", "Ambiguity").value is None
    assert AnnotationStore(annotation_config, "training").load() == {}

    widget("text_input", "Annotator ID").set_value("synthetic_tester")
    widget("selectbox", "Primary intent").select("other_or_unclear")
    widget("radio", "Should a human handle this case under the written policy?").set_value("no")
    widget("radio", "Ambiguity").set_value("clear")
    widget("button", "Save judgment").click().run()
    assert not app.exception
    saved = AnnotationStore(annotation_config, "training").load()
    assert set(saved) == {"train_1"}
    assert saved["train_1"].queue_name == "training"
    assert saved["train_1"].reference_revealed is False
    assert (paths.audit / "training.jsonl").is_file()
    widget("button", "Back").click().run()
    assert widget("selectbox", "Coverage review example").value == "train_0"
    assert widget("selectbox", "Primary intent").value is None
    widget("button", "Next").click().run()
    assert widget("selectbox", "Coverage review example").value == "train_1"
    assert widget("selectbox", "Primary intent").value == "other_or_unclear"
    widget("button", "Resume first incomplete").click().run()
    assert widget("selectbox", "Coverage review example").value == "train_0"
    assert sha256_file(paths.queues / "training.parquet") == queue_hash
