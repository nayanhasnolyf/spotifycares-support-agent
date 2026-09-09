"""Privacy-aware preprocessing and leakage-resistant chronological splitting."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

import numpy as np
import pandas as pd


PREPROCESSING_VERSION = "spotify-preprocess-v1"
SPLITS = ("train", "development", "test_candidate")
OUTPUT_FILES = {
    "train_inputs": "train_inputs.parquet",
    "development_inputs": "development_inputs.parquet",
    "test_candidate_inputs": "test_candidate_inputs.parquet",
    "train_references": "train_references.parquet",
    "development_references": "development_references.parquet",
    "test_candidate_references": "test_candidate_references.parquet",
    "retrieval": "training_retrieval_corpus.parquet",
    "discovery": "taxonomy_discovery_sample.parquet",
    "quarantine": "quarantined_examples.parquet",
    "assignments": "split_assignments.parquet",
    "duplicates": "duplicate_groups.parquet",
    "near_pairs": "near_duplicate_pairs.parquet",
    "manifest": "preprocessing_manifest.json",
}
INPUT_COLUMNS = [
    "example_id", "combined_group_id", "thread_id", "customer_tweet_id",
    "customer_created_at_utc", "customer_text_normalized", "customer_text_redacted",
    "context_tweet_ids", "context_author_ids", "context_inbound",
    "context_created_at_utc", "context_texts_normalized", "context_texts_redacted",
    "quality_flags", "content_start_at_utc", "content_end_at_utc",
    "preprocessing_version", "source_dataset", "source_sha256",
]
REFERENCE_COLUMNS = [
    "example_id", "thread_id", "reference_reply_ids",
    "reference_reply_created_at_utc", "reference_reply_texts_normalized",
    "reference_reply_texts_redacted", "reference_status", "preprocessing_version",
]


class PreprocessingError(RuntimeError):
    """Raised when preprocessing inputs or split invariants are invalid."""


class LeakageError(PreprocessingError):
    """Raised when a generated pool violates a leakage invariant."""


@dataclass(frozen=True)
class PreprocessingResult:
    output_paths: dict[str, Path]
    manifest: dict[str, Any]


class _UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[value] != value:
            value, self.parent[value] = self.parent[value], root
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


def _as_list(value: object) -> list[Any]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _stable_id(prefix: str, values: Iterable[str]) -> str:
    payload = "\0".join(sorted(values)).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:16]}"


def normalize_text(text: object) -> str:
    """Normalize display artifacts and whitespace without linguistic simplification."""

    value = "" if text is None else str(text)
    replacements = {
        "â€™": "’", "â€˜": "‘", "â€œ": "“", "â€": "”",
        "â€“": "–", "â€”": "—", "Â ": " ", "\u00a0": " ",
    }
    for broken, repaired in replacements.items():
        value = value.replace(broken, repaired)
    value = value.replace("\u200b", "").replace("\ufeff", "")
    value = unicodedata.normalize("NFC", value)
    return re.sub(r"\s+", " ", value).strip()


def redact_text(
    text: str,
    *,
    brand_handles: Iterable[str] = ("spotify", "spotifycares"),
    safe_domains: Iterable[str] = ("spotify.com", "spoti.fi"),
) -> tuple[str, Counter[str]]:
    """Apply deterministic, role-aware best-effort redaction."""

    counts: Counter[str] = Counter()
    brand_names = {name.casefold().lstrip("@") for name in brand_handles}
    safe = tuple(domain.casefold() for domain in safe_domains)

    def substitute(pattern: str, replacement: str, value: str, label: str) -> str:
        result, count = re.subn(pattern, replacement, value, flags=re.IGNORECASE)
        counts[label] += count
        return result

    value = substitute(
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", text, "email"
    )

    def replace_url(match: re.Match[str]) -> str:
        raw = match.group(0)
        trailing = ""
        while raw and raw[-1] in ".,!?;:)]}":
            trailing = raw[-1] + trailing
            raw = raw[:-1]
        host = (urlsplit(raw).hostname or "").casefold()
        counts["url"] += 1
        if any(host == domain or host.endswith(f".{domain}") for domain in safe):
            counts["safe_domain_preserved"] += 1
            return f"[URL:{host}]{trailing}"
        return f"[URL]{trailing}"

    value = re.sub(r"https?://[^\s<>()]+|www\.[^\s<>()]+", replace_url, value, flags=re.I)
    value = substitute(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[IP]", value, "ip_address"
    )
    value = substitute(
        r"(?<![\w.])(?:\+?\d[\d\s().-]{7,}\d)(?!\w)",
        "[PHONE]",
        value,
        "phone",
    )

    def replace_handle(match: re.Match[str]) -> str:
        handle = match.group(1)
        if handle.casefold() in brand_names:
            counts["brand_handle"] += 1
            return "[BRAND]"
        counts["customer_handle"] += 1
        return "[CUSTOMER]"

    value = re.sub(r"(?<!\w)@([A-Za-z0-9_]+)", replace_handle, value)
    value = substitute(r"\b\d{6,}\b", "[NUMBER]", value, "long_number")
    return value, counts


def _duplicate_form(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def _shingles(text: str, size: int) -> set[str]:
    compact = re.sub(r"\s+", " ", text)
    return {compact[i : i + size] for i in range(max(1, len(compact) - size + 1))}


def detect_duplicate_links(
    records: list[dict[str, Any]],
    *,
    threshold: float,
    min_chars: int,
    shingle_size: int,
    candidate_keys: int,
    max_block_size: int,
) -> tuple[dict[str, str | None], list[dict[str, Any]], dict[str, int]]:
    """Find exact groups and conservative near-copy links without all-pairs search."""

    by_text: dict[str, list[str]] = defaultdict(list)
    redacted_by_id: dict[str, str] = {}
    for record in records:
        key = _duplicate_form(record["customer_text_normalized"])
        by_text[key].append(record["example_id"])
        redacted_by_id[record["example_id"]] = record["customer_text_redacted"]

    exact_group_for: dict[str, str | None] = {record["example_id"]: None for record in records}
    representative: dict[str, str] = {}
    for text, ids in by_text.items():
        representative[text] = min(ids)
        if len(ids) > 1:
            group_id = _stable_id("exact", ids)
            for example_id in ids:
                exact_group_for[example_id] = group_id

    texts = [text for text in sorted(by_text) if len(text) >= min_chars]
    shingle_sets = {text: _shingles(text, shingle_size) for text in texts}
    document_frequency: Counter[str] = Counter(
        shingle for shingles in shingle_sets.values() for shingle in shingles
    )
    blocks: dict[str, list[str]] = defaultdict(list)
    for text in texts:
        eligible = [
            shingle
            for shingle in shingle_sets[text]
            if 2 <= document_frequency[shingle] <= max_block_size
        ]
        for shingle in sorted(eligible, key=lambda item: (document_frequency[item], item))[
            :candidate_keys
        ]:
            blocks[shingle].append(text)

    candidates: set[tuple[str, str]] = set()
    for block in blocks.values():
        for left, right in combinations(sorted(set(block)), 2):
            candidates.add((left, right))

    near_rows: list[dict[str, Any]] = []
    for left, right in sorted(candidates):
        if min(len(left), len(right)) / max(len(left), len(right)) < threshold:
            continue
        similarity = SequenceMatcher(None, left, right, autojunk=False).ratio()
        if similarity >= threshold:
            left_id, right_id = representative[left], representative[right]
            near_rows.append(
                {
                    "left_example_id": left_id,
                    "right_example_id": right_id,
                    "similarity": float(similarity),
                    "left_text_redacted": redacted_by_id[left_id],
                    "right_text_redacted": redacted_by_id[right_id],
                }
            )
    near_nodes = {
        edge[key]
        for edge in near_rows
        for key in ("left_example_id", "right_example_id")
    }
    near_union = _UnionFind(near_nodes)
    for edge in near_rows:
        near_union.union(edge["left_example_id"], edge["right_example_id"])
    near_components = Counter(near_union.find(node) for node in near_nodes)
    stats = {
        "exact_duplicate_groups": sum(len(ids) > 1 for ids in by_text.values()),
        "examples_in_exact_duplicate_groups": sum(
            len(ids) for ids in by_text.values() if len(ids) > 1
        ),
        "near_candidate_pairs_evaluated": len(candidates),
        "near_duplicate_pairs": len(near_rows),
        "near_duplicate_groups": len(near_components),
        "representatives_in_near_duplicate_groups": len(near_nodes),
        "short_messages_skipped_for_near_matching": sum(
            len(ids) for text, ids in by_text.items() if len(text) < min_chars
        ),
    }
    return exact_group_for, near_rows, stats


def _all_times(record: dict[str, Any]) -> list[pd.Timestamp]:
    raw = [record["customer_created_at_utc"]]
    raw.extend(_as_list(record["context_created_at_utc"]))
    raw.extend(_as_list(record["reference_reply_created_at_utc"]))
    return [pd.to_datetime(value, utc=True, errors="coerce") for value in raw]


def _preprocess_records(
    examples: pd.DataFrame,
    tweets: pd.DataFrame,
    conversations: pd.DataFrame,
    support_author_id: str,
    safe_domains: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Counter[str]]:
    tweet_by_id = tweets.set_index("tweet_id").to_dict(orient="index")
    conversation_flags = {
        row.thread_id: set(_as_list(row.quality_flags))
        for row in conversations.itertuples(index=False)
    }
    processed: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    redaction_counts: Counter[str] = Counter()

    for source in examples.to_dict(orient="records"):
        example_id = str(source["example_id"])
        customer_id = str(source["customer_tweet_id"])
        customer = tweet_by_id.get(customer_id)
        reply_ids = [str(value) for value in _as_list(source["reference_reply_ids"])]
        context_ids = [str(value) for value in _as_list(source["context_tweet_ids"])]
        reasons: set[str] = set()
        if customer is None or customer.get("inbound") != True:  # noqa: E712
            reasons.add("invalid_customer_record")
        if not normalize_text(source["customer_text"]):
            reasons.add("missing_customer_text")
        if not reply_ids:
            reasons.add("missing_reference_reply")
        for reply_id in reply_ids:
            reply = tweet_by_id.get(reply_id)
            if (
                reply is None
                or reply.get("author_id") != support_author_id
                or reply.get("inbound") != False  # noqa: E712
                or reply.get("in_response_to_tweet_id") != customer_id
            ):
                reasons.add("invalid_customer_brand_pairing")
        flags = set(_as_list(source["quality_flags"]))
        thread_flags = conversation_flags.get(source["thread_id"], set())
        if "cross_brand_ambiguous" in flags | thread_flags:
            reasons.add("cross_brand_ambiguous")
        if flags.intersection(
            {
                "parent_response_disagrees", "response_child_disagrees",
                "conflicting_parent_claim", "conflicting_duplicate_tweet_id",
                "cyclic_relationships",
            }
        ):
            reasons.add("unresolved_relationship_conflict")
        if set(reply_ids).intersection({customer_id, *context_ids}):
            reasons.add("future_reply_in_input")

        customer_normalized = normalize_text(source["customer_text"])
        customer_redacted, counts = redact_text(
            customer_normalized,
            brand_handles=(support_author_id, "spotify"),
            safe_domains=safe_domains,
        )
        redaction_counts.update({f"customer.{key}": value for key, value in counts.items()})
        context_normalized = [normalize_text(value) for value in _as_list(source["context_texts"])]
        context_redacted = []
        for text in context_normalized:
            redacted, counts = redact_text(
                text,
                brand_handles=(support_author_id, "spotify"),
                safe_domains=safe_domains,
            )
            context_redacted.append(redacted)
            redaction_counts.update({f"context.{key}": value for key, value in counts.items()})
        reply_normalized = [
            normalize_text(value) for value in _as_list(source["reference_reply_texts"])
        ]
        reply_redacted = []
        for text in reply_normalized:
            redacted, counts = redact_text(
                text,
                brand_handles=(support_author_id, "spotify"),
                safe_domains=safe_domains,
            )
            reply_redacted.append(redacted)
            redaction_counts.update({f"reply.{key}": value for key, value in counts.items()})

        record = {
            **source,
            "example_id": example_id,
            "customer_tweet_id": customer_id,
            "context_tweet_ids": context_ids,
            "reference_reply_ids": reply_ids,
            "quality_flags": sorted(flags),
            "customer_text_normalized": customer_normalized,
            "customer_text_redacted": customer_redacted,
            "context_texts_normalized": context_normalized,
            "context_texts_redacted": context_redacted,
            "reference_reply_texts_normalized": reply_normalized,
            "reference_reply_texts_redacted": reply_redacted,
        }
        if reasons:
            excluded.append(
                {
                    "example_id": example_id,
                    "thread_id": source["thread_id"],
                    "customer_tweet_id": customer_id,
                    "customer_text_redacted": customer_redacted,
                    "reason_codes": sorted(reasons),
                    "combined_group_id": None,
                }
            )
        else:
            processed.append(record)
    return processed, excluded, redaction_counts


def _combine_groups(
    records: list[dict[str, Any]],
    exact_group_for: dict[str, str | None],
    near_rows: list[dict[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]], dict[str, int]]:
    ids = [record["example_id"] for record in records]
    union = _UnionFind(ids)
    by_thread: dict[str, list[str]] = defaultdict(list)
    by_exact: dict[str, list[str]] = defaultdict(list)
    for record in records:
        by_thread[str(record["thread_id"])].append(record["example_id"])
        exact_id = exact_group_for[record["example_id"]]
        if exact_id:
            by_exact[exact_id].append(record["example_id"])
    for group in list(by_thread.values()) + list(by_exact.values()):
        for example_id in group[1:]:
            union.union(group[0], example_id)
    for edge in near_rows:
        union.union(edge["left_example_id"], edge["right_example_id"])

    members: dict[str, list[str]] = defaultdict(list)
    for example_id in ids:
        members[union.find(example_id)].append(example_id)
    combined_for: dict[str, str] = {}
    for group in members.values():
        combined_id = _stable_id("combined", group)
        for example_id in group:
            combined_for[example_id] = combined_id
    exact_sizes = {key: len(value) for key, value in by_exact.items()}
    combined_sizes = Counter(combined_for.values())
    mapping = [
        {
            "example_id": record["example_id"],
            "thread_id": record["thread_id"],
            "normalized_customer_sha256": hashlib.sha256(
                _duplicate_form(record["customer_text_normalized"]).encode("utf-8")
            ).hexdigest(),
            "exact_duplicate_group_id": exact_group_for[record["example_id"]],
            "exact_duplicate_group_size": exact_sizes.get(
                exact_group_for[record["example_id"]] or "", 1
            ),
            "combined_group_id": combined_for[record["example_id"]],
            "combined_group_size": combined_sizes[combined_for[record["example_id"]]],
        }
        for record in records
    ]
    stats = {
        "combined_groups": len(combined_sizes),
        "largest_combined_group": max(combined_sizes.values(), default=0),
        "combined_groups_larger_than_100": sum(size > 100 for size in combined_sizes.values()),
    }
    return combined_for, mapping, stats


def _split_groups(
    records: list[dict[str, Any]],
    combined_for: dict[str, str],
    train_fraction: float,
    development_fraction: float,
) -> tuple[dict[str, str], dict[str, list[str]], pd.Timestamp, pd.Timestamp]:
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    invalid_groups: set[str] = set()
    usable_ends: list[pd.Timestamp] = []
    for record in records:
        group_id = combined_for[record["example_id"]]
        times = _all_times(record)
        if not times or any(pd.isna(value) for value in times):
            invalid_groups.add(group_id)
        else:
            record["content_start_at_utc"] = min(times).isoformat()
            record["content_end_at_utc"] = max(times).isoformat()
            usable_ends.append(max(times))
        by_group[group_id].append(record)
    if len(usable_ends) < 3:
        raise PreprocessingError("At least three timestamp-valid examples are required")
    ordered = sorted(usable_ends)
    first_index = min(len(ordered) - 2, max(1, int(len(ordered) * train_fraction)))
    second_index = min(
        len(ordered) - 1,
        max(first_index + 1, int(len(ordered) * (train_fraction + development_fraction))),
    )
    train_cutoff, test_cutoff = ordered[first_index], ordered[second_index]
    assignment: dict[str, str] = {}
    reasons: dict[str, list[str]] = {}
    for group_id, group in by_group.items():
        if group_id in invalid_groups:
            split = "quarantine"
            reason = ["combined_group_contains_unusable_timestamp"]
        else:
            starts = [pd.Timestamp(item["content_start_at_utc"]) for item in group]
            ends = [pd.Timestamp(item["content_end_at_utc"]) for item in group]
            group_start, group_end = min(starts), max(ends)
            if group_end < train_cutoff:
                split, reason = "train", []
            elif group_start >= train_cutoff and group_end < test_cutoff:
                split, reason = "development", []
            elif group_start >= test_cutoff:
                split, reason = "test_candidate", []
            else:
                split, reason = "quarantine", ["combined_group_spans_chronological_cutoff"]
        for record in group:
            assignment[record["example_id"]] = split
            reasons[record["example_id"]] = reason
    return assignment, reasons, train_cutoff, test_cutoff


def _write_table(rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    pd.DataFrame(rows, columns=columns).to_parquet(path, index=False)


def _pool_date_range(inputs: pd.DataFrame) -> dict[str, str | None]:
    if inputs.empty:
        return {"start": None, "end": None}
    return {
        "start": str(pd.to_datetime(inputs["content_start_at_utc"], utc=True).min()),
        "end": str(pd.to_datetime(inputs["content_end_at_utc"], utc=True).max()),
    }


def validate_split_outputs(output_dir: Path, relevant_tweets_path: Path) -> dict[str, bool]:
    """Load saved pools and fail on identity, graph, retrieval, or chronology leakage."""

    pools = {
        split: pd.read_parquet(output_dir / OUTPUT_FILES[f"{split}_inputs"])
        for split in SPLITS
    }
    references = {
        split: pd.read_parquet(output_dir / OUTPUT_FILES[f"{split}_references"])
        for split in SPLITS
    }
    retrieval = pd.read_parquet(output_dir / OUTPUT_FILES["retrieval"])
    discovery = pd.read_parquet(output_dir / OUTPUT_FILES["discovery"])
    tweets = pd.read_parquet(relevant_tweets_path)
    issues: list[str] = []

    def values(frame: pd.DataFrame, column: str) -> set[str]:
        return set(frame[column].astype(str))

    for left, right in combinations(SPLITS, 2):
        for column in ("example_id", "thread_id", "combined_group_id"):
            if values(pools[left], column).intersection(values(pools[right], column)):
                issues.append(f"{column} overlaps {left} and {right}")

    tweet_sets: dict[str, set[str]] = {}
    for split in SPLITS:
        ids: set[str] = set(pools[split]["customer_tweet_id"].astype(str))
        for column in ("context_tweet_ids",):
            ids.update(str(item) for row in pools[split][column] for item in _as_list(row))
        for row in references[split]["reference_reply_ids"]:
            ids.update(str(item) for item in _as_list(row))
        tweet_sets[split] = ids
    for left, right in combinations(SPLITS, 2):
        if tweet_sets[left].intersection(tweet_sets[right]):
            issues.append(f"tweet IDs overlap {left} and {right}")

    train_ids = values(pools["train"], "example_id")
    held_out_ids = values(pools["development"], "example_id") | values(
        pools["test_candidate"], "example_id"
    )
    retrieval_ids = values(retrieval, "example_id")
    if not retrieval_ids.issubset(train_ids) or retrieval_ids.intersection(held_out_ids):
        issues.append("held-out example appears in training retrieval")
    if not values(discovery, "example_id").issubset(train_ids):
        issues.append("non-training example appears in discovery sample")

    parent_for = dict(zip(tweets["tweet_id"].astype(str), tweets["in_response_to_tweet_id"]))
    for split in SPLITS:
        reply_for = {
            row.example_id: {str(value) for value in _as_list(row.reference_reply_ids)}
            for row in references[split].itertuples(index=False)
        }
        for row in pools[split].itertuples(index=False):
            context = [str(value) for value in _as_list(row.context_tweet_ids)]
            replies = reply_for.get(row.example_id, set())
            if replies.intersection({str(row.customer_tweet_id), *context}):
                issues.append(f"future reply leaked into input for {row.example_id}")
            ancestors: set[str] = set()
            current = parent_for.get(str(row.customer_tweet_id))
            while (
                current is not None
                and not pd.isna(current)
                and str(current) in parent_for
                and str(current) not in ancestors
            ):
                current_id = str(current)
                ancestors.add(current_id)
                current = parent_for.get(current_id)
            if set(context) != ancestors:
                issues.append(f"context is not the ancestor branch for {row.example_id}")

    nonempty = [split for split in SPLITS if not pools[split].empty]
    for earlier, later in zip(nonempty, nonempty[1:]):
        earlier_end = pd.to_datetime(pools[earlier]["content_end_at_utc"], utc=True).max()
        later_start = pd.to_datetime(pools[later]["content_start_at_utc"], utc=True).min()
        if earlier_end >= later_start:
            issues.append(f"chronology violated between {earlier} and {later}")
    if issues:
        raise LeakageError("; ".join(dict.fromkeys(issues)))
    return {
        "example_ids_disjoint": True,
        "conversation_ids_disjoint": True,
        "combined_groups_disjoint": True,
        "tweet_ids_disjoint": True,
        "retrieval_is_training_only": True,
        "discovery_is_training_only": True,
        "contexts_are_ancestor_only": True,
        "future_replies_excluded_from_inputs": True,
        "strict_chronology": True,
    }


def preprocess_and_split(
    examples_path: Path,
    relevant_tweets_path: Path,
    conversations_path: Path,
    output_dir: Path,
    *,
    support_author_id: str = "SpotifyCares",
    seed: int = 42,
    train_fraction: float = 0.70,
    development_fraction: float = 0.15,
    test_fraction: float = 0.15,
    near_duplicate_threshold: float = 0.92,
    near_duplicate_min_chars: int = 20,
    shingle_size: int = 4,
    candidate_keys: int = 4,
    max_block_size: int = 100,
    discovery_sample_size: int = 400,
    safe_domains: tuple[str, ...] = ("spotify.com", "spoti.fi"),
) -> PreprocessingResult:
    """Preprocess Stage 2 examples, group duplicates, and create chronological pools."""

    if not np.isclose(train_fraction + development_fraction + test_fraction, 1.0):
        raise ValueError("split fractions must sum to 1")
    for path in (examples_path, relevant_tweets_path, conversations_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required Stage 2 output not found: {path}")
    examples = pd.read_parquet(examples_path)
    tweets = pd.read_parquet(relevant_tweets_path)
    conversations = pd.read_parquet(conversations_path)
    records, excluded, redaction_counts = _preprocess_records(
        examples, tweets, conversations, support_author_id, safe_domains
    )
    exact_for, near_rows, duplicate_stats = detect_duplicate_links(
        records,
        threshold=near_duplicate_threshold,
        min_chars=near_duplicate_min_chars,
        shingle_size=shingle_size,
        candidate_keys=candidate_keys,
        max_block_size=max_block_size,
    )
    combined_for, duplicate_mapping, combined_stats = _combine_groups(
        records, exact_for, near_rows
    )
    assignments, split_reasons, train_cutoff, test_cutoff = _split_groups(
        records, combined_for, train_fraction, development_fraction
    )
    by_id = {record["example_id"]: record for record in records}
    assignment_rows = []
    quarantine_rows = list(excluded)
    for record in records:
        example_id = record["example_id"]
        record["combined_group_id"] = combined_for[example_id]
        split = assignments[example_id]
        reason_codes = split_reasons[example_id]
        assignment_rows.append(
            {
                "example_id": example_id,
                "thread_id": record["thread_id"],
                "combined_group_id": combined_for[example_id],
                "split": split,
                "reason_codes": reason_codes,
            }
        )
        if split == "quarantine":
            quarantine_rows.append(
                {
                    "example_id": example_id,
                    "thread_id": record["thread_id"],
                    "customer_tweet_id": record["customer_tweet_id"],
                    "customer_text_redacted": record["customer_text_redacted"],
                    "reason_codes": reason_codes,
                    "combined_group_id": combined_for[example_id],
                }
            )
    for item in excluded:
        assignment_rows.append(
            {
                "example_id": item["example_id"],
                "thread_id": item["thread_id"],
                "combined_group_id": None,
                "split": "excluded",
                "reason_codes": item["reason_codes"],
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    pool_frames: dict[str, pd.DataFrame] = {}
    for split in SPLITS:
        pool_records = [by_id[key] for key, value in assignments.items() if value == split]
        input_rows = [
            {
                **{column: record.get(column) for column in INPUT_COLUMNS},
                "preprocessing_version": PREPROCESSING_VERSION,
            }
            for record in pool_records
        ]
        reference_rows = [
            {
                "example_id": record["example_id"],
                "thread_id": record["thread_id"],
                "reference_reply_ids": record["reference_reply_ids"],
                "reference_reply_created_at_utc": _as_list(
                    record["reference_reply_created_at_utc"]
                ),
                "reference_reply_texts_normalized": record[
                    "reference_reply_texts_normalized"
                ],
                "reference_reply_texts_redacted": record[
                    "reference_reply_texts_redacted"
                ],
                "reference_status": "historical_reply_not_verified_resolution",
                "preprocessing_version": PREPROCESSING_VERSION,
            }
            for record in pool_records
        ]
        input_path = output_dir / OUTPUT_FILES[f"{split}_inputs"]
        reference_path = output_dir / OUTPUT_FILES[f"{split}_references"]
        _write_table(input_rows, INPUT_COLUMNS, input_path)
        _write_table(reference_rows, REFERENCE_COLUMNS, reference_path)
        pool_frames[split] = pd.DataFrame(input_rows, columns=INPUT_COLUMNS)

    train_records = [by_id[key] for key, value in assignments.items() if value == "train"]
    retrieval_rows = [
        {
            "example_id": record["example_id"],
            "thread_id": record["thread_id"],
            "combined_group_id": record["combined_group_id"],
            "customer_tweet_id": record["customer_tweet_id"],
            "customer_text_redacted": record["customer_text_redacted"],
            "context_tweet_ids": record["context_tweet_ids"],
            "context_texts_redacted": record["context_texts_redacted"],
            "reference_reply_ids": record["reference_reply_ids"],
            "historical_reply_texts_redacted": record["reference_reply_texts_redacted"],
            "reference_status": "historical_reply_not_verified_resolution",
        }
        for record in train_records
    ]
    retrieval_columns = list(retrieval_rows[0]) if retrieval_rows else ["example_id"]
    _write_table(retrieval_rows, retrieval_columns, output_dir / OUTPUT_FILES["retrieval"])
    discovery_order = sorted(
        train_records,
        key=lambda record: hashlib.sha256(
            f"{seed}:{record['example_id']}".encode("utf-8")
        ).hexdigest(),
    )[: min(discovery_sample_size, len(train_records))]
    discovery_rows = [
        {
            "example_id": record["example_id"],
            "thread_id": record["thread_id"],
            "combined_group_id": record["combined_group_id"],
            "customer_tweet_id": record["customer_tweet_id"],
            "customer_text_redacted": record["customer_text_redacted"],
            "context_tweet_ids": record["context_tweet_ids"],
            "context_texts_redacted": record["context_texts_redacted"],
            "quality_flags": record["quality_flags"],
        }
        for record in discovery_order
    ]
    discovery_columns = list(discovery_rows[0]) if discovery_rows else ["example_id"]
    _write_table(discovery_rows, discovery_columns, output_dir / OUTPUT_FILES["discovery"])
    _write_table(
        quarantine_rows,
        [
            "example_id", "thread_id", "customer_tweet_id", "customer_text_redacted",
            "reason_codes", "combined_group_id",
        ],
        output_dir / OUTPUT_FILES["quarantine"],
    )
    _write_table(
        assignment_rows,
        ["example_id", "thread_id", "combined_group_id", "split", "reason_codes"],
        output_dir / OUTPUT_FILES["assignments"],
    )
    _write_table(
        duplicate_mapping,
        [
            "example_id", "thread_id", "normalized_customer_sha256",
            "exact_duplicate_group_id", "exact_duplicate_group_size",
            "combined_group_id", "combined_group_size",
        ],
        output_dir / OUTPUT_FILES["duplicates"],
    )
    _write_table(
        near_rows,
        [
            "left_example_id", "right_example_id", "similarity",
            "left_text_redacted", "right_text_redacted",
        ],
        output_dir / OUTPUT_FILES["near_pairs"],
    )

    checks = validate_split_outputs(output_dir, relevant_tweets_path)
    quarantine_counts = Counter(
        reason for row in quarantine_rows for reason in row["reason_codes"]
    )
    output_hashes = {
        key: _sha256_file(output_dir / filename)
        for key, filename in OUTPUT_FILES.items()
        if key != "manifest"
    }
    combined_counts = Counter(combined_for.values())
    largest = [
        {"combined_group_id": group_id, "size": size}
        for group_id, size in sorted(
            combined_counts.items(), key=lambda item: (-item[1], item[0])
        )[:10]
    ]
    manifest: dict[str, Any] = {
        "preprocessing_version": PREPROCESSING_VERSION,
        "source": {
            "examples_path": str(examples_path),
            "examples_sha256": _sha256_file(examples_path),
            "relevant_tweets_path": str(relevant_tweets_path),
            "relevant_tweets_sha256": _sha256_file(relevant_tweets_path),
            "source_dataset_sha256": str(examples.iloc[0]["source_sha256"]),
        },
        "configuration": {
            "seed": seed,
            "target_fractions": {
                "train": train_fraction,
                "development": development_fraction,
                "test_candidate": test_fraction,
            },
            "near_duplicate_threshold": near_duplicate_threshold,
            "near_duplicate_min_chars": near_duplicate_min_chars,
            "shingle_size": shingle_size,
            "candidate_keys": candidate_keys,
            "max_block_size": max_block_size,
            "discovery_sample_size": discovery_sample_size,
            "safe_url_domains": list(safe_domains),
        },
        "chronology": {
            "method": "strict_chronological_with_boundary_group_quarantine",
            "train_development_cutoff_utc": train_cutoff.isoformat(),
            "development_test_cutoff_utc": test_cutoff.isoformat(),
            "strict_chronology_achieved": checks["strict_chronology"],
            "pool_date_ranges": {
                split: _pool_date_range(pool_frames[split]) for split in SPLITS
            },
        },
        "counts": {
            "stage2_examples": len(examples),
            "eligible_before_chronology": len(records),
            "train": len(pool_frames["train"]),
            "development": len(pool_frames["development"]),
            "test_candidate": len(pool_frames["test_candidate"]),
            "quarantined": len(quarantine_rows),
            "structurally_excluded": len(excluded),
            "discovery_sample": len(discovery_rows),
            "retrieval_records": len(retrieval_rows),
        },
        "redaction_counts": dict(sorted(redaction_counts.items())),
        "duplicate_statistics": {
            **duplicate_stats,
            **combined_stats,
            "largest_combined_groups": largest,
        },
        "quarantine_by_reason": dict(sorted(quarantine_counts.items())),
        "leakage_checks": checks,
        "output_sha256": output_hashes,
        "near_duplicate_review_sample": near_rows[:10],
        "limitations": [
            "Automated redaction reduces detectable personal information but is not anonymization.",
            "Near-duplicate blocking can miss copies that share no selected rare character shingles.",
            "Large duplicate-connected groups are quarantined at cutoffs rather than split apart.",
            "Historical SpotifyCares replies are not verified resolutions or current policy.",
        ],
    }
    with (output_dir / OUTPUT_FILES["manifest"]).open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return PreprocessingResult(
        output_paths={key: output_dir / value for key, value in OUTPUT_FILES.items()},
        manifest=manifest,
    )
