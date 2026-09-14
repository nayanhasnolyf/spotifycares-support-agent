"""Groq transport and conservative persistent budgets; no raw error logging.

The caller holds the global machine-generation lock. This ledger coordinates this
repository only, not other clients sharing an organization. Server evidence can
lower operator ceilings, never silently raise them.
"""

from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import re
import time
from types import SimpleNamespace

import httpx

from spotify_cares.annotation import AnnotationError, _append_jsonl
from spotify_cares.rate_limits import RateEvidence, QuotaViolation, extract_rate_evidence

GROQ_GENERATION_SETTINGS = {"temperature": 0, "max_completion_tokens": 2048,
                            "reasoning_effort": "low", "stream": False}
STRICT_MODELS = {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}


def generation_settings(config):
    return {**GROQ_GENERATION_SETTINGS,
            "max_completion_tokens": config.annotation.groq_max_completion_tokens}


def usage_fields(data):
    """Only actual numeric provider usage; absent fields stay absent, never zero-filled."""
    value = data.get("usage")
    if not isinstance(value, dict):
        return None
    result = {k: value[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")
              if type(value.get(k)) is int and value[k] >= 0}
    for kind, key in (("prompt_tokens_details", "cached_tokens"),
                      ("completion_tokens_details", "reasoning_tokens")):
        details = value.get(kind, {})
        if isinstance(details, dict) and type(details.get(key)) is int and details[key] >= 0:
            result[kind] = {key: details[key]}
    return result or None


class ProviderPause(AnnotationError):
    """No generation attempt was made; defer without a fake failed label."""


class GroqHTTPError(Exception):
    def __init__(self, status, evidence):
        self.status, self.evidence = status, evidence
        super().__init__(f"Groq HTTP {status}; {evidence.category}")


def duration(value):
    """Groq reset durations, e.g. 2m59.56s; never retain arbitrary headers."""
    if not isinstance(value, str) or not re.fullmatch(r"(?:\d+(?:\.\d+)?(?:ms|[dhms]))+", value):
        return None
    total = sum(float(n) * {"d": 86400, "h": 3600, "m": 60, "s": 1, "ms": .001}[unit]
                for n, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|[dhms])", value))
    return total if math.isfinite(total) else None


def quota_headers(headers):
    result = {}
    for group in ("requests", "tokens"):
        for kind in ("limit", "remaining"):
            value = headers.get(f"x-ratelimit-{kind}-{group}")
            if value is not None and re.fullmatch(r"\d{1,18}", str(value)):
                result[f"{kind}_{group}"] = int(value)
        seconds = duration(headers.get(f"x-ratelimit-reset-{group}"))
        if seconds is not None:
            result[f"reset_{group}_seconds"] = seconds
    return result


def token_reservation(payload):
    """Local GPT-OSS estimate, not provider billing; reserve schema + framing margin."""
    import tiktoken
    from spotify_cares.machine_annotation import canonical
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(Path(".cache/tiktoken").resolve()))
    try:
        encoding = tiktoken.get_encoding("o200k_harmony")
    except Exception:
        raise ProviderPause("tokenizer unavailable; initialize the ignored tokenizer cache with network access before generation") from None
    # Encode untrusted special-token-looking text as ordinary text, not control tokens.
    return math.ceil(len(encoding.encode(canonical(payload), disallowed_special=())) * 1.1) + 512


def error_evidence(response, now=None):
    now = now or datetime.now(timezone.utc)
    # Retry-After parser only. Raw response/error text never escapes this function.
    evidence = extract_rate_evidence(SimpleNamespace(details={}, response=response), response.status_code, now)
    try:
        body = response.json()
        error = body.get("error", {}) if isinstance(body, dict) else {}
        if not isinstance(error, dict):
            error = {}
    except ValueError:
        error = {}
    code = error.get("code")
    message = error.get("message", "")
    message = message if isinstance(message, str) else ""
    # Only extract known dimension markers, never the message or organization ID.
    dimensions = set(re.findall(r"\b(RPM|TPM|RPD|TPD|ITPM|OTPM)\b", message))
    names = {"RPM": "requests_per_minute", "TPM": "tokens_per_minute",
             "RPD": "requests_per_day", "TPD": "tokens_per_day",
             "ITPM": "input_tokens_per_minute", "OTPM": "output_tokens_per_minute"}
    evidence.violations = [QuotaViolation(metric=names[d]) for d in sorted(dimensions)]
    headers = quota_headers(response.headers)
    if code in {"billing_limit_reached", "billing_hard_limit_reached"}:
        evidence.category, evidence.reasons = "billing", [code]
    elif code == "insufficient_quota":
        evidence.category, evidence.reasons = "quota_unavailable", [code]
    elif dimensions & {"RPD", "TPD"} or headers.get("remaining_requests") == 0:
        evidence.category = "daily"
    elif response.status_code == 429:
        evidence.category = "temporary" if dimensions & {"RPM", "TPM", "ITPM", "OTPM"} or evidence.retry_not_before else "unknown"
    elif response.status_code in {500, 502, 503, 504}:
        evidence.category = "temporary"
    return evidence


class GroqProvider:
    def __init__(self, config, *, client=None):
        key = os.environ.get("GROQ_API_KEY", "").strip()
        if not key:
            raise AnnotationError("GROQ_API_KEY is missing; add it to the ignored project-root .env; no generation performed")
        self.config = config
        self.client = client or httpx.Client(
            base_url="https://api.groq.com/openai/v1/",
            headers={"Authorization": f"Bearer {key}"}, timeout=60, follow_redirects=False,
        )
        self.ledger = config.annotation.output_dir / "machine" / "groq_budget.jsonl"
        self.verified_models = set()
        self.last_controls = None

    def verify_model(self, model):
        if model not in STRICT_MODELS:
            raise ProviderPause("model is not in the documented strict-schema allowlist; review support before changing it")
        if model not in self.verified_models:
            response = self.client.get("models")
            if response.status_code != 200:
                raise GroqHTTPError(response.status_code, error_evidence(response))
            ids = {m["id"] for m in response.json().get("data", []) if m.get("active", True)}
            if model not in ids:
                raise ProviderPause("configured Groq model is not returned by the authenticated models endpoint")
            self.verified_models = ids
        return {"provider": "groq", "model": model, "listed_for_credentials": True,
                "structured_schema_live_verified": False,
                "limits": "unknown until response headers/account limits are inspected"}

    def _events(self):
        try:
            events = [json.loads(line) for line in self.ledger.read_text(encoding="utf-8").splitlines()] if self.ledger.exists() else []
            for event in events:
                if event["kind"] not in {"reservation", "response"} or not isinstance(event["model"], str):
                    raise ValueError
                if not math.isfinite(event["time"]) or event["time"] < 0:
                    raise ValueError
                if event["kind"] == "reservation" and any(type(event[k]) is not int or event[k] < 0 for k in ("input_tokens", "output_tokens", "tokens")):
                    raise ValueError
            return events
        except (ValueError, KeyError, TypeError):
            raise ProviderPause("invalid Groq budget ledger; preserve it and inspect locally") from None

    def budget_wait(self, model, input_tokens, output_tokens, now):
        rate = self.config.annotation.groq_rate
        events = [e for e in self._events() if e["model"] == model]
        reservations = [e for e in events if e["kind"] == "reservation" and e["time"] > now - 86400]
        responses = [e for e in events if e["kind"] == "response"]
        last_response = responses[-1] if responses else None
        if last_response and last_response.get("limit_category") in {"daily", "billing", "quota_unavailable"}:
            raise ProviderPause(f"saved Groq {last_response['limit_category']} limit requires account review; no request sent")
        latest = next((e for e in reversed(responses) if e.get("headers")), None)
        evidence = latest.get("headers", {}) if latest else {}
        token_limit = min(rate.tokens_per_minute, evidence.get("limit_tokens", rate.tokens_per_minute))
        daily_limit = rate.requests_per_day
        if "limit_requests" in evidence:
            daily_limit = min(daily_limit, evidence["limit_requests"]) if daily_limit else evidence["limit_requests"]
        tokens = input_tokens + output_tokens
        if daily_limit is not None and len(reservations) >= daily_limit:
            raise ProviderPause("Groq daily request budget exhausted; defer and check organization limits")
        if rate.tokens_per_day and sum(e["tokens"] for e in reservations) + tokens > rate.tokens_per_day:
            raise ProviderPause("Groq daily token budget exhausted; defer and check organization limits")
        wait = 0.0
        dimensions = [("requests", 1, rate.requests_per_minute), ("tokens", tokens, token_limit),
                      ("input_tokens", input_tokens, rate.input_tokens_per_minute),
                      ("output_tokens", output_tokens, rate.output_tokens_per_minute)]
        minute = sorted([e for e in reservations if e["time"] > now - 60], key=lambda e: e["time"])
        for name, cost, cap in dimensions:
            if cap is None:
                continue
            if cost > cap:
                raise ProviderPause(f"single request conservative {name} reservation exceeds configured/observed minute limit; no request sent")
            used = sum(1 if name == "requests" else e[name] for e in minute)
            for event in minute:
                if used + cost <= cap:
                    break
                used -= 1 if name == "requests" else event[name]
                wait = max(wait, event["time"] + 60.1 - now)
        if reservations:
            interval = max(self.config.annotation.machine_rate.request_interval_seconds,
                           60 / rate.requests_per_minute + .1)
            wait = max(wait, max(e["time"] for e in reservations) + interval - now)
        if latest:
            for dimension, cost in (("requests", 1), ("tokens", tokens)):
                remaining = evidence.get(f"remaining_{dimension}")
                if remaining is None or remaining >= cost:
                    continue
                reset = evidence.get(f"reset_{dimension}_seconds")
                if reset is None:
                    raise ProviderPause(f"Groq remaining {dimension} insufficient and reset unknown; check organization limits")
                wait = max(wait, latest["time"] + reset + .1 - now)
        return max(0, wait), evidence

    def __call__(self, *, model, system, schema, message):
        from spotify_cares.machine_annotation import canonical
        self.verify_model(model)
        payload = {"model": model, "messages": [{"role": "system", "content": system},
                    {"role": "user", "content": canonical(message)}],
                   "response_format": {"type": "json_schema", "json_schema": {
                       "name": "machine_annotation", "strict": True, "schema": schema}},
                   **generation_settings(self.config)}
        input_tokens = token_reservation(payload)
        output_tokens = payload["max_completion_tokens"]
        wait, observed = self.budget_wait(model, input_tokens, output_tokens, time.time())
        if wait > self.config.annotation.machine_rate.max_single_wait_seconds:
            raise ProviderPause(f"Groq request/token budget requires {wait:.1f}s wait; resume later")
        if wait:
            time.sleep(wait)
        # Save before the request: a crash/timeout must not erase spent allowance.
        self.last_controls = {"scheduler_version": "groq-token-reservation-v1",
                              "tiktoken_version": version("tiktoken"),
                              "tokenizer": "o200k_harmony", "tokenizer_margin": "10% + 512 framing tokens",
                              "operator_ceilings": self.config.annotation.groq_rate.model_dump(),
                              "observed_headers": observed,
                              "input_token_reservation": input_tokens,
                              "output_token_reservation": output_tokens}
        _append_jsonl(self.ledger, {"kind": "reservation", "time": time.time(), "model": model,
                                   "input_tokens": input_tokens, "output_tokens": output_tokens,
                                   "tokens": input_tokens + output_tokens})
        response = self.client.post("chat/completions", json=payload)
        headers = quota_headers(response.headers)
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        usage = usage_fields(data)
        rate_evidence = error_evidence(response) if response.status_code != 200 else None
        _append_jsonl(self.ledger, {"kind": "response", "time": time.time(), "model": model,
                                   "headers": headers, "http_status": response.status_code,
                                   "limit_category": rate_evidence.category if rate_evidence else None,
                                   "usage": usage})
        self.last_controls["response_headers"] = headers
        self.last_controls["usage"] = usage
        if response.status_code != 200:
            raise GroqHTTPError(response.status_code, rate_evidence)
        choices = data.get("choices", [])
        self.last_controls["finish_reason"] = choices[0].get("finish_reason") if choices else None
        # Length-limited or refused responses must not masquerade as success.
        if not choices or choices[0].get("finish_reason") != "stop":
            return None, data.get("model")
        return choices[0].get("message", {}).get("content"), data.get("model")

    def close(self):
        self.client.close()


def check_groq(config, model=None):
    provider = GroqProvider(config)
    try:
        return provider.verify_model(model or config.annotation.groq_model)
    except (httpx.HTTPError, GroqHTTPError):
        raise AnnotationError("Groq model availability check failed; no customer data sent; inspect account access") from None
    finally:
        provider.close()
