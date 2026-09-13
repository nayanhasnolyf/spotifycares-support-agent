"""Frozen-policy machine labels, separate from human CSVs; no golden access."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from spotify_cares.annotation import (
    AnnotationError, AnnotationStore, assert_queue_access, current_contract,
    load_taxonomy, sha256_file, _append_jsonl,
)
from spotify_cares.config import AppConfig

PROMPT_PATH = Path("configs/machine_annotation_prompt.txt")
ALLOWED_QUEUES = ("training", "development")
GENERATION_SETTINGS = {"temperature": 0, "max_output_tokens": 2048}


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


class MachineDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary_intent: str = Field(min_length=1)
    should_escalate: Literal["yes", "no"]
    escalation_reason_code: str | None
    escalation_explanation: str | None
    risk_flags: list[str]
    ambiguity: Literal["clear", "ambiguous"]
    annotation_notes: str
    expected_reply_guidance: str = Field(min_length=1)

    @model_validator(mode="after")
    def consistent(self):
        if self.should_escalate == "yes":
            if not self.escalation_reason_code or not (self.escalation_explanation or "").strip():
                raise ValueError("escalation requires a reason and explanation")
        elif self.escalation_reason_code is not None or self.escalation_explanation is not None:
            raise ValueError("non-escalation requires null reason and explanation")
        if len(set(self.risk_flags)) != len(self.risk_flags):
            raise ValueError("duplicate risk flags")
        if self.ambiguity == "ambiguous" and not self.annotation_notes.strip():
            raise ValueError("ambiguity requires notes")
        if not self.expected_reply_guidance.strip():
            raise ValueError("reply guidance must not be blank")
        return self


class MachineRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    annotation_source: Literal["machine_annotated"] = "machine_annotated"
    queue_name: Literal["training", "development"]
    example_id: str = Field(min_length=1)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance: dict
    timestamp: datetime
    attempt: int = Field(ge=1)
    status: Literal["success", "failure"]
    decision: MachineDecision | None
    error_code: Literal["provider_error", "invalid_output", "empty_output"] | None
    response_model_version: str | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp needs timezone")
        if self.status == "success":
            if self.decision is None or self.error_code is not None:
                raise ValueError("success needs decision and no error")
        elif self.decision is not None or self.error_code is None:
            raise ValueError("failure needs error and no decision")
        return self


def validate_decision(decision: MachineDecision, taxonomy) -> None:
    if decision.primary_intent not in {item.label for item in taxonomy.intents}:
        raise ValueError("unknown intent")
    if decision.escalation_reason_code is not None and decision.escalation_reason_code not in {
        item.code for item in taxonomy.escalation_policy.reason_codes
    }:
        raise ValueError("unknown reason")
    if set(decision.risk_flags) - set(taxonomy.risk_flags):
        raise ValueError("unknown risk flag")


def prepare_run(config: AppConfig, queue_name: str, model: str, prompt_path: Path):
    # Check before any queue, label, or input reads, including training.
    if queue_name not in ALLOWED_QUEUES:
        raise AnnotationError("machine annotation permits only training/development")
    assert_queue_access(config, "development")  # matching frozen policy for both queues
    if not model.strip():
        raise AnnotationError("an explicit Gemini model ID is required")
    contract = current_contract(config)
    taxonomy = load_taxonomy(config.annotation.taxonomy_path)
    queue_path = config.annotation.output_dir / "queues" / f"{queue_name}.parquet"
    queue = pd.read_parquet(queue_path).sort_values("queue_position")
    if set(queue.queue_name) != {queue_name} or queue.example_id.duplicated().any():
        raise AnnotationError("invalid machine-annotation queue")
    pool_path = config.annotation.split_dir / (
        "train_inputs.parquet" if queue_name == "training" else "development_inputs.parquet"
    )
    pool_hash = sha256_file(pool_path)
    if set(queue.candidate_pool_sha256) != {pool_hash}:
        raise AnnotationError("input pool differs from queue provenance")
    schema = MachineDecision.model_json_schema()
    schema["properties"]["primary_intent"]["enum"] = [item.label for item in taxonomy.intents]
    schema["properties"]["risk_flags"]["items"]["enum"] = taxonomy.risk_flags
    schema["properties"]["escalation_reason_code"]["anyOf"][0]["enum"] = [
        item.code for item in taxonomy.escalation_policy.reason_codes
    ]
    system = prompt_path.read_text(encoding="utf-8") + "\nTAXONOMY\n" + canonical(
        taxonomy.model_dump()
    ) + "\nGUIDE\n" + config.annotation.guide_path.read_text(encoding="utf-8")
    provenance = {
        "workflow_version": "machine-annotation-v1", "model": model,
        "google_genai_version": version("google-genai"),
        **contract, "prompt_template_sha256": sha256_file(prompt_path),
        "prompt_sha256": digest(system), "response_schema_sha256": digest(schema),
        "queue_sha256": sha256_file(queue_path), "input_pool_sha256": pool_hash,
        "generation_settings": GENERATION_SETTINGS,
        "development_interpretation": "model agreement, not independent human accuracy",
    }
    run_hash = digest(provenance)
    path = config.annotation.output_dir / "machine" / queue_name / f"{run_hash}.jsonl"
    return queue, pool_path, taxonomy, system, schema, provenance, path


def load_events(path: Path) -> list[MachineRecord]:
    if not path.exists():
        return []
    try:
        return [MachineRecord.model_validate_json(line) for line in path.read_text(
            encoding="utf-8"
        ).splitlines()]
    except (ValueError, ValidationError):
        raise AnnotationError("invalid machine JSONL; preserve it and inspect locally before resuming") from None


def validate_events(events, provenance, members, taxonomy):
    latest = {}
    attempts = {}
    for record in events:
        if record.provenance != provenance or record.run_sha256 != digest(provenance):
            raise AnnotationError("machine provenance mismatch")
        if record.example_id not in members:
            raise AnnotationError("machine record outside selected queue")
        if record.attempt != attempts.get(record.example_id, 0) + 1:
            raise AnnotationError("invalid machine attempt sequence")
        if record.example_id in latest and latest[record.example_id].status == "success":
            raise AnnotationError("duplicate machine success or attempt after success")
        if record.decision is not None:
            try:
                validate_decision(record.decision, taxonomy)
            except ValueError:
                raise AnnotationError("invalid stored machine decision") from None
        latest[record.example_id] = record
        attempts[record.example_id] = record.attempt
    return latest


def read_inputs(pool_path, ids):
    if not ids:
        return {}
    frame = pd.read_parquet(pool_path, columns=[
        "example_id", "customer_text_redacted", "context_texts_redacted", "context_inbound",
    ], filters=[("example_id", "in", list(ids))])
    if frame.example_id.duplicated().any() or set(frame.example_id) != set(ids):
        raise AnnotationError("missing or duplicate source input IDs")
    values = json.loads(frame.to_json(orient="records"))
    return {row["example_id"]: row for row in values}


@contextmanager
def run_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise AnnotationError("run locked; confirm no generator is running before removing a stale lock") from None
    try:
        handle.close()
        yield
    finally:
        lock.unlink()


class GeminiProvider:
    """Lazy SDK adapter; no fallback labels, no raw exception/response logging."""

    def __init__(self):
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise AnnotationError("GEMINI_API_KEY is missing; no generation performed")
        from google import genai
        self.client = genai.Client(api_key=key, vertexai=False, http_options={
            "timeout": 60000, "retry_options": {"attempts": 1},
        })

    def __call__(self, *, model, system, schema, message):
        response = self.client.models.generate_content(
            model=model, contents=canonical(message), config={
                "system_instruction": system, "response_mime_type": "application/json",
                "response_json_schema": schema, **GENERATION_SETTINGS,
            },
        )
        return response.text, response.model_version

    def close(self):
        self.client.close()


def machine_annotate(config, queue_name, *, model, prompt_path=PROMPT_PATH, limit=None, provider=None):
    if limit is not None and limit < 1:
        raise AnnotationError("limit must be positive")
    queue, pool, taxonomy, system, schema, provenance, path = prepare_run(
        config, queue_name, model, prompt_path
    )
    with run_lock(path):
        human_store = AnnotationStore(config, queue_name)
        humans = human_store.load()
        events = load_events(path)
        latest = validate_events(events, provenance, set(queue.example_id), taxonomy)
        if any(e.queue_name != queue_name for e in events):
            raise AnnotationError("machine queue mismatch")
        missing = [eid for eid in queue.example_id if eid not in humans]
        inputs = read_inputs(pool, missing)
        for eid, event in latest.items():
            if eid in inputs and event.input_sha256 != digest(inputs[eid]):
                raise AnnotationError("saved input fingerprint mismatch")
        pending = [eid for eid in missing if eid not in latest or latest[eid].status != "success"]
        pending = pending[:limit] if limit is not None else pending
        owned_provider = provider is None and bool(pending)
        if owned_provider:
            provider = GeminiProvider()
        try:
            for eid in pending:
                assert_queue_access(config, "development")
                if current_contract(config) != {k: provenance[k] for k in current_contract(config)}:
                    raise AnnotationError("guide changed during generation")
                if human_store.load() != humans:
                    raise AnnotationError("human annotations changed; resume to recompute missing IDs")
                decision, error, resolved_model = None, None, None
                try:
                    raw, resolved_model = provider(model=model, system=system, schema=schema, message=inputs[eid])
                except Exception:
                    error = "provider_error"
                else:
                    if not raw:
                        error = "empty_output"
                    else:
                        try:
                            decision = MachineDecision.model_validate_json(raw)
                            validate_decision(decision, taxonomy)
                        except (ValueError, ValidationError):
                            decision, error = None, "invalid_output"
                assert_queue_access(config, "development")
                if current_contract(config) != {k: provenance[k] for k in current_contract(config)}:
                    raise AnnotationError("guide changed during generation; response discarded")
                if sha256_file(pool) != provenance["input_pool_sha256"]:
                    raise AnnotationError("input pool changed during generation; response discarded")
                if sha256_file(config.annotation.output_dir / "queues" / f"{queue_name}.parquet") != provenance["queue_sha256"]:
                    raise AnnotationError("queue changed during generation; response discarded")
                if human_store.load() != humans:
                    raise AnnotationError("human annotations changed; response discarded")
                record = MachineRecord(
                    queue_name=queue_name, example_id=eid, input_sha256=digest(inputs[eid]),
                    run_sha256=digest(provenance), provenance=provenance,
                    timestamp=datetime.now(timezone.utc),
                    attempt=latest[eid].attempt + 1 if eid in latest else 1,
                    status="failure" if error else "success", decision=decision,
                    error_code=error, response_model_version=resolved_model,
                )
                _append_jsonl(path, record.model_dump(mode="json"))
        finally:
            if owned_provider:
                provider.close()
    return validate_machine_annotations(config, queue_name, model=model, prompt_path=prompt_path)


def validate_machine_annotations(config, queue_name, *, model, prompt_path=PROMPT_PATH):
    queue, pool, taxonomy, _, _, provenance, path = prepare_run(config, queue_name, model, prompt_path)
    humans = AnnotationStore(config, queue_name).load()
    events = load_events(path)
    latest = validate_events(events, provenance, set(queue.example_id), taxonomy)
    if any(event.queue_name != queue_name for event in events):
        raise AnnotationError("machine queue mismatch")
    missing = set(queue.example_id) - set(humans)
    inputs = read_inputs(pool, missing)
    for eid, event in latest.items():
        if eid in inputs and event.input_sha256 != digest(inputs[eid]):
            raise AnnotationError("saved input fingerprint mismatch")
    successes = {eid for eid, event in latest.items() if event.status == "success"} & missing
    failures = {eid for eid, event in latest.items() if event.status == "failure"} & missing
    return {
        "annotation_source": "machine_annotated", "queue": queue_name,
        "path": str(path), "run_sha256": digest(provenance),
        "human_records_protected": len(humans), "expected_machine": len(missing),
        "validated_successes": len(successes), "unresolved_failures": len(failures),
        "not_attempted": len(missing - set(latest)),
        "superseded_by_human": len(set(latest) & set(humans)),
        "complete": successes == missing,
        "interpretation": "machine-label validation only; development scores would be model agreement, not independent human accuracy",
    }
