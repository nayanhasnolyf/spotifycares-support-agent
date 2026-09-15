"""Training-only baselines. Execution is not evaluation or evidence of accuracy."""
from collections import Counter
from pathlib import Path
import json
import re
import warnings

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
import sklearn
import yaml

from spotify_cares.annotation import AnnotationError, load_taxonomy
from spotify_cares.machine_annotation import (
    combined_machine_manifest, digest, load_events, read_inputs, sha256_file,
)
from spotify_cares.preprocessing import redact_text

ACK = "Thanks for reaching out to SpotifyCares."


class BaselineSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_path: Path
    max_features: int = Field(default=30000, ge=1)
    ngram_max: int = Field(default=2, ge=1, le=3)
    logistic_c: float = Field(default=1.0, gt=0)
    max_iter: int = Field(default=1000, ge=1)
    retrieval_k: int = Field(default=3, ge=1, le=10)
    seed: int = 42


def load_settings(path):
    return BaselineSettings.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def feature_text(message, context=()):
    # Redaction placeholders must not become evidence of customer intent.
    text = " ".join([*context, message])
    return re.sub(r"\[[A-Z_]+\]", " ", redact_text(text, safe_domains=())[0])


def load_training(config, settings):
    """Validate current selection read-only, then open only train Parquet columns."""
    path = settings.manifest_path
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("queue") != "training" or digest(manifest) != path.stem:
        raise AnnotationError("baseline requires an intact content-addressed training manifest")
    current = combined_machine_manifest(config, "training", provider_name="groq", write=False)
    if Path(current["combined_manifest"]).stem != path.stem:
        raise AnnotationError("pinned selection is stale; explicitly select a validated current manifest")
    selected = manifest["selected_labels"]
    ids = [s["example_id"] for s in selected]
    blocked = set(manifest["protected_human_ids"]) | {e["example_id"] for e in manifest["excluded_records"]}
    # A record-level hold on an older attempt must not silently admit its ID here.
    if len(set(ids)) != len(ids) or set(ids) & blocked:
        raise AnnotationError("duplicate, held or human IDs in classifier selection")
    taxonomy = load_taxonomy(config.annotation.taxonomy_path)
    allowed = {i.label for i in taxonomy.intents}
    root = config.annotation.split_dir
    split_manifest = json.loads((root / "preprocessing_manifest.json").read_text(encoding="utf-8"))
    for key, name in (("train_inputs", "train_inputs.parquet"), ("retrieval", "training_retrieval_corpus.parquet")):
        if sha256_file(root / name) != split_manifest["output_sha256"][key]:
            raise AnnotationError("training corpus fingerprint changed")
    inputs = read_inputs(root / "train_inputs.parquet", set(ids))
    cache, labels, runs = {}, [], {}
    for item in selected:
        source = item["source_path"]
        if source not in cache:
            cache[source] = load_events(Path(source))
        event = next(e for e in cache[source] if e.example_id == item["example_id"] and e.attempt == item["attempt"])
        if (event.status != "success" or event.decision.primary_intent not in allowed
                or digest(event.model_dump(mode="json")) != item["record_sha256"]
                or digest(inputs[item["example_id"]]) != item["input_sha256"]):
            raise AnnotationError("unknown label or invalid selected record/input")
        labels.append(event.decision.primary_intent)
        runs[event.run_sha256] = event.provenance
    train = pd.DataFrame([{"example_id": eid, "text": feature_text(inputs[eid]["customer_text_redacted"],
                        inputs[eid]["context_texts_redacted"]), "intent": label}
                         for eid, label in zip(ids, labels)], columns=["example_id", "text", "intent"])
    corpus = pd.read_parquet(root / "training_retrieval_corpus.parquet", columns=[
        "example_id", "combined_group_id", "thread_id", "customer_text_redacted",
        "context_texts_redacted", "reference_reply_ids", "historical_reply_texts_redacted"])
    # No development/test files are needed to enforce subset membership and group identity.
    membership = pd.read_parquet(root / "train_inputs.parquet", columns=["example_id", "combined_group_id", "thread_id"])
    validate_corpus(corpus, membership)
    corpus = corpus.sort_values("example_id").reset_index(drop=True)
    summary = {"training_examples": len(train), "class_distribution": dict(Counter(labels)),
               "missing_classes": sorted(allowed - set(labels)), "annotation_source": "machine_annotated",
               "providers": dict(Counter(s["provider"] for s in selected)),
               "protected_human_records": len(manifest["protected_human_ids"]),
               "held_example_ids_excluded": len({e["example_id"] for e in manifest["excluded_records"]}),
               "retrieval_examples": len(corpus), "manifest_sha256": path.stem,
               "policy": {k: manifest[k] for k in ("taxonomy_version", "guide_version", "taxonomy_sha256", "guide_sha256")},
               "label_runs": runs, "settings": settings.model_dump(mode="json"),
               "sklearn_version": sklearn.__version__,
               "corpus_sha256": sha256_file(root / "training_retrieval_corpus.parquet"),
               "interpretation": "implementation demonstration only; no accuracy measured"}
    return train, corpus, allowed, summary


def validate_corpus(corpus, membership):
    if corpus.example_id.duplicated().any() or membership.example_id.duplicated().any():
        raise AnnotationError("duplicate training corpus IDs")
    merged = corpus[["example_id", "combined_group_id", "thread_id"]].merge(
        membership, on="example_id", how="left", suffixes=("", "_train"), validate="one_to_one")
    if any(not merged[col].equals(merged[col + "_train"]) for col in ("combined_group_id", "thread_id")):
        raise AnnotationError("retrieval example/group is outside the eligible training pool")


def vectorizer(settings):
    return TfidfVectorizer(ngram_range=(1, settings.ngram_max), max_features=settings.max_features,
                           lowercase=True, strip_accents="unicode", sublinear_tf=True)


class IntentBaselines:
    def __init__(self, training, allowed, settings):
        labels = list(training.intent)
        if set(labels) - set(allowed):
            raise AnnotationError("unknown training intent")
        counts = Counter(labels)
        self.majority = min(counts, key=lambda k: (-counts[k], k)) if counts else None
        self.model, self.vectorizer, self.blocker = None, vectorizer(settings), None
        if len(counts) < 2:
            self.blocker = f"Logistic Regression needs at least two classes; found {len(counts)}"
            return
        try:
            matrix = self.vectorizer.fit_transform(training.text)
            with warnings.catch_warnings():
                warnings.simplefilter("error", ConvergenceWarning)
                model = LogisticRegression(C=settings.logistic_c, max_iter=settings.max_iter, random_state=settings.seed)
                model.fit(matrix, labels)
            self.model = model
        except (ValueError, ConvergenceWarning) as exc:
            self.blocker = f"Logistic Regression fitting blocked: {exc}"

    def predict(self, text, kind):
        if kind == "trivial":
            if self.majority is None:
                raise AnnotationError("majority intent unavailable: no eligible labels")
            return self.majority
        if self.model is None:
            raise AnnotationError(self.blocker)
        return str(self.model.predict(self.vectorizer.transform([text]))[0])


class HistoricalRetriever:
    def __init__(self, corpus, settings):
        self.rows = corpus.sort_values("example_id").to_dict("records")
        self.vectorizer, self.matrix = vectorizer(settings), None
        if self.rows:
            try:
                self.matrix = self.vectorizer.fit_transform([
                    feature_text(r["customer_text_redacted"], r["context_texts_redacted"]) for r in self.rows])
            except ValueError as exc:
                if "empty vocabulary" not in str(exc):
                    raise

    def search(self, text, k=3, exclude_ids=(), exclude_groups=()):
        if k < 1 or self.matrix is None:
            return []
        scores = (self.matrix @ self.vectorizer.transform([text]).T).toarray().ravel()
        ranked = sorted(range(len(scores)), key=lambda i: (-scores[i], self.rows[i]["example_id"]))
        hits = []
        for i in ranked:
            row = self.rows[i]
            if scores[i] <= 0 or row["example_id"] in exclude_ids or row["combined_group_id"] in exclude_groups:
                continue
            snippets = [sanitize_historical_reply(s) for s in row["historical_reply_texts_redacted"]]
            hits.append({"example_id": row["example_id"], "evidence_ids": list(row["reference_reply_ids"]),
                         "similarity": float(scores[i]), "sanitized_historical_reply": " ".join(s for s in snippets if s),
                         "sanitization_status": "safe_projection" if any(snippets) else "withheld_no_allowlisted_step",
                         "reply_interpretation": "safe projection of historical text, not a verified resolution"})
            if len(hits) == k:
                break
        return hits


def sanitize_historical_reply(text):
    """Allowlisted projection, never arbitrary copied support prose or links."""
    text = text.casefold().replace("’", "'")
    if re.search(r"\b(refund|charge|ticket|password|email|account|verified|cancel|reset|restore|forward|investigat|check|done|fixed|sorted|we|i)\w*\b", text):
        return ""
    if re.search(r"\b(?:try|please|can you|could you)\b.*\brestart(?:ing)?\b", text):
        return "Try restarting the app or device."
    return ""  # Empty is safer than a copied transaction/account action claim.


class PolicySignals(BaseModel):
    """Explicit case evidence; never populated from a predicted intent or historical reply."""
    model_config = ConfigDict(extra="forbid")
    current_security_incident: bool = False
    payment_investigation: bool = False
    private_account_action: bool = False
    insufficient_context: bool = False
    multiple_human_issues: bool = False
    unavailable_current_fact: bool = False


def route_policy(signals):
    for field, code in (("current_security_incident", "security_or_account_compromise"),
                        ("payment_investigation", "refund_or_payment_investigation"),
                        ("private_account_action", "private_account_investigation_or_action"),
                        ("multiple_human_issues", "multiple_issues_include_human_required"),
                        ("unavailable_current_fact", "unavailable_current_fact_or_policy"),
                        ("insufficient_context", "materially_insufficient_context")):
        if getattr(signals, field):
            return {"decision": "escalate", "reason_code": code, "reasons": [f"Supported case signal: {field}"]}
    return {"decision": "auto_handle", "reason_code": None,
            "reasons": ["Safe clarification only; no human-required issue detected by limited baseline rules."]}


def detect_signals(text):
    """Narrow heuristic adapter, not a complete natural-language policy evaluator."""
    t = text.casefold().replace("’", "'")
    security = bool(re.search(r"(?:my account (?:was|is|has been) (?:hacked|stolen|hijacked)|someone (?:changed|is using) my)", t))
    if re.search(r"(?:used to|previously|last year|already|restored|resolved|recovered|no longer|not hacked)", t):
        security = False
    payment = bool(re.search(r"(?:charged (?:twice|three times)|duplicate charge|unknown charge|want a refund|request a refund)", t))
    if re.search(r"(?:not charged|wasn't charged|no duplicate|not requesting|don't want a refund)", t):
        payment = False
    private = bool(re.search(r"(?:please|can you) (?:restore|delete|change|recover) my (?:account|email|playlist)", t))
    return PolicySignals(current_security_incident=security, payment_investigation=payment,
                         private_account_action=private)


def draft_reply(route, evidence):
    if route["decision"] == "escalate":
        return ACK + " Please contact Spotify's private support channel for help with this case."
    safe = next((e["sanitized_historical_reply"] for e in evidence if e["sanitized_historical_reply"]), "")
    # Only a reversible generic step is projected; no old policy, account action or link.
    return ACK + (" " + safe if safe else "") + " Could you describe what happens and what you have tried?"


def run_demo(config, settings, message, kind="tfidf", context=()):
    train, corpus, allowed, report = load_training(config, settings)
    intent = IntentBaselines(train, allowed, settings)
    report["logistic_fit_blocker"] = intent.blocker
    report["classifier_features"] = len(getattr(intent.vectorizer, "vocabulary_", {}))
    text = feature_text(message, context)
    if not text.strip():
        raise AnnotationError("demo message must contain text")
    predicted = intent.predict(text, kind)
    evidence = HistoricalRetriever(corpus, settings).search(text, settings.retrieval_k) if kind != "trivial" else []
    route = route_policy(detect_signals(text))
    if kind == "trivial":
        route = {"decision": "escalate", "reason_code": None, "reasons": ["Trivial baseline always escalates; not a case-policy judgment."]}
    elif not evidence and route["decision"] != "escalate":
        route = {"decision": "escalate", "reason_code": None, "reasons": ["Agent fallback: no positive-overlap training evidence; not a case-policy label."]}
    result = {"baseline": kind, "baseline_version": "tfidf-baselines-v1", "input_sha256": digest(text),
              "intent": predicted, "draft": ACK if kind == "trivial" else draft_reply(route, evidence),
              **route, "evidence": evidence, "evidence_ids": [i for e in evidence for i in e["evidence_ids"]],
              "training": report}
    return result
