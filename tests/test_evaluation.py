"""Synthetic tests for the evaluation harness."""
import json
from pathlib import Path

import pandas as pd
import pytest

from spotify_cares.annotation import AnnotationError, AnnotationStore
from spotify_cares.evaluation import (
    AgentSystem, TFIDFSystem, TrivialSystem, cached_evaluation, compute_metrics,
    run_evaluation
)
from spotify_cares.config import AppConfig
from test_annotation import annotation_config, _save_valid, _write_pool_and_references


class DummySystem:
    def predict(self, message, context):
        return {
            "intent": "other_or_unclear",
            "draft": "ACK",
            "decision": "proposed_auto_handle",
            "reason_codes": [],
            "fallback": False
        }


def test_compute_metrics_structural_only():
    results = [
        {"ground_truth": {"human_intent": None, "human_escalate": None}, "prediction": {"intent": "billing_and_payment", "decision": "proposed_escalate"}}
    ]
    report = compute_metrics(results, "dummy")
    assert report["metrics_status"] == "pending_human_labels"
    assert report["diagnostics"]["escalation_rate"] == 1.0


def test_compute_metrics_with_labels():
    results = [
        {"ground_truth": {"human_intent": "billing_and_payment", "human_escalate": True}, "prediction": {"intent": "billing_and_payment", "decision": "proposed_escalate"}},
        {"ground_truth": {"human_intent": "other_or_unclear", "human_escalate": True}, "prediction": {"intent": "billing_and_payment", "decision": "proposed_auto_handle"}}
    ]
    report = compute_metrics(results, "dummy")
    assert report["metrics_status"] == "computed"
    assert report["intent"]["accuracy"] == 0.5
    assert report["escalation"]["human_escalation_cases"] == 2
    assert report["escalation"]["missed_escalation_rate"] == 0.5
    assert report["escalation"]["unsafe_auto_handle_rate"] == 1.0
    assert report["escalation"]["successfully_escalated"] == 1


def test_cached_evaluation(tmp_path):
    sys = DummySystem()
    cache_dir = tmp_path / "cache"
    records = [{"example_id": "1", "customer_text": "hello", "context_texts": [], "human_intent": None}]
    
    # Run live
    results1 = cached_evaluation(sys, "dummy", records, cache_dir, live=True)
    assert len(results1) == 1
    assert (cache_dir / "dummy_predictions.jsonl").exists()
    
    # Run cached without live
    results2 = cached_evaluation(sys, "dummy", records, cache_dir, live=False)
    assert results2[0]["prediction"]["intent"] == "other_or_unclear"
    
    # Miss cache
    records.append({"example_id": "2", "customer_text": "hello 2", "context_texts": [], "human_intent": None})
    with pytest.raises(AnnotationError, match="cache miss"):
        cached_evaluation(sys, "dummy", records, cache_dir, live=False)


def test_run_evaluation_golden_protection(annotation_config, tmp_path):
    from spotify_cares.baselines import BaselineSettings
    bs = BaselineSettings(manifest_path=tmp_path / "b.json")
    # Need golden confirmed
    with pytest.raises(AnnotationError, match="golden"):
        run_evaluation(annotation_config, bs, None, "golden", ["trivial"], False, False)
