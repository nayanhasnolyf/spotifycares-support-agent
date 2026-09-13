"""Allowlisted Gemini quota evidence and bounded retry scheduling.

Never persist response bodies, error messages, project dimensions, or arbitrary headers.
"""

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from spotify_cares.config import MachineRateSettings


class QuotaViolation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str | None = None
    quota_id: str | None = None
    value: int | None = None


class RateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    category: Literal["temporary", "daily", "billing", "quota_unavailable", "unknown", "not_rate_limited"]
    violations: list[QuotaViolation] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    retry_delay_seconds: float | None = Field(default=None, ge=0)
    retry_after_seconds: float | None = Field(default=None, ge=0)
    retry_not_before: datetime | None = None

    @model_validator(mode="after")
    def aware_deadline(self):
        if self.retry_not_before is not None and self.retry_not_before.tzinfo is None:
            raise ValueError("retry deadline requires timezone")
        return self


def safe_identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_./-]{0,199}", value):
        return None
    if re.search(r"AIza|gh[pousr]_|sk-|(?i:secret|password|api.?key|token=)", value):
        return None
    return value


def duration_seconds(value):
    try:
        if isinstance(value, dict):
            seconds = float(value.get("seconds", 0)) + float(value.get("nanos", 0)) / 1e9
        elif isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d+)?s", value):
            seconds = float(value[:-1])
        else:
            return None
        return seconds if math.isfinite(seconds) and seconds >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def extract_rate_evidence(exc, http_status, now=None):
    now = now or datetime.now(timezone.utc)
    body = getattr(exc, "details", {})
    if isinstance(body, list) and len(body) == 1:
        body = body[0]
    error = body.get("error", body) if isinstance(body, dict) else {}
    if not isinstance(error, dict):
        error = {}
    reasons = []
    known_reasons = {
        "rate_limit_exceeded", "too_many_requests", "quota_exceeded",
        "RATE_LIMIT_EXCEEDED", "QUOTA_EXCEEDED", "DAILY_LIMIT_EXCEEDED",
        "BILLING_DISABLED", "BILLING_NOT_ACTIVE", "BILLING_ACCOUNT_CLOSED",
        "BILLING_ACCOUNT_SUSPENDED", "BILLING_HARD_LIMIT_REACHED",
    }
    for key in ("code", "type", "reason"):
        if isinstance(error.get(key), str) and error[key] in known_reasons:
            reasons.append(error[key])
    violations, delays = [], []
    details = error.get("details", [])
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        kind = detail.get("@type", "")
        if kind == "type.googleapis.com/google.rpc.RetryInfo":
            seconds = duration_seconds(detail.get("retryDelay", detail.get("retry_delay")))
            if seconds is not None:
                delays.append(seconds)
        elif kind == "type.googleapis.com/google.rpc.QuotaFailure":
            entries = detail.get("violations", [])
            for violation in entries if isinstance(entries, list) else []:
                if not isinstance(violation, dict):
                    continue
                raw_value = violation.get("quotaValue", violation.get("quota_value"))
                value = int(str(raw_value)) if re.fullmatch(r"\d{1,20}", str(raw_value)) else None
                violations.append(QuotaViolation(
                    metric=safe_identifier(violation.get("quotaMetric", violation.get("quota_metric"))),
                    quota_id=safe_identifier(violation.get("quotaId", violation.get("quota_id"))), value=value,
                ))
        elif kind == "type.googleapis.com/google.rpc.ErrorInfo" and detail.get("reason") in known_reasons:
            reasons.append(detail["reason"])
    retry_after = None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    header = headers.get("Retry-After", headers.get("retry-after"))
    if header is not None:
        try:
            if re.fullmatch(r"\d+(?:\.\d+)?", str(header)):
                retry_after = float(header)
            else:
                when = parsedate_to_datetime(str(header))
                if when.tzinfo is not None:
                    retry_after = max(0, (when - now).total_seconds())
            if retry_after is not None and not math.isfinite(retry_after):
                retry_after = None
        except (ValueError, TypeError, OverflowError):
            pass
    delay = max(delays) if delays else None
    provided = [v for v in (delay, retry_after) if v is not None]
    not_before = None
    if provided:
        try:
            not_before = now + timedelta(seconds=max(provided))
        except OverflowError:
            not_before = datetime.max.replace(tzinfo=timezone.utc)
    names = [re.sub(r"[^a-z]", "", ((v.metric or "") + (v.quota_id or "")).lower()) for v in violations]
    if any(r.startswith("BILLING_") for r in reasons):
        category = "billing"
    elif any("perday" in n or "daily" in n for n in names) or any(r in reasons for r in ("quota_exceeded", "DAILY_LIMIT_EXCEEDED")):
        category = "daily"
    elif any(v.value == 0 for v in violations):
        category = "quota_unavailable"
    elif http_status == 429 and (
        (names and all("perminute" in n or "persecond" in n for n in names))
        or (not violations and "QUOTA_EXCEEDED" not in reasons and (provided or any(r in reasons for r in ("rate_limit_exceeded", "too_many_requests", "RATE_LIMIT_EXCEEDED"))))
    ):
        category = "temporary"
    else:
        category = "unknown" if http_status == 429 else "not_rate_limited"
    return RateEvidence(category=category, violations=violations, reasons=sorted(set(reasons)),
                        retry_delay_seconds=delay, retry_after_seconds=retry_after,
                        retry_not_before=not_before)


def retry_wait(settings: MachineRateSettings, index: int, evidence: RateEvidence, now: datetime, jitter: float):
    """Never shorten a server minimum to fit the local cap; caller defers instead."""
    local = min(settings.max_backoff_seconds,
                settings.initial_backoff_seconds * 2 ** min(index, 20) + max(0, jitter))
    server = max(0, (evidence.retry_not_before - now).total_seconds()) if evidence.retry_not_before else 0
    return max(local, server)
