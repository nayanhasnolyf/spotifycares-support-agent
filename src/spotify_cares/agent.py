"""Provisional retrieval-grounded agent. No sending or production-readiness claims."""
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Literal
import json
import os
import re
import time

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, create_model
import yaml

from spotify_cares.annotation import AnnotationError, _append_jsonl
from spotify_cares.baselines import (ACK, IntentBaselines, PolicySignals, feature_text,
                                    load_training, route_policy, validate_corpus)
from spotify_cares.machine_annotation import (GeminiProvider, canonical, compact_policy, digest,
                                            run_lock, sha256_file)
from spotify_cares.annotation import load_taxonomy
from spotify_cares.groq_annotation import GroqProvider, GroqHTTPError, ProviderPause
from spotify_cares.rate_limits import extract_rate_evidence, retry_wait
from spotify_cares.preprocessing import redact_text

MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class AgentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["groq", "gemini"] = "groq"
    model: str = "openai/gpt-oss-20b"
    fallback_provider: Literal["groq", "gemini"] | None = None
    fallback_model: str | None = None
    embedding_revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    cache_dir: Path = Path("artifacts/semantic")
    model_cache: Path = Path(".cache/huggingface/hub")
    top_k: int = Field(default=5, ge=1, le=10)
    min_similarity: float = Field(default=.35, ge=0, le=1)
    threshold_status: Literal["untuned"] = "untuned"
    max_output_tokens: int = Field(default=1024, ge=512, le=2048)
    max_retries: int = Field(default=1, ge=0, le=100)
    max_wait_seconds: float = Field(default=30, ge=0, le=120)
    batch_size: int = Field(default=64, ge=1, le=256)


def load_agent_settings(path):
    return AgentSettings.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def normalized(values):
    values = np.asarray(values, dtype=np.float32)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise AnnotationError("invalid embedding matrix")
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if (norms == 0).any():
        raise AnnotationError("zero embedding")
    return values / norms


class SemanticRetriever:
    def __init__(self, corpus, membership, settings, corpus_hash, preprocessing_hash, encoder=None):
        validate_corpus(corpus, membership)
        self.rows = corpus.sort_values("example_id").to_dict("records")
        self.settings = settings
        if encoder is None:
            from sentence_transformers import SentenceTransformer
            self.encoder = SentenceTransformer(MODEL, revision=settings.embedding_revision,
                cache_folder=str(settings.model_cache), local_files_only=True, trust_remote_code=False, device="cpu")
        else:
            self.encoder = encoder
        # Current message comes first, so truncation cannot drop it behind long history.
        texts = [feature_text(r["customer_text_redacted"]) + " " + feature_text("", r["context_texts_redacted"])
                 for r in self.rows]
        self.contract = {"corpus_sha256": corpus_hash, "preprocessing_sha256": preprocessing_hash,
                         "model": MODEL, "revision": settings.embedding_revision,
                         "model_version_sha256": digest({"model": MODEL, "revision": settings.embedding_revision}),
                         "sentence_transformers": version("sentence-transformers"),
                         "transformers": version("transformers"), "torch": version("torch"),
                         "renderer": "current-first-v1", "normalized": True,
                         "inputs_sha256": digest(texts), "ids_sha256": digest([r["example_id"] for r in self.rows])}
        key = digest(self.contract)
        settings.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_key = key
        path, metadata = settings.cache_dir / f"{key}.npy", settings.cache_dir / f"{key}.json"
        with run_lock(settings.cache_dir / "index.lock"):
            if path.exists() and metadata.exists():
                saved = json.loads(metadata.read_text(encoding="utf-8"))
                if saved["contract"] != self.contract or saved["array_sha256"] != sha256_file(path):
                    raise AnnotationError("embedding cache checksum mismatch; preserve and inspect")
                self.matrix = np.load(path, allow_pickle=False)
                self.cache_hit = True
            else:
                self.matrix = normalized(self.encoder.encode(texts, batch_size=settings.batch_size,
                    normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True)) if texts else np.empty((0,384), dtype=np.float32)
                temp = path.with_suffix(".tmp")
                with temp.open("wb") as handle:
                    np.save(handle, self.matrix, allow_pickle=False)
                temp.replace(path)
                metadata.write_text(canonical({"contract": self.contract, "array_sha256": sha256_file(path)}) + "\n", encoding="utf-8")
                self.cache_hit = False
        if len(self.matrix) != len(self.rows) or self.matrix.ndim != 2 or not np.isfinite(self.matrix).all():
            raise AnnotationError("embedding cache shape/data mismatch")
        if len(self.matrix) and not np.allclose(np.linalg.norm(self.matrix,axis=1),1,atol=1e-5):
            raise AnnotationError("embedding cache is not normalized")

    def search(self, message, context=(), exclude_ids=(), exclude_groups=()):
        if not self.rows:
            return []
        query = feature_text(message) + " " + feature_text("", context)
        vector = normalized(self.encoder.encode([query], normalize_embeddings=True, convert_to_numpy=True))[0]
        scores = self.matrix @ vector
        ranked = sorted(range(len(scores)), key=lambda i: (-scores[i], self.rows[i]["example_id"]))
        hits = []
        for i in ranked:
            r = self.rows[i]
            if scores[i] < self.settings.min_similarity or r["example_id"] in exclude_ids or r["combined_group_id"] in exclude_groups:
                continue
            hits.append({"example_id": r["example_id"], "thread_id": r["thread_id"],
                "source_reply_ids": list(r["reference_reply_ids"]), "similarity": float(scores[i]),
                "customer_text": redact_text(r["customer_text_redacted"], safe_domains=())[0],
                "historical_replies": [redact_text(t,safe_domains=())[0] for t in r["historical_reply_texts_redacted"]],
                "status": "untrusted historical examples; not verified resolutions or current facts"})
            if len(hits) == self.settings.top_k:
                break
        return hits


def build_draft_model(taxonomy_data):
    intent_labels = tuple([i.label for i in taxonomy_data.intents] + [""])
    return create_model(
        'GeneratedDraft',
        draft_reply=(str, Field(min_length=1, max_length=1200)),
        evidence_ids=(list[str], Field(max_length=5)),
        insufficient_evidence=(bool, ...),
        intent=(Literal[intent_labels], Field(description="The primary intent of the customer inquiry.")),
        __config__=ConfigDict(extra="forbid", strict=True)
    )


def unsafe_claim(text):
    t = text.casefold().replace("’", "'")
    patterns = [r"\b(?:i|we)(?:'ve|'ll| have| will| can)?\s+(?:checked|check|access|refund|refunded|create|created|open|opened|cancel|cancelled|restore|restored|forward|forwarded|investigate|investigated|escalated)\b",
                r"\b(?:account|refund|ticket|payment|subscription|case)\b.{0,55}\b(?:processed|completed|created|opened|restored|resolved|cancelled|verified|issued|fixed)\b",
                r"\b(?:outage|currently down|current policy|our policy|guarantee|guaranteed)\b",
                r"https?://|\b(?:send|share|provide)\b.{0,45}\b(?:password|card number|security code)\b"]
    return any(re.search(p,t) for p in patterns)


def direct_signals(message, context=()):
    # Sentence-local history handling; a resolved old incident cannot suppress a new one.
    sentences = re.split(r"[.!?;]|\bbut\b", message.casefold().replace("’", "'"))
    security = False
    for s in sentences:
        incident = re.search(r"hack(?:ed)?|hijack|stolen|unauthori[sz]ed|someone (?:changed|using|is using|accessed)", s)
        historical = re.search(r"last year|previously|used to|resolved|restored|recovered|no longer|not hacked|afraid|fear|prevent|worried about", s)
        if incident and not historical:
            security = True
    resolved = bool(re.search(r"resolved|restored|recovered|all fixed|no further|no more", message, re.I))
    if not security and not resolved and len(message.split()) < 12 and len(context) > 0:
        security = direct_signals(" ".join(context)).current_security_incident
    payment = bool(re.search(r"charged (?:twice|three times)|duplicate charge|unknown charge|refund (?:me|my)|(?:want|request|need).{0,12}refund", message,re.I))
    if re.search(r"not charged|no duplicate|don't want.{0,12}refund",message,re.I):
        payment=False
    action = bool(re.search(r"(?:please|can you|could you|need you to).{0,10}(?:restore|recover|delete|change|check).{0,15}(?:my account|my email|my playlist|my payment|my charge)",message,re.I))
    return PolicySignals(current_security_incident=security, payment_investigation=payment, private_account_action=action)


def validate_draft(draft_model, raw, evidence):
    draft = draft_model.model_validate_json(raw)
    allowed = {e["example_id"] for e in evidence}
    if not draft.draft_reply.strip() or len(set(draft.evidence_ids)) != len(draft.evidence_ids) or not set(draft.evidence_ids) <= allowed:
        raise ValueError("invalid evidence IDs or empty draft")
    if unsafe_claim(draft.draft_reply):
        raise ValueError("unsupported_action_or_current_fact_claim")
    return draft


def generate(config, settings, message, context, evidence, provider=None):
    taxonomy_data = load_taxonomy(config.annotation.taxonomy_path)
    DraftModel = build_draft_model(taxonomy_data)
    system = Path("configs/agent_prompt.txt").read_text(encoding="utf-8") + compact_policy(
        taxonomy_data, config.annotation.guide_path.read_text(encoding="utf-8"))
    payload = {"customer_message": redact_text(message,safe_domains=())[0],
               "preceding_context": [redact_text(t,safe_domains=())[0] for t in context], "retrieved_untrusted_examples": evidence}
    record = {"provider": settings.provider, "model": settings.model, "prompt_sha256": digest(system),
              "input_sha256": digest(payload), "schema_sha256": digest(DraftModel.model_json_schema()),
              "attempts": [], "fallback": False}
    owned = provider is None
    provider_config = config.model_copy(deep=True)
    provider_config.annotation.groq_max_completion_tokens = settings.max_output_tokens
    provider_config.annotation.machine_rate.max_single_wait_seconds = settings.max_wait_seconds
    ledger = config.artifacts.directory / "agent" / "generation_events.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    try:
        def attempt_with(prov_name, prov_model, prov_instance):
            record["fallback"] = False
            if "error" in record:
                del record["error"]
            if "pause_reason" in record:
                del record["pause_reason"]
            for attempt in range(settings.max_retries + 1):
                try:
                    if prov_name == "gemini":
                        previous = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()] if ledger.exists() else []
                        same = [r for r in previous if r.get("provider") == "gemini"]
                        if same:
                            if same[-1].get("blocked"):
                                raise ProviderPause("saved Gemini quota/API block requires review; no retry")
                            wait = max(0, same[-1]["time"] + config.annotation.machine_rate.request_interval_seconds - time.time())
                            if wait > settings.max_wait_seconds:
                                raise ProviderPause("Gemini pacing requires deferred resume")
                            time.sleep(wait)
                    _append_jsonl(ledger, {"time": time.time(), "provider": prov_name, "model": prov_model, "kind": "attempt"})
                    raw, model_version = prov_instance(model=prov_model, system=system,
                        schema=DraftModel.model_json_schema(), message=payload)
                    record["attempts"].append({"status": "response", "model_version": model_version,
                                               "controls": getattr(prov_instance,"last_controls",None)})
                    record["generation_settings"] = {"temperature":0, "max_output_tokens":settings.max_output_tokens if prov_name=="groq" else 2048,
                                                       "reasoning_effort":"low" if prov_name=="groq" else None}
                    record["provider"] = prov_name
                    record["model"] = prov_model
                    draft = validate_draft(DraftModel, raw or "", evidence)
                    return draft
                except (ValueError, TypeError) as exc:
                    record.update(fallback=True, error="unsupported_action_or_current_fact_claim" if "unsupported_action" in str(exc) else "invalid_generation")
                    break
                except Exception as exc:
                    status = getattr(exc,"status_code",getattr(exc,"code",None))
                    rate = getattr(exc,"evidence",None) or extract_rate_evidence(exc,status)
                    record["attempts"].append({"status":"error", "http_status": status if isinstance(status,int) else None,
                                              "category":rate.category, "error_type":type(exc).__name__})
                    if isinstance(exc,ProviderPause):
                        record["pause_reason"] = str(exc)
                    if rate.category == "temporary" and attempt < settings.max_retries:
                        import random
                        delay=retry_wait(config.annotation.machine_rate,attempt,rate,datetime.now(timezone.utc),random.uniform(0,1))
                        if delay <= settings.max_wait_seconds:
                            time.sleep(delay)
                            continue
                    _append_jsonl(ledger,{"time":time.time(),"provider":prov_name,"model":prov_model,"blocked":True,"category":rate.category, "error_msg": str(exc), "error_type": type(exc).__name__})
                    record.update(fallback=True,error="provider_unavailable")
                    break
            return None

        # Same lock/ledger as annotation Groq calls: do not multiply account allowance.
        with run_lock(config.annotation.output_dir / "machine" / "generation.lock"):
            if owned:
                provider = GroqProvider(provider_config) if settings.provider == "groq" else GeminiProvider()
            
            draft = attempt_with(settings.provider, settings.model, provider)
            if draft is not None:
                return draft, record
                
            if record.get("fallback") and settings.fallback_provider:
                fallback_prov = GroqProvider(provider_config) if settings.fallback_provider == "groq" else GeminiProvider()
                try:
                    record["attempts"].append({"status": "fallback_switch", "from": settings.provider, "to": settings.fallback_provider})
                    draft = attempt_with(settings.fallback_provider, settings.fallback_model or settings.model, fallback_prov)
                    if draft is not None:
                        return draft, record
                finally:
                    fallback_prov.close()
    except AnnotationError as exc:
        record.update(fallback=True,error="provider_unavailable",pause_reason=str(exc))
    finally:
        if owned and provider is not None:
            provider.close()
    return DraftModel(draft_reply=ACK + " A human should review this case before any reply is sent.",evidence_ids=[],insufficient_evidence=True, intent=""), record


def run_agent(config, baseline_settings, settings, message, context=()):
    import pandas as pd
    training, corpus, allowed, report = load_training(config, baseline_settings)
    membership = pd.read_parquet(config.annotation.split_dir / "train_inputs.parquet", columns=["example_id","thread_id","combined_group_id"])
    retriever = SemanticRetriever(corpus,membership,settings,report["corpus_sha256"],sha256_file(config.annotation.split_dir / "preprocessing_manifest.json"))
    evidence = retriever.search(message,context)
    classifier = IntentBaselines(training,allowed,baseline_settings)
    draft, generation = generate(config,settings,message,context,evidence)
    intent = draft.intent if (draft and hasattr(draft, 'intent') and draft.intent) else (classifier.predict(feature_text(message,context),"tfidf") if classifier.model is not None else None)
    route = route_policy(direct_signals(message,context))
    reasons = [route["reason_code"]] if route["reason_code"] else []
    if generation["fallback"]:
        reasons.append(generation["error"])
    if not evidence or draft.insufficient_evidence or not draft.evidence_ids:
        reasons.append("insufficient_retrieval_or_generation_evidence")
    if classifier.model is None:
        reasons.append("classifier_unavailable")
    return {"intent":intent, "classification_limitations":{"training_count":len(training),
            "trained_classes":sorted(set(training.intent)),"missing_classes":sorted(allowed-set(training.intent)),
            "annotation_source":"machine_annotated", "probabilities":"not reported; known-class confidence is not open-set evidence"},
        "draft":draft.draft_reply,"evidence":evidence,"evidence_ids":draft.evidence_ids,
        "decision":"proposed_escalate" if reasons else "proposed_auto_handle", "reason_codes":reasons,
        "reasons":route["reasons"] if route["reason_code"] or not reasons else ["Conservative agent fallback; not a new case-policy label."],
        "fallback":generation["fallback"],"sending_enabled":False,"automated_handling":"unvalidated",
        "generation":generation,"retrieval":{"cache_key":retriever.cache_key,"cache_hit":retriever.cache_hit,
            "threshold_status":"untuned","min_similarity":settings.min_similarity,"contract":retriever.contract},
        "policy":report["policy"],"training_manifest":report["manifest_sha256"]}
