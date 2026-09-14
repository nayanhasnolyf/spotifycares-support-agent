"""Synthetic fixtures/fake HTTP only. No real customer data or provider calls."""

import json
from pathlib import Path

import httpx
import pytest

from test_annotation import annotation_config, _complete_pilot
from test_machine_annotation import fake, freeze
from spotify_cares.annotation import AnnotationError, _append_jsonl, sha256_file
from spotify_cares.config import RetainedMachineRun
from spotify_cares.groq_annotation import (
    GroqProvider, ProviderPause, error_evidence, quota_headers, duration,
)
from spotify_cares.machine_annotation import (
    machine_annotate, prepare_run, PROMPT_PATH, load_events, combined_machine_manifest,
    digest, canonical,
)


def ready(config):
    _complete_pilot(config)
    freeze(config)
    return config


def retain(config, report, provider="gemini", legacy=False):
    config.annotation.retained_machine_runs = [RetainedMachineRun(
        queue="training", provider=provider, model="synthetic",
        run_sha256=report["run_sha256"], legacy_gemini=legacy)]


def test_mixed_resume_selects_once_preserves_humans_and_gemini(annotation_config, monkeypatch):
    config = ready(annotation_config)
    initial = machine_annotate(config, "training", model="synthetic", provider=fake)
    path = Path(initial["path"])
    before = path.read_bytes()
    retain(config, initial)
    import pandas as pd
    original = pd.read_parquet
    def guarded(path, *args, **kwargs):
        assert not any(s in str(path) for s in ("golden", "test_candidate", "references"))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(pd, "read_parquet", guarded)
    result = machine_annotate(config, "training", model="synthetic", provider_name="groq",
                              provider=lambda **kw: pytest.fail("regenerated retained label"))
    assert result["complete"] and result["validated_successes"] == 1
    assert result["active_run_successes"] == 0 and result["human_records_protected"] == 1
    assert path.read_bytes() == before
    manifest = json.loads(Path(result["combined_manifest"]).read_text())
    assert len(manifest["selected_labels"]) == 1
    assert manifest["selected_labels"][0]["provider"] == "gemini"
    assert manifest["active_provenance"]["provider"] == "groq"


def test_failed_gemini_is_pending_for_groq_and_provenance_separate(annotation_config):
    config = ready(annotation_config)
    initial = machine_annotate(config, "training", model="synthetic",
                               provider=lambda **kw: ("not JSON", None))
    retain(config, initial)
    before = Path(initial["path"]).read_bytes()
    result = machine_annotate(config, "training", model="synthetic", provider_name="groq", provider=fake)
    assert result["complete"] and result["successes_by_provider"] == {"gemini": 0, "groq": 1}
    assert initial["run_sha256"] != result["run_sha256"]
    assert Path(initial["path"]).read_bytes() == before
    event = load_events(Path(result["path"]))[0]
    assert event.provenance["provider"] == "groq"
    for key in ("prompt_sha256", "taxonomy_sha256", "guide_sha256", "response_schema_sha256"):
        assert len(event.provenance[key]) == 64
    again = machine_annotate(config, "training", model="synthetic", provider_name="groq",
                             provider=lambda **kw: pytest.fail("duplicate"))
    assert again["combined_manifest"] == result["combined_manifest"]


def test_legacy_provenance_adoption_without_rewrite(annotation_config):
    config = ready(annotation_config)
    result = machine_annotate(config, "training", model="synthetic", provider=fake)
    event = load_events(Path(result["path"]))[0].model_dump(mode="json")
    *_, provenance, path = prepare_run(config, "training", "synthetic", PROMPT_PATH, "gemini", True)
    event.update(provenance=provenance, run_sha256=digest(provenance))
    event.pop("request_controls")
    _append_jsonl(path, event)
    before = sha256_file(path)
    retain(config, {"run_sha256": digest(provenance)}, legacy=True)
    report = combined_machine_manifest(config, "training", provider_name="groq", model="synthetic")
    assert report["validated_successes"] == 1 and sha256_file(path) == before


def test_conflicting_valid_runs_explicit_retained_priority(annotation_config):
    config = ready(annotation_config)
    first = machine_annotate(config, "training", model="synthetic", provider=fake)
    second = machine_annotate(config, "training", model="synthetic", provider_name="groq", provider=fake)
    retain(config, first)
    result = combined_machine_manifest(config, "training", model="synthetic", provider_name="groq")
    manifest = json.loads(Path(result["combined_manifest"]).read_text())
    assert len(manifest["selected_labels"]) == 1
    assert manifest["selected_labels"][0]["run_sha256"] == first["run_sha256"]
    assert second["run_sha256"] != first["run_sha256"]


def test_missing_or_tampered_retained_run_fails_closed(annotation_config):
    config = ready(annotation_config)
    report = machine_annotate(config, "training", model="synthetic", provider=fake)
    retain(config, report)
    path = Path(report["path"])
    contents = path.read_text()
    path.write_text(contents.replace('"input_sha256": "', '"input_sha256": "1'))
    with pytest.raises(AnnotationError):
        machine_annotate(config, "training", provider_name="groq", provider=fake)


def test_headers_have_correct_dimensions_and_no_secret_fields():
    assert duration("2m59.56s") == pytest.approx(179.56)
    assert duration("NaN") is None
    assert quota_headers(httpx.Headers({"x-ratelimit-limit-requests": "1000",
        "x-ratelimit-limit-tokens": "8000", "x-ratelimit-reset-tokens": "7.5s",
        "authorization": "SYNTHETIC_SECRET"})) == {
            "limit_requests": 1000, "limit_tokens": 8000, "reset_tokens_seconds": 7.5}


@pytest.mark.parametrize("metric,category", [("RPM", "temporary"), ("TPM", "temporary"),
                                           ("TPD", "daily"), ("RPD", "daily")])
def test_groq_limits_sanitized(metric, category):
    response = httpx.Response(429, headers={"retry-after": "12"},
        json={"error": {"code": "rate_limit_exceeded", "message": f"SYNTHETIC_SECRET limit ({metric})"}})
    evidence = error_evidence(response)
    assert evidence.category == category and evidence.retry_after_seconds == 12
    assert "SYNTHETIC_SECRET" not in evidence.model_dump_json()


def test_billing_unknown_and_permanent_evidence():
    assert error_evidence(httpx.Response(429, json={"error": {"code": "billing_limit_reached"}})).category == "billing"
    assert error_evidence(httpx.Response(429, json={"error": {"message": "contact billing"}})).category == "unknown"
    assert error_evidence(httpx.Response(503, json={})).category == "temporary"


def provider_for(config, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-fixture-not-a-real-key")
    return GroqProvider(config, client=httpx.Client(transport=httpx.MockTransport(
        lambda request: pytest.fail("unexpected HTTP"))))


def test_persistent_request_token_pacing_across_queues(annotation_config, monkeypatch):
    provider = provider_for(annotation_config, monkeypatch)
    annotation_config.annotation.groq_rate.requests_per_minute = 2
    annotation_config.annotation.groq_rate.tokens_per_minute = 100
    _append_jsonl(provider.ledger, {"kind": "reservation", "time": 100, "model": "m",
                                   "tokens": 80, "input_tokens": 60, "output_tokens": 20})
    wait, _ = provider.budget_wait("m", 20, 20, 110)
    assert wait == pytest.approx(50.1)  # token bucket, not just RPM
    resumed = provider_for(annotation_config, monkeypatch)
    assert resumed.budget_wait("m", 20, 20, 110)[0] == wait
    assert resumed.budget_wait("m", 20, 20, 161)[0] == 0
    with pytest.raises(ProviderPause, match="single request"):
        provider.budget_wait("m", 101, 1, 200)


def test_server_token_limit_and_daily_budget_override_ceilings(annotation_config, monkeypatch):
    provider = provider_for(annotation_config, monkeypatch)
    _append_jsonl(provider.ledger, {"kind": "response", "time": 100, "model": "m",
                                   "headers": {"limit_tokens": 100, "remaining_requests": 0,
                                               "reset_requests_seconds": 10000}})
    assert provider.budget_wait("m", 20, 20, 110)[0] > 9000
    with pytest.raises(ProviderPause, match="single request"):
        provider.budget_wait("m", 101, 1, 110)
    _append_jsonl(provider.ledger, {"kind": "response", "time": 120, "model": "m",
                                   "headers": {}, "limit_category": "daily"})
    with pytest.raises(ProviderPause, match="daily"):
        provider.budget_wait("m", 20, 20, 121)


def test_missing_credentials_no_network_or_generated_events(annotation_config, monkeypatch):
    config = ready(annotation_config)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(AnnotationError, match="GROQ_API_KEY is missing"):
        machine_annotate(config, "training", provider_name="groq")
    assert not list((config.annotation.output_dir / "machine").rglob("*.jsonl"))


def test_real_adapter_with_fake_http_uses_strict_schema_and_records_headers(annotation_config, monkeypatch):
    config = ready(annotation_config)
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-key")
    monkeypatch.setattr("spotify_cares.groq_annotation.token_reservation", lambda payload: 100)
    seen = []
    def handle(request):
        seen.append(request.url.path)
        if request.url.path.endswith("models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-20b", "active": True}]})
        payload = json.loads(request.content)
        schema = payload["response_format"]["json_schema"]
        assert schema["strict"] is True and schema["schema"]["additionalProperties"] is False
        assert payload["temperature"] == 0 and payload["reasoning_effort"] == "low"
        message = json.loads(payload["messages"][1]["content"])
        text, model = fake(message=message)
        return httpx.Response(200, headers={"x-ratelimit-limit-tokens": "8000"},
            json={"model": model, "choices": [{"finish_reason": "stop", "message": {"content": text}}]})
    client = httpx.Client(base_url="https://api.groq.com/openai/v1/", transport=httpx.MockTransport(handle))
    provider = GroqProvider(config, client=client)
    report = machine_annotate(config, "training", provider_name="groq", provider=provider)
    event = load_events(Path(report["path"]))[0]
    assert report["complete"] and event.annotation_source == "machine_annotated"
    assert event.request_controls["provider_controls"]["response_headers"]["limit_tokens"] == 8000
    assert len(seen) == 2


def test_groq_pause_no_fake_failure_and_failure_retries_bounded(annotation_config, monkeypatch):
    config = ready(annotation_config)
    def pause(**kwargs):
        raise ProviderPause("temporary long wait; resume later")
    report = machine_annotate(config, "training", provider_name="groq", provider=pause)
    assert report["not_attempted"] == 1 and report["unresolved_failures"] == 0
    assert not Path(report["path"]).exists()
    from spotify_cares.groq_annotation import GroqHTTPError
    calls = []
    def failing(**kwargs):
        calls.append(1)
        response = httpx.Response(429, json={"error": {"message": "TPM limit"}})
        raise GroqHTTPError(429, error_evidence(response))
    monkeypatch.setattr("spotify_cares.machine_annotation.time.sleep", lambda seconds: None)
    report = machine_annotate(config, "training", provider_name="groq", provider=failing, limit=2)
    assert len(calls) == 2 and report["unresolved_failures"] == 1
    assert [e.attempt for e in load_events(Path(report["path"]))] == [1, 2]


def test_golden_rejected_for_combining_before_any_source_read(annotation_config, monkeypatch):
    monkeypatch.setattr("pandas.read_parquet", lambda *a, **kw: pytest.fail("golden access"))
    with pytest.raises(AnnotationError):
        combined_machine_manifest(annotation_config, "golden", provider_name="groq")


def test_compact_renderer_preserves_frozen_rules_and_new_identity(annotation_config):
    from spotify_cares.machine_annotation import compact_policy
    from spotify_cares.annotation import load_taxonomy
    guide = Path("docs/annotation_guide.md").read_text(encoding="utf-8")
    taxonomy = load_taxonomy(annotation_config.annotation.taxonomy_path)
    rendered = compact_policy(taxonomy, guide)
    for intent in taxonomy.intents:
        for text in [intent.meaning, *intent.include, *intent.exclude]:
            assert text in rendered
    assert all(rule in rendered for rule in taxonomy.tie_breakers)
    assert "Mark `ambiguous` when" in rendered
    assert "Do not copy private details, promise account action" in rendered
    assert "## Required workflow" not in rendered and "example_ids" not in rendered
    annotation_config.annotation.guide_path.write_text(guide, encoding="utf-8")
    ready(annotation_config)
    old = prepare_run(annotation_config, "training", None, None, "groq")[-2]
    annotation_config.annotation.groq_prompt_profile = "compact-v1"
    annotation_config.annotation.groq_prompt_path = Path("configs/machine_annotation_prompt_v2.txt")
    annotation_config.annotation.groq_max_completion_tokens = 1024
    new = prepare_run(annotation_config, "training", None, None, "groq")[-2]
    assert old["guide_sha256"] == new["guide_sha256"]
    assert old["prompt_sha256"] != new["prompt_sha256"]
    assert new["generation_settings"]["max_completion_tokens"] == 1024


def test_exclusion_retry_supersession_and_pinned_resume(annotation_config):
    config = ready(annotation_config)
    old = machine_annotate(config, "training", provider_name="groq", provider=fake)
    before = Path(old["path"]).read_bytes()
    config.annotation.excluded_machine_runs = {old["run_sha256"]: "synthetic unresolved review"}
    excluded = combined_machine_manifest(config, "training", provider_name="groq")
    assert excluded["validated_successes"] == 0 and excluded["remaining"] == 1
    with pytest.raises(AnnotationError, match="excluded"):
        machine_annotate(config, "training", provider_name="groq", provider=fake)
    config.annotation.groq_max_completion_tokens = 1024
    *_, provenance, _ = prepare_run(config, "training", None, None, "groq")
    pin = config.annotation.output_dir / "synthetic_selection.json"
    pin.write_text(canonical({"queue_name": "training", "run_sha256": digest(provenance),
                              "example_ids": ["train_1"]}))
    result = machine_annotate(config, "training", provider_name="groq", provider=fake, selection_path=pin)
    assert result["validated_successes"] == 1
    assert load_events(Path(result["path"]))[0].supersedes[0]["run_sha256"] == old["run_sha256"]
    machine_annotate(config, "training", provider_name="groq", selection_path=pin,
                     provider=lambda **kw: pytest.fail("duplicate pinned call"))
    assert Path(old["path"]).read_bytes() == before


def test_reservation_expiry_counts_failed_retries_without_refunds(annotation_config, monkeypatch):
    provider = provider_for(annotation_config, monkeypatch)
    annotation_config.annotation.groq_rate.tokens_per_minute = 100
    for when in (100, 110):
        _append_jsonl(provider.ledger, {"kind": "reservation", "time": when, "model": "m",
                                       "tokens": 40, "input_tokens": 30, "output_tokens": 10})
        _append_jsonl(provider.ledger, {"kind": "response", "time": when+1, "model": "m",
                                       "headers": {}, "http_status": 429,
                                       "usage": {"total_tokens": 1}})
    # Both reservations count even though usage is smaller and responses failed.
    assert provider.budget_wait("m", 25, 10, 120)[0] == pytest.approx(40.1)
    assert provider.budget_wait("m", 25, 10, 171)[0] == 0
    annotation_config.annotation.groq_rate.requests_per_day = 2
    with pytest.raises(ProviderPause, match="daily request"):
        provider.budget_wait("m", 25, 10, 171)
    assert provider.budget_wait("m", 25, 10, 86511)[0] == 0


def test_usage_capture_has_no_inferred_counts_or_raw_fields():
    from spotify_cares.groq_annotation import usage_fields
    assert usage_fields({}) is None
    assert usage_fields({"usage": {"prompt_tokens": 40, "completion_tokens": 10,
        "total_tokens": 50, "secret": "SYNTHETIC_SECRET",
        "completion_tokens_details": {"reasoning_tokens": 5, "ignored": "secret"}}}) == {
            "prompt_tokens": 40, "completion_tokens": 10, "total_tokens": 50,
            "completion_tokens_details": {"reasoning_tokens": 5}}


def test_retained_gemini_uses_its_original_prompt(annotation_config):
    config = ready(annotation_config)
    initial = machine_annotate(config, "training", model="synthetic", provider=fake)
    retain(config, initial)
    changed = config.annotation.output_dir / "synthetic_new_prompt.txt"
    changed.write_text("Synthetic revised machine prompt")
    result = combined_machine_manifest(config, "training", model="synthetic", provider_name="groq", prompt_path=changed)
    assert result["successes_by_provider"]["gemini"] == 1


def test_record_hold_excludes_success_without_mutating_or_repeating(annotation_config):
    config = ready(annotation_config)
    result = machine_annotate(config, "training", provider_name="groq", provider=fake)
    path = Path(result["path"])
    before = path.read_bytes()
    registry = config.annotation.output_dir / "synthetic_exclusions.json"
    config.annotation.machine_record_exclusions_path = registry
    with pytest.raises(AnnotationError, match="registry"):
        combined_machine_manifest(config, "training", provider_name="groq")
    registry.write_text(canonical([{"queue_name": "training", "run_sha256": result["run_sha256"],
                                   "example_id": "train_1", "reason": "synthetic review hold"}]))
    report = machine_annotate(config, "training", provider_name="groq",
                              provider=lambda **kw: pytest.fail("implicit repeated attempt"))
    assert report["validated_successes"] == 0 and report["excluded_active_records"] == 1
    assert report["remaining"] == 1 and path.read_bytes() == before


def test_http_retry_reserves_each_attempt_and_keeps_actual_usage(annotation_config, monkeypatch):
    config = ready(annotation_config)
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-key")
    monkeypatch.setattr("spotify_cares.groq_annotation.token_reservation", lambda payload: 100)
    monkeypatch.setattr("spotify_cares.groq_annotation.time.sleep", lambda seconds: None)
    calls = []
    def handle(request):
        if request.url.path.endswith("models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-20b"}]})
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "0"},
                                  json={"error": {"message": "synthetic TPM limit"}})
        payload = json.loads(request.content)
        text, model = fake(message=json.loads(payload["messages"][1]["content"]))
        return httpx.Response(200, json={"model": model,
            "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            "choices": [{"finish_reason": "stop", "message": {"content": text}}]})
    client = httpx.Client(base_url="https://api.groq.com/openai/v1/", transport=httpx.MockTransport(handle))
    provider = GroqProvider(config, client=client)
    report = machine_annotate(config, "training", provider_name="groq", provider=provider, limit=2)
    assert report["complete"] and len(calls) == 2
    events = load_events(Path(report["path"]))
    assert [e.status for e in events] == ["failure", "success"]
    reservations = [e for e in provider._events() if e["kind"] == "reservation"]
    assert len(reservations) == 2 and all(e["tokens"] == 2148 for e in reservations)
    assert events[-1].request_controls["provider_controls"]["usage"]["total_tokens"] == 70
