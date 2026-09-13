"""Synthetic quota errors only; no live requests and no real waiting."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import httpx
import pytest
from google.genai.errors import APIError

from test_annotation import annotation_config, _complete_pilot
from test_machine_annotation import freeze, fake
from spotify_cares.annotation import AnnotationError, AnnotationStore
from spotify_cares.machine_annotation import machine_annotate, load_events
from spotify_cares.config import MachineRateSettings
from spotify_cares.rate_limits import extract_rate_evidence, retry_wait


def quota_error(quota_id=None, delay=None, reason=None, header=None, value=None):
    details = []
    if quota_id is not None:
        details.append({'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{
            'quotaMetric': 'generativelanguage.googleapis.com/generate_content_requests',
            'quotaId': quota_id, 'quotaValue': value,
            'quotaDimensions': {'project': 'SYNTHETIC_SECRET'},
            'description': 'SYNTHETIC_SECRET',
        }]})
    if delay is not None:
        details.append({'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': delay})
    if reason:
        details.append({'@type': 'type.googleapis.com/google.rpc.ErrorInfo', 'reason': reason})
    response = httpx.Response(429, headers={'Retry-After': header} if header else {})
    return APIError(429, {'error': {'message': 'SYNTHETIC_SECRET; please check billing details',
                                   'details': details}}, response)


@pytest.mark.parametrize('quota_id,category', [
    ('GenerateRequestsPerMinutePerProject', 'temporary'),
    ('GenerateInputTokensPerMinute', 'temporary'),
    ('GenerateRequestsPerDay', 'daily'),
    ('GenerateTokensPerDay', 'daily'),
    ('UnspecifiedLimit', 'unknown'),
])
def test_metric_classification_does_not_invent_window(quota_id, category):
    result = extract_rate_evidence(quota_error(quota_id, '12.5s'), 429)
    assert result.category == category
    assert result.violations[0].quota_id == quota_id
    assert result.retry_delay_seconds == 12.5
    assert 'SYNTHETIC_SECRET' not in result.model_dump_json()


def test_daily_overrides_retry_hint_and_billing_requires_explicit_evidence():
    assert extract_rate_evidence(quota_error('RequestsPerDay', '2s'), 429).category == 'daily'
    assert extract_rate_evidence(quota_error(), 429).category == 'unknown'
    assert extract_rate_evidence(quota_error(reason='BILLING_DISABLED'), 429).category == 'billing'
    assert extract_rate_evidence(quota_error('RequestsPerMinute', value='0'), 429).category == 'quota_unavailable'
    assert extract_rate_evidence(quota_error(reason='QUOTA_EXCEEDED', delay='2s'), 429).category == 'unknown'


def test_retry_info_retry_after_date_and_cap():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = extract_rate_evidence(quota_error(delay={'seconds': '3', 'nanos': 500000000},
        header='Thu, 01 Jan 2026 00:01:00 GMT'), 429, now=now)
    assert result.retry_delay_seconds == 3.5 and result.retry_after_seconds == 60
    assert result.retry_not_before == now + timedelta(seconds=60)
    settings = MachineRateSettings()
    assert retry_wait(settings, 0, result, now, 1) == 60  # server wait never truncated
    assert retry_wait(settings, 0, result, now + timedelta(seconds=70), 1) == 6
    assert retry_wait(settings, 1, result, now + timedelta(seconds=70), 1) == 11
    assert retry_wait(settings, 9, result, now + timedelta(seconds=70), 1) == 30


def test_secret_like_identifiers_and_invalid_delay_not_saved():
    result = extract_rate_evidence(quota_error('AIza' + 'a' * 35, 'secret', header='secret'), 429)
    assert result.violations[0].quota_id is None
    assert result.retry_not_before is None
    assert 'AIza' not in result.model_dump_json()


def setup(config, monkeypatch, **settings):
    _complete_pilot(config)
    freeze(config)
    rate = MachineRateSettings(**settings)
    configured = config.model_copy(update={'annotation': config.annotation.model_copy(update={'machine_rate': rate})})
    sleeps = []
    monkeypatch.setattr('spotify_cares.machine_annotation.time.sleep', sleeps.append)
    monkeypatch.setattr('spotify_cares.machine_annotation.random.uniform', lambda a,b: b)
    return configured, sleeps


def test_temporary_retry_preserves_failure_then_success_and_no_duplicates(annotation_config, monkeypatch):
    config, sleeps = setup(annotation_config, monkeypatch)
    calls = []
    def provider(**kwargs):
        calls.append(kwargs['message']['example_id'])
        if len(calls) == 1:
            raise quota_error('RequestsPerMinute', '2s')
        return fake(**kwargs)
    result = machine_annotate(config, 'training', model='synthetic', provider=provider)
    assert result['complete'] and calls == ['train_1', 'train_1']
    assert sleeps == [6]  # backoff floor plus deterministic test jitter
    events = load_events(Path(result['path']))
    assert [r.attempt for r in events] == [1, 2]
    assert events[0].rate_limit_evidence.category == 'temporary'
    assert events[1].request_controls['scheduler_version'] == 'bounded-rate-v1'
    before = Path(result['path']).read_bytes()
    resumed = machine_annotate(config, 'training', model='synthetic', provider=lambda **kw: pytest.fail('duplicate'))
    assert resumed['complete'] and Path(result['path']).read_bytes() == before


def test_retry_count_and_total_attempt_limit(annotation_config, monkeypatch):
    config, sleeps = setup(annotation_config, monkeypatch, max_retries=2)
    def provider(**kwargs):
        raise quota_error('RequestsPerMinute')
    result = machine_annotate(config, 'training', model='synthetic', provider=provider)
    assert len(load_events(Path(result['path']))) == 3
    assert sleeps == [6, 11]
    assert result['unresolved_failures'] == 1
    resumed = machine_annotate(config, 'training', model='synthetic', provider=provider, limit=1)
    assert len(load_events(Path(resumed['path']))) == 4  # limit counts retries too


@pytest.mark.parametrize('kind', ['daily', 'billing', 'unknown', 'long_wait'])
def test_stop_conditions_keep_failed_example_without_next_request(annotation_config, monkeypatch, kind):
    config, sleeps = setup(annotation_config, monkeypatch)
    AnnotationStore(config, 'training').label_path.unlink()  # synthetic fixture only
    error = {'daily': quota_error('RequestsPerDay', '2s'),
             'billing': quota_error(reason='BILLING_DISABLED'),
             'unknown': quota_error(), 'long_wait': quota_error('RequestsPerMinute', '3600s')}[kind]
    calls = []
    def provider(**kwargs):
        calls.append(kwargs['message']['example_id'])
        raise error
    result = machine_annotate(config, 'training', model='synthetic', provider=provider)
    assert len(calls) == 1 and result['unresolved_failures'] == 1 and result['not_attempted'] == 1
    assert not sleeps
    with pytest.raises(AnnotationError):
        machine_annotate(config, 'training', model='synthetic', provider=provider)
    assert len(calls) == 1


def test_pacing_between_successes_without_changing_run(annotation_config, monkeypatch):
    config, sleeps = setup(annotation_config, monkeypatch, request_interval_seconds=10)
    AnnotationStore(config, 'training').label_path.unlink()  # synthetic fixture only
    monkeypatch.setattr('spotify_cares.machine_annotation.time.monotonic', lambda: 100)
    result = machine_annotate(config, 'training', model='synthetic', provider=fake)
    assert result['complete'] and sleeps == [10]


def test_legacy_unknown_requires_explicit_acknowledgement(annotation_config, monkeypatch):
    config, sleeps = setup(annotation_config, monkeypatch)
    def fail(**kwargs):
        raise APIError(429, {})
    result = machine_annotate(config, 'training', model='synthetic', provider=fail)
    path = Path(result['path'])
    row = json.loads(path.read_text(encoding='utf-8'))
    row.pop('rate_limit_evidence')
    row.pop('request_controls')
    path.write_text(json.dumps(row)+'\n', encoding='utf-8')  # synthetic legacy event
    before = path.read_bytes()
    with pytest.raises(AnnotationError, match='unknown quota'):
        machine_annotate(config, 'training', model='synthetic', provider=fake)
    assert path.read_bytes() == before
    resumed = machine_annotate(config, 'training', model='synthetic', provider=fake, retry_unknown_quota=True)
    assert resumed['complete'] and path.read_bytes().startswith(before)


def test_total_retry_wait_budget(annotation_config, monkeypatch):
    config, sleeps = setup(annotation_config, monkeypatch, max_total_retry_wait_seconds=10)
    def provider(**kwargs):
        raise quota_error('RequestsPerMinute')
    result = machine_annotate(config, 'training', model='synthetic', provider=provider)
    assert sleeps == [6]
    assert len(load_events(Path(result['path']))) == 2
    assert 'wait budget' in result['halt_reason']
