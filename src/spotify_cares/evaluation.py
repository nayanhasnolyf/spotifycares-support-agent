"""Evaluation harness for comparing automated systems against human labels.

Produces structural reports, saves prediction caches, and computes metrics only
when genuine labels are provided. Golden evaluation is protected by default.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from spotify_cares.annotation import AnnotationError, AnnotationStore
from spotify_cares.baselines import ACK, route_policy
from spotify_cares.machine_annotation import canonical, run_lock


class EvaluationSystem(Protocol):
    def predict(self, message: str, context: list[str]) -> dict[str, Any]:
        """Return a structured prediction dictionary for a customer message."""
        ...


class TrivialSystem:
    def __init__(self, classifier):
        self.majority = classifier.majority if classifier.model is not None else None

    def predict(self, message: str, context: list[str]) -> dict[str, Any]:
        return {
            "intent": self.majority,
            "draft": ACK + " Escalate to human.",
            "decision": "proposed_escalate",
            "reason_codes": [],
        }


class TFIDFSystem:
    def __init__(self, classifier, retriever, settings):
        self.classifier = classifier
        self.retriever = retriever
        self.settings = settings

    def predict(self, message: str, context: list[str]) -> dict[str, Any]:
        from spotify_cares.baselines import detect_signals, draft_reply, feature_text, route_policy
        text = feature_text(message, context)
        intent = self.classifier.predict(text, "tfidf") if self.classifier.model else None
        evidence = self.retriever.search(text)
        route = route_policy(detect_signals(text))
        draft = draft_reply(route, evidence)
        reasons = [route["reason_code"]] if route["reason_code"] else []
        if not evidence:
            reasons.append("insufficient_retrieval_or_generation_evidence")
        if self.classifier.model is None:
            reasons.append("classifier_unavailable")
            
        return {
            "intent": intent,
            "draft": draft,
            "decision": "proposed_escalate" if reasons else "proposed_auto_handle",
            "reason_codes": reasons,
            "evidence_ids": [i for e in evidence for i in e.get("evidence_ids", [])],
        }


class AgentSystem:
    def __init__(self, config, baseline_settings, agent_settings):
        self.config = config
        self.baseline_settings = baseline_settings
        self.agent_settings = agent_settings

    def predict(self, message: str, context: list[str]) -> dict[str, Any]:
        from spotify_cares.agent import run_agent
        return run_agent(self.config, self.baseline_settings, self.agent_settings, message, context)


def _load_labels(config, queue_name, split_dir, must_have_labels=False):
    inputs = pd.read_parquet(split_dir / f"{'test_candidate' if queue_name == 'golden' else queue_name}_inputs.parquet")
    try:
        store = AnnotationStore(config, queue_name).load()
        labels = {k: v.model_dump() for k, v in store.items() if v.status == "judgment_saved"}
    except AnnotationError:
        labels = {}
    
    if must_have_labels and not labels:
        raise AnnotationError(f"no completed human labels found for {queue_name}")
        
    records = []
    for r in inputs.to_dict("records"):
        label = labels.get(r["example_id"])
        if must_have_labels and not label:
            continue
            
        record = {
            "example_id": r["example_id"],
            "customer_text": r["customer_text_redacted"],
            "context_texts": r.get("context_texts_redacted", []),
            "human_intent": label["primary_intent"] if label else None,
            "human_escalate": label["should_escalate"] == "yes" if label else None,
            "human_escalation_reason": label.get("escalation_reason_code") if label else None,
        }
        records.append(record)
        
    if must_have_labels:
        if len(records) != 150:
            raise AnnotationError(f"expected exactly 150 golden records, found {len(records)}")
        annotators = {labels.get(r["example_id"], {}).get("annotator_id") for r in records}
        if "gemini" in annotators or "groq" in annotators:
            raise AnnotationError("machine-generated labels detected in golden set")
        if len(set(r["example_id"] for r in records)) != len(records):
            raise AnnotationError("duplicate golden IDs detected")
            
    return records


def cached_evaluation(system: EvaluationSystem, system_name: str, records: list[dict], cache_dir: Path, live: bool = False):
    cache_path = cache_dir / f"{system_name}_predictions.jsonl"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    predictions = {}
    if cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    p = json.loads(line)
                    if p.get("generation", {}).get("error") != "provider_unavailable":
                        predictions[p["example_id"]] = p
                    
    results = []
    new_predictions = []
    
    for r in records:
        eid = r["example_id"]
        if eid in predictions:
            pred = predictions[eid]
        elif live:
            start_time = time.time()
            pred = system.predict(r["customer_text"], r["context_texts"])
            pred["example_id"] = eid
            pred["runtime_seconds"] = time.time() - start_time
            pred["timestamp"] = datetime.now(timezone.utc).isoformat()
            
            if pred.get("generation", {}).get("error") != "provider_unavailable":
                with run_lock(cache_dir / "predictions.lock"):
                    with cache_path.open("a", encoding="utf-8") as f:
                        f.write(canonical(pred) + "\n")
                    
        else:
            raise AnnotationError(f"cache miss for {eid} and --live not specified")
        
        results.append({"example_id": eid, "prediction": pred, "ground_truth": r})
                    
    return results


def compute_metrics(results: list[dict], system_name: str):
    from collections import Counter
    report = {"system": system_name, "metrics_status": "structural_only"}
    
    has_labels = any(r["ground_truth"]["human_intent"] for r in results)
    
    # Structural diagnostics
    preds = [r["prediction"] for r in results]
    intents = [p.get("intent") for p in preds if p.get("intent")]
    escalates = [p.get("decision") == "proposed_escalate" for p in preds]
    
    report["diagnostics"] = {
        "total_examples": len(results),
        "predicted_intents_count": len(set(intents)),
        "escalation_rate": sum(escalates) / len(results) if results else 0,
        "fallback_rate": sum(p.get("fallback", False) for p in preds) / len(results) if results else 0,
        "empty_retrieval_rate": sum("insufficient_retrieval_or_generation_evidence" in p.get("reason_codes", []) for p in preds) / len(results) if results else 0,
    }
    
    report["reply_quality"] = {
        "status": "pending_human_ratings",
        "llm_judge_agreement": "N/A",
        "helpfulness_score": "N/A",
        "safety_score": "N/A"
    }
    
    if not has_labels:
        report["metrics_status"] = "pending_human_labels"
        return report
        
    report["metrics_status"] = "computed"
    
    # Intent metrics
    correct = sum(1 for r in results if r["ground_truth"]["human_intent"] and r["prediction"].get("intent") == r["ground_truth"]["human_intent"])
    total_labeled = sum(1 for r in results if r["ground_truth"]["human_intent"])
    
    report["intent"] = {
        "accuracy": correct / total_labeled if total_labeled else 0,
        "correct": correct,
        "total_labeled": total_labeled
    }
    
    # Escalation safety metrics
    # Escalation safety metrics
    escalation_cases = [r for r in results if r["ground_truth"]["human_escalate"] is True]
    auto_handle_cases = [r for r in results if r["ground_truth"]["human_escalate"] is False]
    
    proposed_escalate = [r for r in results if r["prediction"].get("decision") == "proposed_escalate"]
    proposed_auto_handle = [r for r in results if r["prediction"].get("decision") == "proposed_auto_handle"]
    
    true_escalations = [r for r in escalation_cases if r["prediction"].get("decision") == "proposed_escalate"]
    false_auto_handles = [r for r in escalation_cases if r["prediction"].get("decision") == "proposed_auto_handle"]
    true_auto_handles = [r for r in auto_handle_cases if r["prediction"].get("decision") == "proposed_auto_handle"]
    
    report["escalation"] = {
        "human_escalation_cases": len(escalation_cases),
        "human_auto_handle_cases": len(auto_handle_cases),
        "proposed_escalate": len(proposed_escalate),
        "proposed_auto_handle": len(proposed_auto_handle),
        
        "successfully_escalated": len(true_escalations),
        "unsafe_auto_handles": len(false_auto_handles),
        "successful_auto_handles": len(true_auto_handles),
        
        "escalation_precision": len(true_escalations) / len(proposed_escalate) if proposed_escalate else 0.0,
        "escalation_recall": len(true_escalations) / len(escalation_cases) if escalation_cases else 0.0,
        "auto_handling_coverage": len(proposed_auto_handle) / len(results) if results else 0.0,
        "unsafe_auto_handle_rate": len(false_auto_handles) / len(proposed_auto_handle) if proposed_auto_handle else 0.0,
        "missed_escalation_rate": len(false_auto_handles) / len(escalation_cases) if escalation_cases else 0.0,
    }
    
    failed_intent = [r.get("example_id") for r in results if r["ground_truth"]["human_intent"] and r["prediction"].get("intent") != r["ground_truth"]["human_intent"]]
    failed_escalation = [r.get("example_id") for r in false_auto_handles]
    
    report["failures"] = {
        "intent_errors": failed_intent,
        "unsafe_auto_handles": failed_escalation,
    }
        
    return report


def run_evaluation(config, baseline_settings, agent_settings, queue_name: str, systems: list[str], live: bool, golden_confirmed: bool):
    if queue_name == "golden" and not golden_confirmed:
        raise AnnotationError("golden queue evaluation requires explicit confirmation (--golden-confirmed) to prevent accidental unblinding")
        
    cache_dir = config.artifacts.directory / "evaluation"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    records = _load_labels(config, queue_name, config.annotation.split_dir, must_have_labels=queue_name=="golden")
    if not records:
        raise AnnotationError(f"no examples found for queue {queue_name}")
        
    from spotify_cares.baselines import IntentBaselines, HistoricalRetriever, load_training
    training, corpus, allowed, tr_report = load_training(config, baseline_settings)
    classifier = IntentBaselines(training, allowed, baseline_settings)
    
    reports = {}
    
    if "trivial" in systems:
        sys = TrivialSystem(classifier)
        results = cached_evaluation(sys, "trivial", records, cache_dir, live)
        reports["trivial"] = compute_metrics(results, "trivial")
        
    if "tfidf" in systems:
        retriever = HistoricalRetriever(corpus, baseline_settings)
        sys = TFIDFSystem(classifier, retriever, baseline_settings)
        results = cached_evaluation(sys, "tfidf", records, cache_dir, live)
        reports["tfidf"] = compute_metrics(results, "tfidf")
        
    if "agent" in systems:
        sys = AgentSystem(config, baseline_settings, agent_settings)
        results = cached_evaluation(sys, "agent", records, cache_dir, live)
        reports["agent"] = compute_metrics(results, "agent")
        
    final_report = {
        "queue": queue_name,
        "examples": len(records),
        "labeled_examples": sum(1 for r in records if r["human_intent"]),
        "systems": reports,
        "classifier_status": {
            "training_examples": len(training),
            "missing_classes": sorted(allowed - set(training.intent))
        }
    }
    
    return final_report
