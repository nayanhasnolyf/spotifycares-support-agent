"""Frozen-policy machine labels, separate from human CSVs; no golden access."""

from __future__ import annotations

from contextlib import contextmanager
from collections import deque
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
import random
import time
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from spotify_cares.annotation import (
    AnnotationError, AnnotationStore, assert_queue_access, current_contract,
    load_taxonomy, sha256_file, _append_jsonl,
)
from spotify_cares.config import AppConfig
from spotify_cares.rate_limits import RateEvidence, extract_rate_evidence, retry_wait

PROMPT_PATH = Path("configs/machine_annotation_prompt.txt")
ALLOWED_QUEUES = ("training", "development")
GENERATION_SETTINGS = {"temperature": 0, "max_output_tokens": 2048}
PERMANENT_HTTP_ERRORS = {400, 401, 403, 404, 405, 410, 413, 422}


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
    provider_http_status: int | None = Field(default=None, ge=100, le=599)
    rate_limit_evidence: RateEvidence | None = None
    request_controls: dict | None = None

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


def prepare_run(config: AppConfig, queue_name: str, model: str | None, prompt_path: Path,
                provider_name=None, legacy_gemini=False):
    # Check before any queue, label, or input reads, including training.
    if queue_name not in ALLOWED_QUEUES:
        raise AnnotationError("machine annotation permits only training/development")
    assert_queue_access(config, "development")  # matching frozen policy for both queues
    provider_name = provider_name or config.annotation.machine_provider
    if provider_name not in {"gemini", "groq"} or (legacy_gemini and provider_name != "gemini"):
        raise AnnotationError("invalid provider/legacy selection")
    model = model if model is not None else (
        config.annotation.groq_model if provider_name == "groq" else config.annotation.machine_model
    )
    if not model or not model.strip():
        raise AnnotationError("configure annotation.machine_model or supply --model")
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
        "workflow_version": "machine-annotation-v2", "model": model,
        "google_genai_version": version("google-genai"),
        **contract, "prompt_template_sha256": sha256_file(prompt_path),
        "prompt_sha256": digest(system), "response_schema_sha256": digest(schema),
        "queue_sha256": sha256_file(queue_path), "input_pool_sha256": pool_hash,
        "generation_settings": GENERATION_SETTINGS,
        "development_interpretation": "model agreement, not independent human accuracy",
    }
    if not legacy_gemini:
        provenance.update(workflow_version="machine-annotation-v3", provider=provider_name)
        if provider_name == "groq":
            from spotify_cares.groq_annotation import GROQ_GENERATION_SETTINGS
            provenance.pop("google_genai_version")
            provenance.update(httpx_version=version("httpx"),
                              generation_settings=GROQ_GENERATION_SETTINGS,
                              transport="groq-chat-completions-json-schema-strict-v1")
    run_hash = digest(provenance)
    path = config.annotation.output_dir / "machine" / queue_name / f"{run_hash}.jsonl"
    return queue, pool_path, taxonomy, system, schema, provenance, path


def retained_labels(config, queue_name, prompt_path=PROMPT_PATH):
    """Explicit ordered sources only; never scan and silently merge arbitrary runs."""
    selected, sources, seen = {}, [], set()
    for source in config.annotation.retained_machine_runs:
        if source.queue != queue_name:
            continue
        if source.run_sha256 in seen:
            raise AnnotationError("duplicate retained run")
        seen.add(source.run_sha256)
        queue, pool, taxonomy, _, _, provenance, path = prepare_run(
            config, queue_name, source.model, prompt_path, source.provider, source.legacy_gemini)
        if digest(provenance) != source.run_sha256:
            raise AnnotationError("retained run does not match current policy/prompt/schema/environment")
        if not path.exists():
            raise AnnotationError("configured retained run is missing locally; restore it before generation")
        events = load_events(path)
        latest = validate_events(events, provenance, set(queue.example_id), taxonomy)
        if any(e.queue_name != queue_name for e in events):
            raise AnnotationError("retained queue mismatch")
        inputs = read_inputs(pool, set(latest))
        if any(e.input_sha256 != digest(inputs[eid]) for eid, e in latest.items()):
            raise AnnotationError("retained input fingerprint mismatch")
        sources.append({**source.model_dump(), "path": str(path), "file_sha256": sha256_file(path)})
        for eid, event in latest.items():
            if event.status == "success":
                selected.setdefault(eid, (event, source.provider, str(path)))
    return selected, sources


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


def machine_annotate(config, queue_name, *, model=None, prompt_path=PROMPT_PATH, limit=None, provider=None,
                     provider_name=None,
                     retry_unknown_quota=False):
    if limit is not None and limit < 1:
        raise AnnotationError("limit must be positive")
    queue, pool, taxonomy, system, schema, provenance, path = prepare_run(
        config, queue_name, model, prompt_path, provider_name
    )
    provider_name = provenance["provider"]
    model = provenance["model"]
    rate = config.annotation.machine_rate
    halt_reason = None
    # Serializes providers and queues, protecting combined selection and quota ledger.
    with run_lock(config.annotation.output_dir / "machine" / "generation"), run_lock(path):
        human_store = AnnotationStore(config, queue_name)
        humans = human_store.load()
        retained, retained_sources = retained_labels(config, queue_name, prompt_path)
        events = load_events(path)
        latest = validate_events(events, provenance, set(queue.example_id), taxonomy)
        if any(e.queue_name != queue_name for e in events):
            raise AnnotationError("machine queue mismatch")
        missing = [eid for eid in queue.example_id if eid not in humans and eid not in retained]
        # A new provenance format is not permission to bypass the same provider's
        # saved permanent/unknown-quota error. Groq does not inherit Gemini quota.
        inherited_failures = {}
        for source in retained_sources:
            if source["provider"] == provider_name and source["model"] == model:
                prior = {e.example_id: e for e in load_events(Path(source["path"]))}
                inherited_failures.update({eid: e for eid, e in prior.items()
                                           if eid in missing and eid not in latest and e.status == "failure"})
        safety_latest = {**inherited_failures, **latest}
        permanent = [e for eid, e in safety_latest.items() if eid in missing
                     and e.status == "failure" and e.provider_http_status in PERMANENT_HTTP_ERRORS]
        if permanent:
            raise AnnotationError(
                f"recorded permanent provider error HTTP {permanent[0].provider_http_status}; "
                "not retried. Correct the configuration and inspect the local run before recovery."
            )
        pending = [eid for eid in missing if eid not in latest or latest[eid].status != "success"]
        for eid, previous in safety_latest.items():
            if eid not in missing or previous.status != "failure":
                continue
            evidence = previous.rate_limit_evidence
            if evidence and evidence.category in {"daily", "billing", "quota_unavailable"}:
                raise AnnotationError(f"saved {evidence.category} limit requires quota/account review; not retried")
            if previous.provider_http_status == 429 and (evidence is None or evidence.category == "unknown") and not retry_unknown_quota:
                raise AnnotationError("saved HTTP 429 has unknown quota/delay; check project quota before explicitly using --retry-unknown-quota")
        pending = pending[:limit] if limit is not None else pending
        inputs = read_inputs(pool, set(pending) | (set(latest) & set(missing)))
        for eid, event in latest.items():
            if eid in inputs and event.input_sha256 != digest(inputs[eid]):
                raise AnnotationError("saved input fingerprint mismatch")
        owned_provider = provider is None and bool(pending)
        # Pacing changes preserve the run hash; successes are never regenerated.
        for eid in pending:
            previous = safety_latest.get(eid)
            evidence = previous.rate_limit_evidence if previous else None
            if evidence and evidence.retry_not_before:
                wait = max(0, (evidence.retry_not_before - datetime.now(timezone.utc)).total_seconds())
                if wait > rate.max_single_wait_seconds or wait > rate.max_total_retry_wait_seconds:
                    raise AnnotationError(f"server retry wait is still {wait:.1f}s; defer and resume later")
        if owned_provider:
            if provider_name == "groq":
                from spotify_cares.groq_annotation import GroqProvider
                provider = GroqProvider(config)
            else:
                provider = GeminiProvider()
        try:
            work = deque(pending)
            retries, waited, calls, last_started = {}, 0.0, 0, None
            if events:
                elapsed = max(0, (datetime.now(timezone.utc) - max(e.timestamp for e in events)).total_seconds())
                last_started = time.monotonic() - elapsed
            while work and (limit is None or calls < limit):
                eid = work.popleft()
                previous = latest.get(eid, inherited_failures.get(eid))
                evidence = previous.rate_limit_evidence if previous else None
                wait = 0.0
                if previous and previous.status == "failure" and evidence and evidence.category == "temporary":
                    wait = retry_wait(rate, max(0, retries.get(eid, 0) - 1), evidence,
                                      datetime.now(timezone.utc), random.uniform(0, rate.jitter_seconds))
                elif evidence and evidence.retry_not_before:
                    wait = max(0, (evidence.retry_not_before - datetime.now(timezone.utc)).total_seconds())
                if last_started is not None:
                    wait = max(wait, rate.request_interval_seconds - (time.monotonic() - last_started))
                if wait > rate.max_single_wait_seconds or (
                    evidence and evidence.category == "temporary" and waited + wait > rate.max_total_retry_wait_seconds
                ):
                    halt_reason = f"retry wait {wait:.1f}s exceeds configured wait budget; resume later"
                    break
                if wait > 0:
                    time.sleep(wait)
                    if evidence and evidence.category == "temporary":
                        waited += wait
                assert_queue_access(config, "development")
                if current_contract(config) != {k: provenance[k] for k in current_contract(config)}:
                    raise AnnotationError("guide changed during generation")
                if human_store.load() != humans:
                    raise AnnotationError("human annotations changed; resume to recompute missing IDs")
                if any(sha256_file(Path(s["path"])) != s["file_sha256"] for s in retained_sources):
                    raise AnnotationError("retained source changed during generation")
                decision, error, resolved_model, http_status, rate_evidence = None, None, None, None, None
                last_started = time.monotonic()
                calls += 1
                try:
                    raw, resolved_model = provider(model=model, system=system, schema=schema, message=inputs[eid])
                except Exception as exc:
                    from spotify_cares.groq_annotation import ProviderPause, GroqHTTPError
                    if isinstance(exc, ProviderPause):
                        halt_reason = str(exc)
                        break  # No attempted label: still pending; reservations remain conservative.
                    error = "provider_error"
                    # Never persist or print exception text, which may echo credentials/input.
                    from google.genai.errors import APIError
                    if isinstance(exc, APIError) and isinstance(exc.code, int) and 100 <= exc.code <= 599:
                        http_status = exc.code
                        rate_evidence = extract_rate_evidence(exc, http_status)
                    elif isinstance(exc, GroqHTTPError):
                        http_status, rate_evidence = exc.status, exc.evidence
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
                if any(sha256_file(Path(s["path"])) != s["file_sha256"] for s in retained_sources):
                    raise AnnotationError("retained source changed; response discarded")
                record = MachineRecord(
                    queue_name=queue_name, example_id=eid, input_sha256=digest(inputs[eid]),
                    run_sha256=digest(provenance), provenance=provenance,
                    timestamp=datetime.now(timezone.utc),
                    attempt=latest[eid].attempt + 1 if eid in latest else 1,
                    status="failure" if error else "success", decision=decision,
                    error_code=error, response_model_version=resolved_model,
                    provider_http_status=http_status,
                    rate_limit_evidence=rate_evidence,
                    request_controls={"scheduler_version": "bounded-rate-v1", **rate.model_dump(),
                                      "provider_controls": getattr(provider, "last_controls", None),
                                      "unknown_quota_retry_confirmed": retry_unknown_quota},
                )
                _append_jsonl(path, record.model_dump(mode="json"))
                latest[eid] = record
                if error == "provider_error":
                    if (http_status == 429 or http_status in {500, 502, 503, 504}) and rate_evidence and rate_evidence.category == "temporary" and retries.get(eid, 0) < rate.max_retries:
                        retries[eid] = retries.get(eid, 0) + 1
                        work.appendleft(eid)
                        continue
                    category = rate_evidence.category if rate_evidence else "unknown"
                    halt_reason = f"provider error HTTP {http_status}; {category}; no further automatic requests"
                    break
        finally:
            if owned_provider:
                provider.close()
    report = combined_machine_manifest(config, queue_name, model=model, prompt_path=prompt_path,
                                      provider_name=provider_name)
    report["halt_reason"] = halt_reason
    return report


def validate_machine_annotations(config, queue_name, *, model=None, prompt_path=PROMPT_PATH,
                                 provider_name=None):
    queue, pool, taxonomy, _, _, provenance, path = prepare_run(config, queue_name, model, prompt_path, provider_name)
    humans = AnnotationStore(config, queue_name).load()
    events = load_events(path)
    latest = validate_events(events, provenance, set(queue.example_id), taxonomy)
    if any(event.queue_name != queue_name for event in events):
        raise AnnotationError("machine queue mismatch")
    missing = set(queue.example_id) - set(humans)
    inputs = read_inputs(pool, missing & set(latest))
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
        "provider_failures": [
            {"example_id": eid, "http_status": latest[eid].provider_http_status,
             "permanent": latest[eid].provider_http_status in PERMANENT_HTTP_ERRORS,
             "rate_limit_evidence": latest[eid].rate_limit_evidence.model_dump(mode="json") if latest[eid].rate_limit_evidence else None}
            for eid in sorted(failures) if latest[eid].error_code == "provider_error"
        ],
        "complete": successes == missing,
        "interpretation": "machine-label validation only; development scores would be model agreement, not independent human accuracy",
    }


def combined_machine_manifest(config, queue_name, *, model=None, prompt_path=PROMPT_PATH,
                              provider_name=None, write=True):
    """Content-addressed local selection; stale human labels are protected, not adopted."""
    report = validate_machine_annotations(config, queue_name, model=model, prompt_path=prompt_path,
                                          provider_name=provider_name)
    queue, _, _, _, _, provenance, path = prepare_run(config, queue_name, model, prompt_path, provider_name)
    humans = AnnotationStore(config, queue_name)
    human_records = humans.load()
    selected, sources = retained_labels(config, queue_name, prompt_path)
    latest = {e.example_id: e for e in load_events(path)}
    for eid, event in latest.items():
        if event.status == "success":
            selected.setdefault(eid, (event, provenance["provider"], str(path)))
    rows = []
    for eid in queue.example_id:
        if eid in human_records or eid not in selected:
            continue
        event, provider, source_path = selected[eid]
        rows.append({"example_id": eid, "annotation_source": "machine_annotated",
                     "provider": provider, "model": event.provenance["model"],
                     "run_sha256": event.run_sha256, "record_sha256": digest(event.model_dump(mode="json")),
                     "input_sha256": event.input_sha256, "source_path": source_path,
                     "attempt": event.attempt})
    chosen = {r["example_id"] for r in rows}
    pending = set(queue.example_id) - set(human_records) - chosen
    failures = {eid for eid in pending if eid in latest and latest[eid].status == "failure"}
    # Retained failures remain pending, even though no failure has occurred on this provider.
    counts = {p: sum(r["provider"] == p for r in rows) for p in ("gemini", "groq")}
    manifest = {"manifest_version": "mixed-machine-labels-v1", "queue": queue_name,
                **current_contract(config), "selection_rule": "protect every human record; first configured valid retained run; active run",
                "retained_sources": sources, "active_provenance": provenance,
                "active_path": str(path), "active_file_sha256": sha256_file(path) if path.exists() else None,
                "human_csv_sha256": sha256_file(humans.label_path) if humans.label_path.exists() else None,
                "protected_human_ids": sorted(human_records),
                "human_policy": "not selected here; preserve original versions and stale status",
                "readiness": "schema/input/provenance validation only; not semantic approval or training authorization",
                "selected_labels": rows, "pending_ids": sorted(pending),
                "interpretation": report["interpretation"]}
    manifest_path = config.annotation.output_dir / "machine" / "combined" / queue_name / f"{digest(manifest)}.json"
    if write:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload = canonical(manifest) + "\n"
        if manifest_path.exists():
            if manifest_path.read_text(encoding="utf-8") != payload:
                raise AnnotationError("combined manifest was modified")
        else:
            with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
    report.update(active_run_successes=report["validated_successes"],
                  validated_successes=len(rows), successes_by_provider=counts,
                  retained_successes=len(chosen - set(latest)), remaining=len(pending),
                  unresolved_failures=len(failures), not_attempted=len(pending - set(latest)),
                  complete=not pending, combined_manifest=str(manifest_path))
    return report
