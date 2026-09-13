"""Only synthetic inputs and fake provider outputs; never calls a live API."""

import json
from pathlib import Path

import pandas as pd
import pytest

from test_annotation import annotation_config, _complete_pilot, _save_valid
from spotify_cares.annotation import (
    AnnotationError, AnnotationStore, current_contract, freeze_guide,
    training_pilot_status, sha256_file,
)
from spotify_cares.machine_annotation import (
    MachineDecision, GeminiProvider, machine_annotate, validate_machine_annotations,
    prepare_run, load_events,
)


def freeze(config, **kwargs):
    contract = current_contract(config)
    return freeze_guide(config, annotator_id="synthetic-tester",
                        confirm_taxonomy_version=contract["taxonomy_version"],
                        confirm_guide_version=contract["guide_version"], **kwargs)


def fake(**kwargs):
    assert "reference" not in kwargs["message"]
    assert set(kwargs["message"]) == {
        "example_id", "customer_text_redacted", "context_texts_redacted", "context_inbound",
    }
    return json.dumps({
        "primary_intent": "other_or_unclear", "should_escalate": "no",
        "escalation_reason_code": None, "escalation_explanation": None,
        "risk_flags": [], "ambiguity": "clear", "annotation_notes": "Synthetic test output",
        "expected_reply_guidance": "Synthetic acknowledgement",
    }), "synthetic-model-version"


@pytest.mark.parametrize("queue", ["training", "development", "golden", "../golden"])
def test_locked_before_source_reads(annotation_config, monkeypatch, queue):
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **kw: pytest.fail("source read before gate"))
    with pytest.raises(AnnotationError):
        machine_annotate(annotation_config, queue, model="synthetic", provider=fake)


def test_explicit_prior_pilot_acknowledgement_does_not_refresh_labels(annotation_config):
    with pytest.raises(AnnotationError):
        freeze(annotation_config, acknowledge_prior_version_pilot=True)
    _complete_pilot(annotation_config)
    store = AnnotationStore(annotation_config, "training")
    before = store.label_path.read_bytes(), store.audit_path.read_bytes()
    guide = annotation_config.annotation.guide_path
    guide.write_text("# Changed synthetic guide\n", encoding="utf-8")
    assert training_pilot_status(annotation_config)["stale"] == 1
    with pytest.raises(AnnotationError):
        freeze(annotation_config)
    state = freeze(annotation_config, acknowledge_prior_version_pilot=True)
    assert state["pilot_at_approval"]["stale"] == 1
    assert state["prior_version_pilot_acknowledged"] is True
    assert before == (store.label_path.read_bytes(), store.audit_path.read_bytes())
    assert training_pilot_status(annotation_config)["stale"] == 1


def test_resume_preserves_humans_and_never_reads_golden_or_references(annotation_config, monkeypatch):
    _complete_pilot(annotation_config)
    freeze(annotation_config)
    root = annotation_config.annotation.output_dir
    protected = {p: sha256_file(p) for p in root.rglob("*") if p.is_file()}
    original = pd.read_parquet
    def guarded(path, *args, **kwargs):
        assert "golden" not in str(path) and "test_candidate" not in str(path)
        assert "references" not in str(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(pd, "read_parquet", guarded)
    report = machine_annotate(annotation_config, "training", model="synthetic", provider=fake)
    assert report["complete"] and report["validated_successes"] == 1
    assert report["human_records_protected"] == 1
    record = load_events(Path(report["path"]))[0]
    assert record.example_id == "train_1" and record.annotation_source == "machine_annotated"
    assert record.response_model_version == "synthetic-model-version"
    assert len(record.provenance["prompt_sha256"]) == 64
    machine_annotate(annotation_config, "training", model="synthetic",
                     provider=lambda **kw: pytest.fail("duplicate call"))
    assert len(load_events(Path(report["path"]))) == 1
    assert all(sha256_file(p) == h for p, h in protected.items())
    dev = machine_annotate(annotation_config, "development", model="synthetic", provider=fake)
    assert dev["complete"] and "not independent human accuracy" in dev["interpretation"]


@pytest.mark.parametrize("response,code", [("not json", "invalid_output"), ("", "empty_output")])
def test_failures_are_explicit_and_resumable(annotation_config, response, code):
    _complete_pilot(annotation_config)
    freeze(annotation_config)
    result = machine_annotate(annotation_config, "training", model="synthetic",
                              provider=lambda **kw: (response, None))
    assert not result["complete"] and result["unresolved_failures"] == 1
    events = load_events(Path(result["path"]))
    assert events[0].error_code == code and events[0].decision is None
    result = machine_annotate(annotation_config, "training", model="synthetic", provider=fake)
    assert result["complete"]
    assert [e.attempt for e in load_events(Path(result["path"]))] == [1, 2]


def test_provider_error_is_sanitized_and_credentials_missing_no_labels(annotation_config, monkeypatch):
    _complete_pilot(annotation_config)
    freeze(annotation_config)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(AnnotationError, match="missing"):
        machine_annotate(annotation_config, "training", model="synthetic")
    assert not list((annotation_config.annotation.output_dir / "machine").rglob("*.jsonl"))
    def fail(**kwargs):
        raise RuntimeError("SYNTHETIC_SECRET_MUST_NOT_BE_LOGGED")
    report = machine_annotate(annotation_config, "training", model="synthetic", provider=fail)
    contents = Path(report["path"]).read_text(encoding="utf-8")
    assert "provider_error" in contents and "SYNTHETIC_SECRET" not in contents


def test_drift_invalid_output_and_tampered_records(annotation_config):
    _complete_pilot(annotation_config)
    freeze(annotation_config)
    invalid = json.loads(fake(message={
        "example_id": "x", "customer_text_redacted": "x",
        "context_texts_redacted": [], "context_inbound": [],
    })[0])
    invalid["primary_intent"] = "invented_intent"
    report = machine_annotate(annotation_config, "training", model="synthetic",
                              provider=lambda **kw: (json.dumps(invalid), None))
    assert report["unresolved_failures"] == 1
    path = Path(report["path"])
    record = json.loads(path.read_text(encoding="utf-8"))
    record["provenance"]["model"] = "tampered"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(AnnotationError, match="provenance"):
        validate_machine_annotations(annotation_config, "training", model="synthetic")
    annotation_config.annotation.guide_path.write_text("changed", encoding="utf-8")
    with pytest.raises(AnnotationError, match="no longer matches"):
        machine_annotate(annotation_config, "training", model="synthetic", provider=fake)


def test_partial_human_record_protected_and_later_human_supersedes(annotation_config):
    _complete_pilot(annotation_config)
    freeze(annotation_config)
    report = machine_annotate(annotation_config, "training", model="synthetic", provider=fake)
    machine_bytes = Path(report["path"]).read_bytes()
    _save_valid(annotation_config, "train_1")
    report = machine_annotate(annotation_config, "training", model="synthetic",
                              provider=lambda **kw: pytest.fail("human record overwritten"))
    assert report["expected_machine"] == 0 and report["superseded_by_human"] == 1
    assert Path(report["path"]).read_bytes() == machine_bytes


def test_pydantic_rejects_reason_on_no_and_ambiguous_without_notes():
    value = dict(primary_intent="other_or_unclear", should_escalate="no",
                 escalation_reason_code="security_or_account_compromise", escalation_explanation=None,
                 risk_flags=[], ambiguity="clear", annotation_notes="", expected_reply_guidance="Synthetic")
    with pytest.raises(ValueError):
        MachineDecision(**value)
    value.update(escalation_reason_code=None, ambiguity="ambiguous")
    with pytest.raises(ValueError):
        MachineDecision(**value)


def test_sdk_adapter_request_shape_without_network(monkeypatch):
    from google import genai
    from google.genai.types import GenerateContentConfig
    seen = {}
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["http_options"]["timeout"] == 60000
            from google.genai.types import HttpOptions
            HttpOptions.model_validate(kwargs["http_options"])
            assert kwargs["vertexai"] is False
            assert kwargs["http_options"]["retry_options"]["attempts"] == 1
            self.models = self
        def generate_content(self, **kwargs):
            seen.update(kwargs)
            GenerateContentConfig.model_validate(kwargs["config"])
            return type("Response", (), {"text": "{}", "model_version": "synthetic"})()
        def close(self):
            pass
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test-key")
    monkeypatch.setattr(genai, "Client", Client)
    provider = GeminiProvider()
    assert provider(model="synthetic", system="synthetic", schema=MachineDecision.model_json_schema(), message={}) == ("{}", "synthetic")
    assert seen["config"]["response_mime_type"] == "application/json"
    provider.close()


def test_golden_rejected_even_after_freeze(annotation_config, monkeypatch):
    _complete_pilot(annotation_config)
    freeze(annotation_config)
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **kw: pytest.fail("golden read"))
    with pytest.raises(AnnotationError, match="only training/development"):
        machine_annotate(annotation_config, "golden", model="synthetic", provider=fake)


def test_lock_and_truncated_jsonl_fail_closed(annotation_config):
    _complete_pilot(annotation_config)
    freeze(annotation_config)
    report = machine_annotate(annotation_config, "training", model="synthetic", provider=fake)
    path = Path(report["path"])
    lock = path.with_suffix(".lock")
    lock.touch()
    with pytest.raises(AnnotationError, match="locked"):
        machine_annotate(annotation_config, "training", model="synthetic", provider=fake)
    lock.unlink()
    path.write_text('{"unfinished":', encoding="utf-8")
    with pytest.raises(AnnotationError, match="invalid machine JSONL"):
        machine_annotate(annotation_config, "training", model="synthetic", provider=fake)
    assert path.read_text(encoding="utf-8") == '{"unfinished":'


def test_bounded_resume_and_input_tamper(annotation_config):
    _complete_pilot(annotation_config)
    freeze(annotation_config)
    # Allow both synthetic training records to be missing while retaining the
    # synthetic prior freeze. This fixture-only removal never touches real data.
    AnnotationStore(annotation_config, "training").label_path.unlink()
    report = machine_annotate(annotation_config, "training", model="synthetic", provider=fake, limit=1)
    assert not report["complete"] and report["not_attempted"] == 1
    report = machine_annotate(annotation_config, "training", model="synthetic", provider=fake, limit=1)
    assert report["complete"] and report["validated_successes"] == 2
    path = Path(report["path"])
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["input_sha256"] = "0" * 64
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    with pytest.raises(AnnotationError, match="fingerprint"):
        validate_machine_annotations(annotation_config, "training", model="synthetic")


def test_human_edit_during_request_discards_response(annotation_config):
    _complete_pilot(annotation_config)
    freeze(annotation_config)
    def racing(**kwargs):
        _save_valid(annotation_config, "train_1")
        return fake(**kwargs)
    with pytest.raises(AnnotationError, match="response discarded"):
        machine_annotate(annotation_config, "training", model="synthetic", provider=racing)
    assert not list((annotation_config.annotation.output_dir / "machine").rglob("*.jsonl"))


def test_new_prompt_and_model_have_distinct_runs(annotation_config, tmp_path):
    _complete_pilot(annotation_config)
    freeze(annotation_config)
    first = machine_annotate(annotation_config, "training", model="synthetic", provider=fake)
    second = machine_annotate(annotation_config, "training", model="synthetic-other", provider=fake)
    assert first["run_sha256"] != second["run_sha256"]
    prompt = tmp_path / "synthetic-prompt.txt"
    prompt.write_text("Synthetic changed prompt", encoding="utf-8")
    third = machine_annotate(annotation_config, "training", model="synthetic", provider=fake, prompt_path=prompt)
    assert third["run_sha256"] != first["run_sha256"]
    assert Path(first["path"]).is_file() and Path(second["path"]).is_file()


def test_configured_model_used_without_cli_override(annotation_config):
    _complete_pilot(annotation_config)
    freeze(annotation_config)
    def configured(**kwargs):
        assert kwargs['model'] == annotation_config.annotation.machine_model
        return fake(**kwargs)
    report = machine_annotate(annotation_config, 'training', provider=configured)
    assert report['complete']
    assert load_events(Path(report['path']))[0].provenance['model'] == 'gemini-2.5-flash'


@pytest.mark.parametrize('status', [400, 401, 403, 404, 429, 500])
def test_http_failures_stop_and_permanent_failures_are_not_retried(annotation_config, status):
    from google.genai.errors import APIError
    _complete_pilot(annotation_config)
    freeze(annotation_config)
    # Synthetic fixture only: make two entries eligible to prove stop-on-error.
    AnnotationStore(annotation_config, 'training').label_path.unlink()
    calls = []
    def fail(**kwargs):
        calls.append(kwargs['message']['example_id'])
        raise APIError(status, {'error': {'message': 'SYNTHETIC_SECRET'}})
    report = machine_annotate(annotation_config, 'training', model='synthetic', provider=fail)
    assert len(calls) == 1 and report['not_attempted'] == 1
    assert report['provider_failures'][0]['http_status'] == status
    assert 'SYNTHETIC_SECRET' not in Path(report['path']).read_text(encoding='utf-8')
    if status in {400, 401, 403, 404}:
        with pytest.raises(AnnotationError, match='not retried'):
            machine_annotate(annotation_config, 'training', model='synthetic', provider=fail)
        assert len(calls) == 1
    else:
        # Only an explicit subsequent invocation retries transient failures.
        resumed = machine_annotate(annotation_config, 'training', model='synthetic', provider=fake)
        assert resumed['complete']


def test_successes_preserved_when_later_provider_request_fails(annotation_config):
    from google.genai.errors import APIError
    _complete_pilot(annotation_config)
    freeze(annotation_config)
    AnnotationStore(annotation_config, 'training').label_path.unlink()
    first = machine_annotate(annotation_config, 'training', model='synthetic', provider=fake, limit=1)
    saved = Path(first['path']).read_bytes()
    def fail(**kwargs):
        raise APIError(403, {'error': {'message': 'Synthetic denied request'}})
    report = machine_annotate(annotation_config, 'training', model='synthetic', provider=fail)
    assert report['validated_successes'] == 1 and report['unresolved_failures'] == 1
    assert Path(report['path']).read_bytes().startswith(saved)
