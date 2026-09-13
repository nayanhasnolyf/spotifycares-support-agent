"""UI-independent taxonomy, queue, and human-annotation workflows."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from spotify_cares.config import AppConfig
from spotify_cares.preprocessing import OUTPUT_FILES, validate_split_outputs


ANNOTATION_VERSION = "spotify-annotation-tool-v1"
QUEUE_NAMES = ("training", "development", "golden")
POOL_FOR_QUEUE = {
    "training": "train",
    "development": "development",
    "golden": "test_candidate",
}
QUEUE_COLUMNS = [
    "queue_name",
    "queue_position",
    "example_id",
    "thread_id",
    "combined_group_id",
    "sampling_stratum",
    "selection_rule",
    "candidate_pool_sha256",
    "seed",
]
LABEL_COLUMNS = [
    "example_id",
    "queue_name",
    "status",
    "primary_intent",
    "should_escalate",
    "escalation_reason_code",
    "escalation_explanation",
    "risk_flags_json",
    "ambiguity",
    "annotation_notes",
    "expected_reply_guidance",
    "annotator_id",
    "annotation_timestamp",
    "taxonomy_version",
    "guide_version",
    "taxonomy_sha256",
    "guide_sha256",
    "reference_revealed",
    "reference_revealed_at",
    "revision",
]


class AnnotationError(RuntimeError):
    """Raised when annotation state, inputs, or records are invalid."""


class TaxonomyIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    name: str
    meaning: str
    include: list[str]
    exclude: list[str]
    example_ids: list[str]


class EscalationReason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    meaning: str


class EscalationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_handle_definition: str
    reason_codes: list[EscalationReason]


class TaxonomyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int
    brand: str
    status: Literal["proposed"]
    taxonomy_version: str
    guide_version: str
    primary_intent_rule: str
    intents: list[TaxonomyIntent]
    tie_breakers: list[str]
    risk_flags: list[str]
    escalation_policy: EscalationPolicy

    @model_validator(mode="after")
    def validate_unique_values(self) -> "TaxonomyConfig":
        labels = [item.label for item in self.intents]
        reasons = [item.code for item in self.escalation_policy.reason_codes]
        if len(labels) != len(set(labels)):
            raise ValueError("intent labels must be unique")
        if "other_or_unclear" not in labels:
            raise ValueError("taxonomy must include other_or_unclear")
        if len(reasons) != len(set(reasons)):
            raise ValueError("escalation reason codes must be unique")
        if len(self.risk_flags) != len(set(self.risk_flags)):
            raise ValueError("risk flags must be unique")
        return self


class AnnotationRecord(BaseModel):
    """One human-authored record. Blank labels are allowed only when skipped."""

    model_config = ConfigDict(extra="forbid")
    example_id: str
    queue_name: Literal["training", "development", "golden"]
    status: Literal["judgment_saved", "complete", "skipped"]
    primary_intent: str | None = None
    should_escalate: Literal["yes", "no"] | None = None
    escalation_reason_code: str | None = None
    escalation_explanation: str | None = None
    risk_flags: tuple[str, ...] = ()
    ambiguity: Literal["clear", "ambiguous"] | None = None
    annotation_notes: str = ""
    expected_reply_guidance: str = ""
    annotator_id: str
    annotation_timestamp: datetime
    taxonomy_version: str
    guide_version: str
    taxonomy_sha256: str
    guide_sha256: str
    reference_revealed: bool = False
    reference_revealed_at: datetime | None = None
    revision: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_required_fields(self) -> "AnnotationRecord":
        if not self.annotator_id.strip():
            raise ValueError("annotator_id is required")
        if self.annotation_timestamp.tzinfo is None:
            raise ValueError("annotation_timestamp must include a timezone")
        if self.status != "skipped":
            if not self.primary_intent:
                raise ValueError("primary_intent is required")
            if not self.should_escalate:
                raise ValueError("should_escalate is required")
            if not self.ambiguity:
                raise ValueError("ambiguity is required")
            if self.should_escalate == "yes":
                if not self.escalation_reason_code:
                    raise ValueError("escalation_reason_code is required when escalating")
                if not (self.escalation_explanation or "").strip():
                    raise ValueError("escalation_explanation is required when escalating")
        if self.status == "complete":
            if not self.reference_revealed:
                raise ValueError("reference must be revealed before completion")
            if not self.expected_reply_guidance.strip():
                raise ValueError("expected_reply_guidance is required for completion")
        if self.reference_revealed and self.reference_revealed_at is None:
            raise ValueError("reference_revealed_at is required after revealing")
        return self


@dataclass(frozen=True)
class AnnotationPaths:
    root: Path
    queues: Path
    labels: Path
    audit: Path
    state: Path
    manifest: Path
    taxonomy_examples: Path


def annotation_paths(root: Path) -> AnnotationPaths:
    return AnnotationPaths(
        root=root,
        queues=root / "queues",
        labels=root / "labels",
        audit=root / "audit",
        state=root / "state" / "guide_state.json",
        manifest=root / "annotation_manifest.json",
        taxonomy_examples=root / "taxonomy_examples.parquet",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_taxonomy(path: Path) -> TaxonomyConfig:
    with path.open(encoding="utf-8") as handle:
        return TaxonomyConfig.model_validate(yaml.safe_load(handle))


def current_contract(config: AppConfig) -> dict[str, str]:
    taxonomy = load_taxonomy(config.annotation.taxonomy_path)
    return {
        "taxonomy_version": taxonomy.taxonomy_version,
        "guide_version": taxonomy.guide_version,
        "taxonomy_sha256": sha256_file(config.annotation.taxonomy_path),
        "guide_sha256": sha256_file(config.annotation.guide_path),
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".parquet", dir=path.parent)
    os.close(handle)
    try:
        frame.to_parquet(temporary, index=False)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _stable_rank(seed: int, namespace: str, example_id: str) -> str:
    return hashlib.sha256(f"{seed}|{namespace}|{example_id}".encode()).hexdigest()


def _as_list(value: object) -> list[Any]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def verify_preprocessing_prerequisites(config: AppConfig) -> dict[str, Any]:
    """Verify the Stage 3 manifest hashes and leakage checks before sampling."""

    split_dir = config.annotation.split_dir
    manifest_path = split_dir / OUTPUT_FILES["manifest"]
    if not manifest_path.is_file():
        raise AnnotationError(f"missing Stage 3 manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_hashes = manifest.get("output_sha256", {})
    missing: list[str] = []
    mismatched: list[str] = []
    checked: dict[str, str] = {}
    for key, expected in expected_hashes.items():
        filename = OUTPUT_FILES.get(key)
        if not filename:
            mismatched.append(f"unknown manifest output key: {key}")
            continue
        path = split_dir / filename
        if not path.is_file():
            missing.append(str(path))
            continue
        actual = sha256_file(path)
        checked[key] = actual
        if actual != expected:
            mismatched.append(f"{key}: expected {expected}, got {actual}")
    required = {
        "train_inputs",
        "development_inputs",
        "test_candidate_inputs",
        "train_references",
        "development_references",
        "test_candidate_references",
        "discovery",
    }
    absent_keys = sorted(required - set(expected_hashes))
    if missing or mismatched or absent_keys:
        details = [*(f"missing file: {item}" for item in missing), *mismatched]
        details.extend(f"missing manifest hash: {item}" for item in absent_keys)
        raise AnnotationError("Stage 3 hash verification failed: " + "; ".join(details))
    leakage = validate_split_outputs(
        split_dir, config.preprocessing.relevant_tweets_path
    )
    return {"hashes_verified": len(checked), "leakage_checks": leakage, "manifest": manifest}


_COVERAGE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("security", re.compile(r"\b(hack|hijack|compromis|not me|unauthori[sz]|stolen)")),
    ("billing", re.compile(r"\b(charge|refund|payment|card|bill|price|paid)")),
    ("membership", re.compile(r"\b(premium|family plan|student|subscription|trial|invite)")),
    ("account", re.compile(r"\b(log ?in|password|username|account|email address|facebook)")),
    ("catalog", re.compile(r"\b(album|artist|song|track|catalog|library)\b.*\b(missing|removed|available|add|wrong)")),
    ("library_playlist", re.compile(r"\b(playlist|download|saved|library|10,?000|queue)")),
    ("playback", re.compile(r"\b(play|playing|shuffle|skip|audio|sound|pause|autoplay)")),
    ("app_device", re.compile(r"\b(app|iphone|ios|android|desktop|web player|bluetooth|speaker|crash|bug)")),
    ("feature_market", re.compile(r"\b(feature|support|available in|country|watch|fitbit|siri|notification)")),
)


def _coverage_bucket(row: pd.Series) -> str:
    text = str(row["customer_text_redacted"]).lower()
    for name, pattern in _COVERAGE_PATTERNS:
        if pattern.search(text):
            return name
    if len(text.strip()) <= 40 or not _as_list(row.get("context_tweet_ids")):
        return "short_or_context_limited"
    return "general"


_SECURITY_PATTERN = re.compile(
    r"\b(hack(?:ed|er)?|hijack(?:ed)?|compromis(?:e|ed)|unauthori[sz]ed|not me|someone (?:has|got|changed|signed)|stolen account)\b"
)
_PAYMENT_DISPUTE_PATTERN = re.compile(
    r"\b(refund|charged? (?:me )?(?:twice|double|extra|more)|unknown charge|fraudulent charge|never signed up|account i don.t have|money back)\b"
)


def challenge_flags(row: pd.Series) -> tuple[str, ...]:
    """Observable sampling flags fixed before held-out cases are selected."""

    text = str(row["customer_text_redacted"]).strip().lower()
    flags: list[str] = []
    if len(text) <= 40:
        flags.append("very_short_message")
    if not _as_list(row.get("context_tweet_ids")):
        flags.append("missing_preceding_context")
    if text.count("?") >= 2:
        flags.append("multiple_question_clauses")
    if _SECURITY_PATTERN.search(text):
        flags.append("security_related_wording")
    if _PAYMENT_DISPUTE_PATTERN.search(text):
        flags.append("account_specific_payment_dispute_wording")
    return tuple(flags)


def _eligible_ranked(
    frame: pd.DataFrame,
    *,
    seed: int,
    namespace: str,
    used_threads: set[str] | None = None,
    used_groups: set[str] | None = None,
) -> list[pd.Series]:
    threads = used_threads or set()
    groups = used_groups or set()
    rows = sorted(
        (row for _, row in frame.iterrows()),
        key=lambda row: _stable_rank(seed, namespace, str(row["example_id"])),
    )
    selected: list[pd.Series] = []
    local_threads = set(threads)
    local_groups = set(groups)
    for row in rows:
        thread = str(row["thread_id"])
        group = str(row["combined_group_id"])
        if thread in local_threads or group in local_groups:
            continue
        selected.append(row)
        local_threads.add(thread)
        local_groups.add(group)
    return selected


def _queue_frame(
    rows: list[pd.Series],
    *,
    queue_name: str,
    strata: list[str],
    rules: list[str],
    pool_hash: str,
    seed: int,
) -> pd.DataFrame:
    values = []
    for position, (row, stratum, rule) in enumerate(zip(rows, strata, rules), start=1):
        values.append(
            {
                "queue_name": queue_name,
                "queue_position": position,
                "example_id": str(row["example_id"]),
                "thread_id": str(row["thread_id"]),
                "combined_group_id": str(row["combined_group_id"]),
                "sampling_stratum": stratum,
                "selection_rule": rule,
                "candidate_pool_sha256": pool_hash,
                "seed": seed,
            }
        )
    return pd.DataFrame(values, columns=QUEUE_COLUMNS)


def sample_training_queue(frame: pd.DataFrame, size: int, seed: int, pool_hash: str) -> pd.DataFrame:
    working = frame.copy()
    working["_coverage"] = working.apply(_coverage_bucket, axis=1)
    buckets = list(dict.fromkeys(name for name, _ in _COVERAGE_PATTERNS)) + [
        "short_or_context_limited",
        "general",
    ]
    per_bucket = max(1, size // len(buckets))
    chosen: list[pd.Series] = []
    strata: list[str] = []
    used_threads: set[str] = set()
    used_groups: set[str] = set()
    for bucket in buckets:
        candidates = _eligible_ranked(
            working[working["_coverage"] == bucket],
            seed=seed,
            namespace=f"training:{bucket}",
            used_threads=used_threads,
            used_groups=used_groups,
        )
        for row in candidates[:per_bucket]:
            chosen.append(row)
            strata.append(f"coverage:{bucket}")
            used_threads.add(str(row["thread_id"]))
            used_groups.add(str(row["combined_group_id"]))
    if len(chosen) < size:
        fill = _eligible_ranked(
            working,
            seed=seed,
            namespace="training:remainder",
            used_threads=used_threads,
            used_groups=used_groups,
        )
        for row in fill[: size - len(chosen)]:
            chosen.append(row)
            strata.append("coverage:remainder")
    if len(chosen) < size:
        raise AnnotationError(f"training pool supports only {len(chosen)} unique selections; requested {size}")
    return _queue_frame(
        chosen[:size],
        queue_name="training",
        strata=strata[:size],
        rules=["topic-proxy coverage enrichment; not an intent label"] * size,
        pool_hash=pool_hash,
        seed=seed,
    )


def sample_uniform_queue(
    frame: pd.DataFrame, *, queue_name: str, size: int, seed: int, pool_hash: str
) -> pd.DataFrame:
    rows = _eligible_ranked(frame, seed=seed, namespace=f"{queue_name}:uniform")
    if len(rows) < size:
        raise AnnotationError(f"{queue_name} pool supports only {len(rows)} unique selections; requested {size}")
    return _queue_frame(
        rows[:size],
        queue_name=queue_name,
        strata=["random"] * size,
        rules=["deterministic hash-ranked random sample"] * size,
        pool_hash=pool_hash,
        seed=seed,
    )


def sample_golden_queue(
    frame: pd.DataFrame,
    *,
    random_size: int,
    challenge_size: int,
    seed: int,
    pool_hash: str,
) -> pd.DataFrame:
    random_rows = _eligible_ranked(frame, seed=seed, namespace="golden:random")[:random_size]
    if len(random_rows) < random_size:
        raise AnnotationError(f"golden random stratum shortfall: {len(random_rows)} of {random_size}")
    used_threads = {str(row["thread_id"]) for row in random_rows}
    used_groups = {str(row["combined_group_id"]) for row in random_rows}
    flagged = frame.copy()
    flagged["_flags"] = flagged.apply(challenge_flags, axis=1)
    flag_order = [
        "very_short_message",
        "missing_preceding_context",
        "multiple_question_clauses",
        "security_related_wording",
        "account_specific_payment_dispute_wording",
    ]
    lists = {
        flag: _eligible_ranked(
            flagged[flagged["_flags"].map(lambda values, item=flag: item in values)],
            seed=seed,
            namespace=f"golden:challenge:{flag}",
        )
        for flag in flag_order
    }
    offsets = {flag: 0 for flag in flag_order}
    challenge_rows: list[pd.Series] = []
    challenge_strata: list[str] = []
    while len(challenge_rows) < challenge_size:
        progress = False
        for flag in flag_order:
            candidates = lists[flag]
            while offsets[flag] < len(candidates):
                row = candidates[offsets[flag]]
                offsets[flag] += 1
                thread = str(row["thread_id"])
                group = str(row["combined_group_id"])
                if thread in used_threads or group in used_groups:
                    continue
                challenge_rows.append(row)
                challenge_strata.append(f"challenge:{flag}")
                used_threads.add(thread)
                used_groups.add(group)
                progress = True
                break
            if len(challenge_rows) == challenge_size:
                break
        if not progress:
            break
    if len(challenge_rows) < challenge_size:
        raise AnnotationError(
            f"golden challenge stratum shortfall: {len(challenge_rows)} of {challenge_size} "
            "after thread/group separation"
        )
    rows = random_rows + challenge_rows
    strata = ["random"] * random_size + challenge_strata
    rules = ["deterministic hash-ranked random sample"] * random_size + [
        "deterministic round-robin over predeclared observable challenge flags"
    ] * challenge_size
    return _queue_frame(
        rows,
        queue_name="golden",
        strata=strata,
        rules=rules,
        pool_hash=pool_hash,
        seed=seed,
    )


def validate_queues(
    queues: dict[str, pd.DataFrame], *, golden_random_size: int, golden_challenge_size: int
) -> dict[str, Any]:
    issues: list[str] = []
    for name in QUEUE_NAMES:
        frame = queues[name]
        missing = set(QUEUE_COLUMNS) - set(frame.columns)
        if missing:
            issues.append(f"{name} queue missing columns: {sorted(missing)}")
        if frame["example_id"].duplicated().any():
            issues.append(f"{name} queue has duplicate example IDs")
        if frame["thread_id"].duplicated().any():
            issues.append(f"{name} queue has duplicate conversation IDs")
        if frame["combined_group_id"].duplicated().any():
            issues.append(f"{name} queue has duplicate combined-group IDs")
    for left, right in (("training", "development"), ("training", "golden"), ("development", "golden")):
        overlap = set(queues[left]["example_id"]) & set(queues[right]["example_id"])
        if overlap:
            issues.append(f"example IDs overlap {left} and {right}")
    golden = queues["golden"]
    random_count = int((golden["sampling_stratum"] == "random").sum())
    challenge_count = int(golden["sampling_stratum"].str.startswith("challenge:").sum())
    if random_count != golden_random_size or challenge_count != golden_challenge_size:
        issues.append(
            f"golden strata are random={random_count}, challenge={challenge_count}; "
            f"expected {golden_random_size}/{golden_challenge_size}"
        )
    if issues:
        raise AnnotationError("queue validation failed: " + "; ".join(issues))
    return {
        "queue_sizes": {name: len(frame) for name, frame in queues.items()},
        "golden_random": random_count,
        "golden_challenge": challenge_count,
        "cross_queue_example_overlap": 0,
    }


def validate_queue_membership(
    queues: dict[str, pd.DataFrame], pools: dict[str, pd.DataFrame]
) -> None:
    """Reject queue IDs or grouping metadata that do not match their Stage 3 pool."""

    issues: list[str] = []
    for queue_name, queue in queues.items():
        pool_name = POOL_FOR_QUEUE[queue_name]
        pool = pools[pool_name].set_index("example_id", drop=False)
        for row in queue.itertuples(index=False):
            if row.example_id not in pool.index:
                issues.append(f"{queue_name} example {row.example_id} is not in {pool_name}")
                continue
            source = pool.loc[row.example_id]
            if str(source["thread_id"]) != str(row.thread_id):
                issues.append(f"{queue_name} thread mismatch for {row.example_id}")
            if str(source["combined_group_id"]) != str(row.combined_group_id):
                issues.append(f"{queue_name} combined-group mismatch for {row.example_id}")
    if issues:
        raise AnnotationError("queue membership validation failed: " + "; ".join(issues))


def validate_queue_provenance(
    config: AppConfig, queues: dict[str, pd.DataFrame]
) -> None:
    """Verify the stored pool fingerprint, seed, name, and queue positions."""

    issues: list[str] = []
    for queue_name, queue in queues.items():
        pool_name = POOL_FOR_QUEUE[queue_name]
        pool_path = config.annotation.split_dir / OUTPUT_FILES[f"{pool_name}_inputs"]
        expected_hash = sha256_file(pool_path)
        if set(queue["candidate_pool_sha256"].astype(str)) != {expected_hash}:
            issues.append(f"{queue_name} candidate-pool hash does not match {pool_path}")
        if set(queue["seed"].astype(int)) != {config.project.random_seed}:
            issues.append(f"{queue_name} seed does not match project configuration")
        if set(queue["queue_name"].astype(str)) != {queue_name}:
            issues.append(f"{queue_name} queue_name values are invalid")
        if list(queue["queue_position"].astype(int)) != list(range(1, len(queue) + 1)):
            issues.append(f"{queue_name} positions are not contiguous from 1")
    if issues:
        raise AnnotationError("queue provenance validation failed: " + "; ".join(issues))


def prepare_annotation_queues(config: AppConfig) -> dict[str, Any]:
    prerequisite = verify_preprocessing_prerequisites(config)
    taxonomy = load_taxonomy(config.annotation.taxonomy_path)
    paths = annotation_paths(config.annotation.output_dir)
    paths.queues.mkdir(parents=True, exist_ok=True)
    paths.labels.mkdir(parents=True, exist_ok=True)
    paths.audit.mkdir(parents=True, exist_ok=True)
    previous_manifest = (
        json.loads(paths.manifest.read_text(encoding="utf-8"))
        if paths.manifest.is_file()
        else {}
    )
    previous_training = (
        pd.read_parquet(paths.queues / "training.parquet")
        if (paths.queues / "training.parquet").is_file()
        else None
    )
    pools = {
        split: pd.read_parquet(config.annotation.split_dir / OUTPUT_FILES[f"{split}_inputs"])
        for split in ("train", "development", "test_candidate")
    }
    hashes = prerequisite["manifest"]["output_sha256"]
    queues = {
        "training": sample_training_queue(
            pools["train"],
            config.annotation.training_queue_size,
            config.project.random_seed,
            hashes["train_inputs"],
        ),
        "development": sample_uniform_queue(
            pools["development"],
            queue_name="development",
            size=config.annotation.development_queue_size,
            seed=config.project.random_seed,
            pool_hash=hashes["development_inputs"],
        ),
        "golden": sample_golden_queue(
            pools["test_candidate"],
            random_size=config.annotation.golden_random_size,
            challenge_size=config.annotation.golden_challenge_size,
            seed=config.project.random_seed,
            pool_hash=hashes["test_candidate_inputs"],
        ),
    }
    initial_size = config.annotation.training_queue_size
    if previous_training is not None and len(previous_training) > initial_size:
        previous_initial = previous_training.iloc[:initial_size]
        if list(previous_initial["example_id"].astype(str)) != list(
            queues["training"]["example_id"].astype(str)
        ):
            raise AnnotationError(
                "refusing to replace the labelled initial training queue; its deterministic IDs changed"
            )
        queues["training"] = pd.concat(
            [queues["training"], previous_training.iloc[initial_size:]], ignore_index=True
        )
    validation = validate_queues(
        queues,
        golden_random_size=config.annotation.golden_random_size,
        golden_challenge_size=config.annotation.golden_challenge_size,
    )
    validate_queue_membership(queues, pools)
    validate_queue_provenance(config, queues)
    for name, frame in queues.items():
        _atomic_parquet(frame, paths.queues / f"{name}.parquet")

    discovery = pd.read_parquet(config.annotation.split_dir / OUTPUT_FILES["discovery"])
    label_for_id = {
        example_id: intent.label
        for intent in taxonomy.intents
        for example_id in intent.example_ids
    }
    missing_examples = sorted(set(label_for_id) - set(discovery["example_id"].astype(str)))
    if missing_examples:
        raise AnnotationError(f"taxonomy example IDs missing from training discovery sample: {missing_examples}")
    examples = discovery[discovery["example_id"].isin(label_for_id)].copy()
    examples.insert(1, "proposed_intent", examples["example_id"].map(label_for_id))
    _atomic_parquet(examples, paths.taxonomy_examples)

    contract = current_contract(config)
    existing_state = (
        json.loads(paths.state.read_text(encoding="utf-8"))
        if paths.state.is_file()
        else None
    )
    if existing_state is None or existing_state.get("status") == "proposed":
        _atomic_json(
            paths.state,
            {
                "status": "proposed",
                **contract,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": "system",
                "note": "Development and golden annotation remain locked pending human review and freeze.",
            },
        )
    manifest = {
        "annotation_tool_version": ANNOTATION_VERSION,
        "status": {
            "tooling": "ready",
            "queues": "prepared",
            "human_annotations": "not_started",
            "guide": json.loads(paths.state.read_text(encoding="utf-8"))["status"],
        },
        "contract": contract,
        "seed": config.project.random_seed,
        "queue_validation": validation,
        "training_sampling": {
            "method": "topic-proxy coverage enrichment plus deterministic remainder",
            "natural_frequency_claim": False,
            "pilot_size": config.annotation.training_pilot_size,
            "extensions": previous_manifest.get("training_sampling", {}).get(
                "extensions", []
            ),
        },
        "golden_sampling": {
            "random_target": config.annotation.golden_random_size,
            "challenge_target": config.annotation.golden_challenge_size,
            "challenge_rules_declared_in": "spotify_cares.annotation.challenge_flags",
            "held_out_text_manually_inspected_during_design": False,
        },
        "candidate_pool_sha256": {
            "training": hashes["train_inputs"],
            "development": hashes["development_inputs"],
            "golden": hashes["test_candidate_inputs"],
        },
        "queue_sha256": {
            name: sha256_file(paths.queues / f"{name}.parquet") for name in QUEUE_NAMES
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_json(paths.manifest, manifest)
    return manifest


def extend_training_queue(
    config: AppConfig,
    *,
    batch_name: str,
    size: int,
    coverage_bucket: str | None = None,
) -> dict[str, Any]:
    """Append a reproducible training-only batch without replacing earlier IDs."""

    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", batch_name):
        raise AnnotationError("batch_name must use 1-32 lowercase letters, numbers, '_' or '-'")
    if size <= 0:
        raise AnnotationError("extension size must be positive")
    allowed_buckets = {name for name, _ in _COVERAGE_PATTERNS} | {
        "short_or_context_limited",
        "general",
    }
    if coverage_bucket is not None and coverage_bucket not in allowed_buckets:
        raise AnnotationError(
            f"unknown coverage bucket {coverage_bucket!r}; choose from {sorted(allowed_buckets)}"
        )

    prerequisite = verify_preprocessing_prerequisites(config)
    paths = annotation_paths(config.annotation.output_dir)
    if not paths.manifest.is_file() or not (paths.queues / "training.parquet").is_file():
        raise AnnotationError("prepare the initial annotation queues before extending training")
    manifest = json.loads(paths.manifest.read_text(encoding="utf-8"))
    extensions = list(manifest.get("training_sampling", {}).get("extensions", []))
    if any(item.get("batch_name") == batch_name for item in extensions):
        raise AnnotationError(f"training extension {batch_name!r} already exists")

    training = pd.read_parquet(paths.queues / "training.parquet")
    pool_path = config.annotation.split_dir / OUTPUT_FILES["train_inputs"]
    pool = pd.read_parquet(pool_path)
    used_threads = set(training["thread_id"].astype(str))
    used_groups = set(training["combined_group_id"].astype(str))
    available = pool[
        ~pool["thread_id"].astype(str).isin(used_threads)
        & ~pool["combined_group_id"].astype(str).isin(used_groups)
    ].copy()
    if coverage_bucket is not None:
        available["_coverage"] = available.apply(_coverage_bucket, axis=1)
        available = available[available["_coverage"] == coverage_bucket]
    rows = _eligible_ranked(
        available,
        seed=config.project.random_seed,
        namespace=f"training-extension:{batch_name}:{coverage_bucket or 'all'}",
    )
    if len(rows) < size:
        raise AnnotationError(
            f"training extension shortfall: {len(rows)} eligible unique records for requested {size}"
        )
    stratum = f"extension:{batch_name}:{coverage_bucket or 'all'}"
    rule = (
        f"training-only deterministic hash rank within observable proxy {coverage_bucket}"
        if coverage_bucket
        else "training-only deterministic hash-ranked extension"
    )
    extension = _queue_frame(
        rows[:size],
        queue_name="training",
        strata=[stratum] * size,
        rules=[rule] * size,
        pool_hash=prerequisite["manifest"]["output_sha256"]["train_inputs"],
        seed=config.project.random_seed,
    )
    extension["queue_position"] += len(training)
    combined = pd.concat([training, extension], ignore_index=True)
    queues = {
        "training": combined,
        "development": pd.read_parquet(paths.queues / "development.parquet"),
        "golden": pd.read_parquet(paths.queues / "golden.parquet"),
    }
    validation = validate_queues(
        queues,
        golden_random_size=config.annotation.golden_random_size,
        golden_challenge_size=config.annotation.golden_challenge_size,
    )
    pools = {
        "train": pool,
        "development": pd.read_parquet(
            config.annotation.split_dir / OUTPUT_FILES["development_inputs"]
        ),
        "test_candidate": pd.read_parquet(
            config.annotation.split_dir / OUTPUT_FILES["test_candidate_inputs"]
        ),
    }
    validate_queue_membership(queues, pools)
    validate_queue_provenance(config, queues)
    _atomic_parquet(combined, paths.queues / "training.parquet")

    extension_record = {
        "batch_name": batch_name,
        "size": size,
        "coverage_bucket": coverage_bucket,
        "selection_rule": rule,
        "first_queue_position": len(training) + 1,
        "last_queue_position": len(combined),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    extensions.append(extension_record)
    manifest["queue_validation"] = validation
    manifest.setdefault("training_sampling", {})["extensions"] = extensions
    manifest.setdefault("queue_sha256", {})["training"] = sha256_file(
        paths.queues / "training.parquet"
    )
    _atomic_json(paths.manifest, manifest)
    _append_jsonl(
        paths.audit / "queue_changes.jsonl",
        {"event": "training_queue_extended", **extension_record},
    )
    return extension_record


def load_guide_state(config: AppConfig) -> dict[str, Any]:
    path = annotation_paths(config.annotation.output_dir).state
    if not path.is_file():
        raise AnnotationError("annotation queues/state are not prepared; run prepare-annotations")
    return json.loads(path.read_text(encoding="utf-8"))


def assert_queue_access(config: AppConfig, queue_name: str) -> None:
    if queue_name not in QUEUE_NAMES:
        raise AnnotationError(f"unknown queue: {queue_name}")
    if queue_name == "training":
        return
    state = load_guide_state(config)
    if state.get("status") != "frozen":
        raise AnnotationError("development and golden queues are locked until the guide is frozen")
    contract = current_contract(config)
    if any(state.get(key) != value for key, value in contract.items()):
        raise AnnotationError("the frozen guide no longer matches current files; human review is required")


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def freeze_guide(
    config: AppConfig,
    *,
    annotator_id: str,
    confirm_taxonomy_version: str,
    confirm_guide_version: str,
    acknowledge_prior_version_pilot: bool = False,
) -> dict[str, Any]:
    if not annotator_id.strip():
        raise AnnotationError("annotator_id is required")
    paths = annotation_paths(config.annotation.output_dir)
    if not paths.manifest.is_file():
        raise AnnotationError("prepare annotation queues before freezing the guide")
    contract = current_contract(config)
    if confirm_taxonomy_version != contract["taxonomy_version"]:
        raise AnnotationError("confirmed taxonomy version does not match the current taxonomy")
    if confirm_guide_version != contract["guide_version"]:
        raise AnnotationError("confirmed guide version does not match the current guide")
    pilot = training_pilot_status(config)
    accepted_prior_pilot = (
        acknowledge_prior_version_pilot
        and pilot["missing"] == 0
        and pilot["incomplete"] == 0
    )
    if not pilot["ready_to_freeze"] and not accepted_prior_pilot:
        raise AnnotationError(
            "training pilot is not ready: "
            f"{pilot['complete_current']}/{pilot['required']} current complete annotations; "
            f"missing={pilot['missing']}, incomplete={pilot['incomplete']}, stale={pilot['stale']}"
        )
    previous = load_guide_state(config)
    if previous.get("status") == "frozen":
        raise AnnotationError("guide is already frozen; no state change was made")
    state = {
        "status": "frozen",
        **contract,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": annotator_id.strip(),
        "note": "Human-confirmed freeze; development and golden annotation unlocked.",
        "pilot_at_approval": pilot,
        "prior_version_pilot_acknowledged": acknowledge_prior_version_pilot,
        "coverage_caveat": "A complete pilot does not establish broad coverage or independent human labelling; old annotation versions are preserved.",
    }
    _atomic_json(paths.state, state)
    _append_jsonl(
        paths.audit / "guide_state.jsonl",
        {"event": "guide_frozen", "before": previous, "after": state},
    )
    return state


def training_pilot_status(config: AppConfig) -> dict[str, Any]:
    """Report whether the first configured training items are complete and current."""

    queue_path = _queue_path(config, "training")
    if not queue_path.is_file():
        raise AnnotationError("training queue is not prepared")
    queue = pd.read_parquet(queue_path).sort_values("queue_position")
    required = min(config.annotation.training_pilot_size, len(queue))
    pilot_ids = list(queue.iloc[:required]["example_id"].astype(str))
    records = AnnotationStore(config, "training", enforce_access=False).load()
    contract = current_contract(config)
    missing = sum(example_id not in records for example_id in pilot_ids)
    incomplete = sum(
        example_id in records and records[example_id].status != "complete"
        for example_id in pilot_ids
    )
    stale = sum(
        example_id in records
        and any(getattr(records[example_id], key) != value for key, value in contract.items())
        for example_id in pilot_ids
    )
    complete_current = sum(
        example_id in records
        and records[example_id].status == "complete"
        and not any(
            getattr(records[example_id], key) != value for key, value in contract.items()
        )
        for example_id in pilot_ids
    )
    return {
        "required": required,
        "complete_current": complete_current,
        "missing": missing,
        "incomplete": incomplete,
        "stale": stale,
        "ready_to_freeze": complete_current == required,
    }


def _queue_path(config: AppConfig, queue_name: str) -> Path:
    return annotation_paths(config.annotation.output_dir).queues / f"{queue_name}.parquet"


def load_queue(config: AppConfig, queue_name: str) -> pd.DataFrame:
    assert_queue_access(config, queue_name)
    path = _queue_path(config, queue_name)
    if not path.is_file():
        raise AnnotationError(f"queue is not prepared: {path}")
    return pd.read_parquet(path)


class AnnotationStore:
    """CSV label persistence with atomic rewrites and append-only edit audit."""

    def __init__(self, config: AppConfig, queue_name: str, *, enforce_access: bool = True):
        if enforce_access:
            assert_queue_access(config, queue_name)
        self.config = config
        self.queue_name = queue_name
        self.paths = annotation_paths(config.annotation.output_dir)
        self.label_path = self.paths.labels / f"{queue_name}.csv"
        self.audit_path = self.paths.audit / f"{queue_name}.jsonl"
        self.taxonomy = load_taxonomy(config.annotation.taxonomy_path)
        self.contract = current_contract(config)
        queue_path = _queue_path(config, queue_name)
        if not queue_path.is_file():
            raise AnnotationError(f"queue is not prepared: {queue_path}")
        self.members = set(pd.read_parquet(queue_path)["example_id"].astype(str))

    def load(self) -> dict[str, AnnotationRecord]:
        if not self.label_path.is_file():
            return {}
        frame = pd.read_csv(self.label_path, dtype=str, keep_default_na=False)
        if frame["example_id"].duplicated().any():
            duplicates = sorted(frame.loc[frame["example_id"].duplicated(), "example_id"].unique())
            raise AnnotationError(f"duplicate annotation records: {duplicates}")
        records: dict[str, AnnotationRecord] = {}
        for row in frame.to_dict("records"):
            value = _record_from_csv(row)
            self._validate_contract_values(value)
            records[value.example_id] = value
        return records

    def _validate_contract_values(self, record: AnnotationRecord) -> None:
        if record.example_id not in self.members:
            raise AnnotationError(f"example {record.example_id} is not in the {self.queue_name} queue")
        if record.queue_name != self.queue_name:
            raise AnnotationError("annotation queue_name does not match its label file")
        labels = {item.label for item in self.taxonomy.intents}
        reasons = {item.code for item in self.taxonomy.escalation_policy.reason_codes}
        flags = set(self.taxonomy.risk_flags)
        if record.primary_intent and record.primary_intent not in labels:
            raise AnnotationError(f"invalid intent label: {record.primary_intent}")
        if record.escalation_reason_code and record.escalation_reason_code not in reasons:
            raise AnnotationError(f"invalid escalation reason: {record.escalation_reason_code}")
        unknown_flags = set(record.risk_flags) - flags
        if unknown_flags:
            raise AnnotationError(f"invalid risk flags: {sorted(unknown_flags)}")

    def _write(self, records: dict[str, AnnotationRecord]) -> None:
        self.label_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [_record_to_csv(records[key]) for key in sorted(records)]
        frame = pd.DataFrame(rows, columns=LABEL_COLUMNS)
        handle, temporary = tempfile.mkstemp(prefix=f".{self.label_path.name}.", suffix=".csv", dir=self.label_path.parent)
        os.close(handle)
        try:
            frame.to_csv(temporary, index=False, lineterminator="\n")
            Path(temporary).replace(self.label_path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def save(self, record: AnnotationRecord, event: str) -> AnnotationRecord:
        self._validate_contract_values(record)
        records = self.load()
        before = records.get(record.example_id)
        if before and record.revision <= before.revision:
            record = record.model_copy(update={"revision": before.revision + 1})
        records[record.example_id] = record
        self._write(records)
        _append_jsonl(
            self.audit_path,
            {
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "example_id": record.example_id,
                "revision": record.revision,
                "reference_was_revealed_before_edit": bool(before and before.reference_revealed),
                "before": before.model_dump(mode="json") if before else None,
                "after": record.model_dump(mode="json"),
            },
        )
        return record


def _record_to_csv(record: AnnotationRecord) -> dict[str, Any]:
    value = record.model_dump(mode="json")
    value["risk_flags_json"] = json.dumps(value.pop("risk_flags"), ensure_ascii=False)
    value["reference_revealed"] = "true" if record.reference_revealed else "false"
    for key in (
        "primary_intent",
        "should_escalate",
        "escalation_reason_code",
        "escalation_explanation",
        "ambiguity",
        "reference_revealed_at",
    ):
        if value.get(key) is None:
            value[key] = ""
    return value


def _record_from_csv(row: dict[str, str]) -> AnnotationRecord:
    value: dict[str, Any] = dict(row)
    value["risk_flags"] = tuple(json.loads(value.pop("risk_flags_json") or "[]"))
    value["reference_revealed"] = value["reference_revealed"].lower() == "true"
    value["revision"] = int(value["revision"])
    for key in (
        "primary_intent",
        "should_escalate",
        "escalation_reason_code",
        "escalation_explanation",
        "ambiguity",
        "reference_revealed_at",
    ):
        if value.get(key) == "":
            value[key] = None
    return AnnotationRecord.model_validate(value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def save_initial_judgment(
    config: AppConfig,
    *,
    queue_name: str,
    example_id: str,
    primary_intent: str,
    should_escalate: Literal["yes", "no"],
    escalation_reason_code: str | None,
    escalation_explanation: str | None,
    risk_flags: tuple[str, ...],
    ambiguity: Literal["clear", "ambiguous"],
    annotation_notes: str,
    annotator_id: str,
) -> AnnotationRecord:
    store = AnnotationStore(config, queue_name)
    previous = store.load().get(example_id)
    contract = store.contract
    record = AnnotationRecord(
        example_id=example_id,
        queue_name=queue_name,
        status="complete" if previous and previous.status == "complete" else "judgment_saved",
        primary_intent=primary_intent or None,
        should_escalate=should_escalate or None,
        escalation_reason_code=escalation_reason_code or None,
        escalation_explanation=escalation_explanation or None,
        risk_flags=risk_flags,
        ambiguity=ambiguity or None,
        annotation_notes=annotation_notes,
        expected_reply_guidance=previous.expected_reply_guidance if previous else "",
        annotator_id=annotator_id,
        annotation_timestamp=_now(),
        **contract,
        reference_revealed=previous.reference_revealed if previous else False,
        reference_revealed_at=previous.reference_revealed_at if previous else None,
        revision=(previous.revision + 1) if previous else 1,
    )
    return store.save(record, "initial_judgment_saved" if previous is None else "judgment_edited")


def reveal_reference(config: AppConfig, queue_name: str, example_id: str) -> AnnotationRecord:
    store = AnnotationStore(config, queue_name)
    records = store.load()
    if example_id not in records or records[example_id].status == "skipped":
        raise AnnotationError("save the initial intent and escalation judgment before revealing the reference")
    record = records[example_id]
    if record.reference_revealed:
        return record
    updated = record.model_copy(
        update={"reference_revealed": True, "reference_revealed_at": _now(), "revision": record.revision + 1}
    )
    return store.save(updated, "historical_reference_revealed")


def save_expected_guidance(
    config: AppConfig, queue_name: str, example_id: str, guidance: str
) -> AnnotationRecord:
    store = AnnotationStore(config, queue_name)
    records = store.load()
    if example_id not in records or not records[example_id].reference_revealed:
        raise AnnotationError("reveal the historical reference only after saving initial judgments")
    record = records[example_id]
    updated = record.model_copy(
        update={
            "status": "complete",
            "expected_reply_guidance": guidance,
            "annotation_timestamp": _now(),
            "revision": record.revision + 1,
        }
    )
    updated = AnnotationRecord.model_validate(updated.model_dump())
    return store.save(updated, "expected_reply_guidance_saved")


def skip_example(
    config: AppConfig, queue_name: str, example_id: str, annotator_id: str, notes: str = ""
) -> AnnotationRecord:
    store = AnnotationStore(config, queue_name)
    previous = store.load().get(example_id)
    contract = store.contract
    record = AnnotationRecord(
        example_id=example_id,
        queue_name=queue_name,
        status="skipped",
        primary_intent=previous.primary_intent if previous else None,
        should_escalate=previous.should_escalate if previous else None,
        escalation_reason_code=previous.escalation_reason_code if previous else None,
        escalation_explanation=previous.escalation_explanation if previous else None,
        risk_flags=previous.risk_flags if previous else (),
        ambiguity=previous.ambiguity if previous else None,
        annotation_notes=notes or (previous.annotation_notes if previous else ""),
        expected_reply_guidance=previous.expected_reply_guidance if previous else "",
        annotator_id=annotator_id,
        annotation_timestamp=_now(),
        **contract,
        reference_revealed=previous.reference_revealed if previous else False,
        reference_revealed_at=previous.reference_revealed_at if previous else None,
        revision=(previous.revision + 1) if previous else 1,
    )
    return store.save(record, "example_skipped")


def get_annotation_view(config: AppConfig, queue_name: str, example_id: str) -> dict[str, Any]:
    """Return only human-visible fields; never forwards model columns."""

    queue = load_queue(config, queue_name)
    if example_id not in set(queue["example_id"].astype(str)):
        raise AnnotationError(f"example {example_id} is not in the {queue_name} queue")
    pool = POOL_FOR_QUEUE[queue_name]
    inputs = pd.read_parquet(
        config.annotation.split_dir / OUTPUT_FILES[f"{pool}_inputs"],
        columns=[
            "example_id",
            "customer_text_redacted",
            "context_tweet_ids",
            "context_author_ids",
            "context_inbound",
            "context_created_at_utc",
            "context_texts_redacted",
            "quality_flags",
        ],
    )
    match = inputs[inputs["example_id"].astype(str) == example_id]
    if len(match) != 1:
        raise AnnotationError(f"expected one input row for {example_id}; found {len(match)}")
    row = match.iloc[0]
    context = []
    lists = {
        name: _as_list(row[name])
        for name in (
            "context_tweet_ids",
            "context_author_ids",
            "context_inbound",
            "context_created_at_utc",
            "context_texts_redacted",
        )
    }
    for values in zip(*(lists[name] for name in lists)):
        context.append(dict(zip(lists, values)))
    view: dict[str, Any] = {
        "example_id": example_id,
        "customer_text_redacted": str(row["customer_text_redacted"]),
        "preceding_context": context,
        "quality_flags": [str(value) for value in _as_list(row["quality_flags"])],
        "reference_revealed": False,
    }
    record = AnnotationStore(config, queue_name).load().get(example_id)
    if record and record.reference_revealed:
        references = pd.read_parquet(
            config.annotation.split_dir / OUTPUT_FILES[f"{pool}_references"],
            columns=["example_id", "reference_reply_ids", "reference_reply_texts_redacted", "reference_status"],
        )
        reference = references[references["example_id"].astype(str) == example_id]
        if len(reference) != 1:
            raise AnnotationError(f"expected one reference row for {example_id}; found {len(reference)}")
        ref = reference.iloc[0]
        view["reference_revealed"] = True
        view["historical_reference"] = {
            "reply_ids": [str(value) for value in _as_list(ref["reference_reply_ids"])],
            "reply_texts_redacted": [str(value) for value in _as_list(ref["reference_reply_texts_redacted"])],
            "reference_status": str(ref["reference_status"]),
            "warning": "Historical replies are imperfect reference material, not verified current answers.",
        }
    return view


def validate_annotation_outputs(config: AppConfig) -> dict[str, Any]:
    paths = annotation_paths(config.annotation.output_dir)
    queues = {name: pd.read_parquet(paths.queues / f"{name}.parquet") for name in QUEUE_NAMES}
    queue_report = validate_queues(
        queues,
        golden_random_size=config.annotation.golden_random_size,
        golden_challenge_size=config.annotation.golden_challenge_size,
    )
    pools = {
        split: pd.read_parquet(config.annotation.split_dir / OUTPUT_FILES[f"{split}_inputs"])
        for split in ("train", "development", "test_candidate")
    }
    validate_queue_membership(queues, pools)
    validate_queue_provenance(config, queues)
    contract = current_contract(config)
    by_queue: dict[str, Any] = {}
    hard_issues: list[str] = []
    for name, queue in queues.items():
        try:
            records = AnnotationStore(config, name, enforce_access=False).load()
        except AnnotationError as error:
            hard_issues.append(f"{name}: {error}")
            continue
        expected = set(queue["example_id"].astype(str))
        stale = [
            example_id
            for example_id, record in records.items()
            if any(getattr(record, key) != value for key, value in contract.items())
        ]
        complete = [key for key, value in records.items() if value.status == "complete"]
        skipped = [key for key, value in records.items() if value.status == "skipped"]
        in_progress = [key for key, value in records.items() if value.status == "judgment_saved"]
        by_queue[name] = {
            "expected": len(expected),
            "complete": len(complete),
            "judgment_saved": len(in_progress),
            "skipped_incomplete": len(skipped),
            "missing": len(expected - set(records)),
            "stale_requires_human_review": len(stale),
        }
    if hard_issues:
        raise AnnotationError("annotation validation failed: " + "; ".join(hard_issues))
    all_complete = all(
        value["complete"] == value["expected"]
        and value["skipped_incomplete"] == 0
        and value["stale_requires_human_review"] == 0
        for value in by_queue.values()
    )
    return {
        "tooling": "ready",
        "queues": "prepared",
        "human_annotations": "complete" if all_complete else "in_progress_or_not_started",
        "guide": load_guide_state(config)["status"],
        "queue_validation": queue_report,
        "annotations": by_queue,
    }
