"""Synthetic software fixtures only; these tests do not measure model accuracy."""
import json
from pathlib import Path

import pandas as pd
import pytest

from spotify_cares.annotation import AnnotationError, sha256_file
from spotify_cares.baselines import (
    ACK, BaselineSettings, HistoricalRetriever, IntentBaselines, PolicySignals,
    detect_signals, draft_reply, feature_text, load_training, route_policy,
    sanitize_historical_reply, validate_corpus,
)
from test_annotation import annotation_config
from test_groq_annotation import ready
from test_machine_annotation import fake
from spotify_cares.machine_annotation import machine_annotate
from spotify_cares.machine_annotation import digest


def settings():
    return BaselineSettings(manifest_path=Path("synthetic.json"))


def corpus():
    return pd.DataFrame([
        {"example_id": "train_a", "combined_group_id": "ga", "thread_id": "ta",
         "customer_text_redacted": "synthetic music playback", "context_texts_redacted": [],
         "reference_reply_ids": ["reply_a"], "historical_reply_texts_redacted": ["Please restart your app."]},
        {"example_id": "train_b", "combined_group_id": "gb", "thread_id": "tb",
         "customer_text_redacted": "synthetic card refund", "context_texts_redacted": [],
         "reference_reply_ids": ["reply_b"], "historical_reply_texts_redacted": ["We refunded your card."]},
    ])


def test_classifier_fit_scope_unknown_labels_and_tie():
    train = pd.DataFrame({"text": ["music stops", "card charged"], "intent": ["playback", "billing"]})
    model = IntentBaselines(train, {"playback", "billing"}, settings())
    assert model.majority == "billing"  # lexical tie break
    assert model.model is not None
    before = dict(model.vectorizer.vocabulary_)
    model.predict("neverfitcanary", "tfidf")
    assert model.vectorizer.vocabulary_ == before and "neverfitcanary" not in before
    assert "refunded" not in before  # historical responses never fit classifier vocabulary
    with pytest.raises(AnnotationError, match="unknown"):
        IntentBaselines(train, {"playback"}, settings())


@pytest.mark.parametrize("size", [0, 1])
def test_fitting_blocker_does_not_block_retrieval(size):
    train = pd.DataFrame({"text": ["music"] * size, "intent": ["playback"] * size})
    model = IntentBaselines(train, {"playback"}, settings())
    assert "at least two classes" in model.blocker
    with pytest.raises(AnnotationError):
        model.predict("music", "tfidf")
    assert HistoricalRetriever(corpus(), settings()).search("music")


def test_retrieval_empty_oov_and_group_exclusion():
    assert HistoricalRetriever(corpus().iloc[:0], settings()).search("music") == []
    retriever = HistoricalRetriever(corpus(), settings())
    assert retriever.search("nonexistentcanary") == []
    assert retriever.search("music", exclude_groups={"ga"}) == []
    assert retriever.search("music", exclude_ids={"train_a"}) == []
    hit = retriever.search("music")[0]
    assert hit["evidence_ids"] == ["reply_a"]
    assert "reply_a" not in retriever.vectorizer.vocabulary_


@pytest.mark.parametrize("column,value", [("example_id", "golden_canary"), ("combined_group_id", "dev_group"), ("thread_id", "test_thread")])
def test_reject_corpus_leakage(column, value):
    rows = corpus()
    members = rows[["example_id", "combined_group_id", "thread_id"]].copy()
    rows.loc[0, column] = value
    with pytest.raises(AnnotationError, match="outside"):
        validate_corpus(rows, members)


@pytest.mark.parametrize("text", [
    "We checked your transaction. Please restart the app.",
    "I've created a support ticket. Try restarting.",
    "Your refund is done. Please restart.",
    "Your account has been restored. Please restart.",
    "Send your password to https://untrusted.example. Try restarting.",
    "Please restart. Your subscription is cancelled.",
])
def test_unsafe_historical_claims_are_not_copied(text):
    assert sanitize_historical_reply(text) == ""


def test_safe_projection_and_no_historical_routing():
    assert sanitize_historical_reply("Can you try restarting the app? /SyntheticAgent") == "Try restarting the app or device."
    hit = HistoricalRetriever(corpus(), settings()).search("refund")
    route = route_policy(PolicySignals())
    draft = draft_reply(route, hit)
    assert "refunded" not in draft and "Could you describe" in draft
    assert route["decision"] == "auto_handle"


def test_policy_specific_reason_and_safe_clarification():
    assert route_policy(PolicySignals(current_security_incident=True, private_account_action=True))["reason_code"] == "security_or_account_compromise"
    assert route_policy(PolicySignals(payment_investigation=True, private_account_action=True))["reason_code"] == "refund_or_payment_investigation"
    assert route_policy(detect_signals("I got paid three times and have no subscription"))["decision"] == "auto_handle"
    assert not detect_signals("My account was hacked last year but is now restored").current_security_incident
    assert detect_signals("My account is hacked").current_security_incident
    assert not detect_signals("I was not charged twice").payment_investigation


def test_loader_no_dev_or_golden_reads_and_preserves_labels(annotation_config, monkeypatch):
    config = ready(annotation_config)
    report = machine_annotate(config, "training", provider_name="groq", provider=fake)
    root = config.annotation.split_dir
    inputs = pd.read_parquet(root / "train_inputs.parquet")
    historical = inputs[["example_id", "combined_group_id", "thread_id", "customer_text_redacted", "context_texts_redacted"]].copy()
    historical["reference_reply_ids"] = [["synthetic_reply"] for _ in range(len(historical))]
    historical["historical_reply_texts_redacted"] = [["Please restart."] for _ in range(len(historical))]
    historical.to_parquet(root / "training_retrieval_corpus.parquet", index=False)
    (root / "preprocessing_manifest.json").write_text(json.dumps({"output_sha256": {
        "train_inputs": sha256_file(root / "train_inputs.parquet"),
        "retrieval": sha256_file(root / "training_retrieval_corpus.parquet")}}))
    label_path = Path(report["path"])
    before = label_path.read_bytes()
    original = pd.read_parquet
    def guarded(path, *a, **kw):
        assert not any(s in Path(path).name for s in ("development", "golden", "test_candidate", "references"))
        return original(path, *a, **kw)
    monkeypatch.setattr(pd, "read_parquet", guarded)
    config_settings = BaselineSettings(manifest_path=Path(report["combined_manifest"]))
    train, historical, allowed, summary = load_training(config, config_settings)
    assert len(train) == 1 and summary["protected_human_records"] == 1
    assert len(historical) > len(train)  # no label-completeness gate on retrieval
    assert label_path.read_bytes() == before


def test_redaction_placeholders_not_features():
    assert "CUSTOMER" not in feature_text("[CUSTOMER] hello")


@pytest.mark.parametrize("blocked_by", ["held", "human", "duplicate"])
def test_selection_rejects_held_human_and_duplicates(tmp_path, monkeypatch, blocked_by):
    manifest = {"queue": "training", "selected_labels": [{"example_id": "synthetic_id"}],
                "protected_human_ids": [], "excluded_records": []}
    if blocked_by == "held":
        manifest["excluded_records"] = [{"example_id": "synthetic_id"}]
    elif blocked_by == "human":
        manifest["protected_human_ids"] = ["synthetic_id"]
    else:
        manifest["selected_labels"] *= 2
    path = tmp_path / (digest(manifest) + ".json")
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr("spotify_cares.baselines.combined_machine_manifest", lambda *a, **k: {"combined_manifest": str(path)})
    with pytest.raises(AnnotationError, match="duplicate, held or human"):
        load_training(None, BaselineSettings(manifest_path=path))
