"""Chunked extraction and branch-safe reconstruction of SpotifyCares threads."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = (
    "tweet_id",
    "author_id",
    "inbound",
    "created_at",
    "text",
    "response_tweet_id",
    "in_response_to_tweet_id",
)
OUTPUT_FILENAMES = {
    "tweets": "relevant_tweets.parquet",
    "examples": "support_examples.parquet",
    "conversations": "conversations.parquet",
    "relationships": "relationships.parquet",
    "exclusions": "exclusions.parquet",
    "duplicates": "duplicate_records.parquet",
    "audit": "extraction_audit.json",
}


class ExtractionError(RuntimeError):
    """Raised when source data violates a required extraction contract."""


@dataclass(frozen=True)
class ExtractionResult:
    """Paths and headline counts from a completed extraction."""

    output_paths: dict[str, Path]
    audit: dict[str, Any]


def _clean_id(value: object) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


def _response_ids(value: object) -> list[str]:
    raw = "" if value is None else str(value)
    return list(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))


def _parent_id(value: object) -> tuple[str | None, list[str]]:
    raw = "" if value is None else str(value).strip()
    if not raw:
        return None, []
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) != 1:
        return None, ["invalid_parent_format"]
    return parts[0], []


def _inbound(value: object) -> tuple[int | None, list[str]]:
    raw = "" if value is None else str(value).strip().casefold()
    if raw == "true":
        return 1, []
    if raw == "false":
        return 0, []
    return None, ["invalid_inbound"]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _stable_id(prefix: str, values: Iterable[str]) -> str:
    payload = "\0".join(sorted(values)).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:16]}"


def _json_list(value: object) -> list[str]:
    if not value:
        return []
    return list(json.loads(str(value)))


def _redact(text: str | None) -> str | None:
    """Best-effort redaction for local audit excerpts, not dataset publication."""

    if text is None:
        return None
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", text)
    value = re.sub(r"https?://\S+|www\.\S+", "[URL]", value)
    value = re.sub(r"(?<!\w)@[A-Za-z0-9_]+", "[USER]", value)
    value = re.sub(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)", "[PHONE]", value)
    value = re.sub(r"\b\d{6,}\b", "[NUMBER]", value)
    return value[:500]


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("PRAGMA temp_store=MEMORY")
    connection.execute("PRAGMA cache_size=-131072")
    return connection


def _validate_header(csv_path: Path) -> None:
    columns = tuple(pd.read_csv(csv_path, nrows=0).columns)
    missing = sorted(set(REQUIRED_COLUMNS) - set(columns))
    if missing:
        raise ExtractionError(f"CSV is missing required columns: {', '.join(missing)}")


def _ingest_metadata(
    csv_path: Path, connection: sqlite3.Connection, chunk_size: int
) -> dict[str, int]:
    connection.executescript(
        """
        CREATE TABLE records (
            source_record INTEGER PRIMARY KEY,
            tweet_id TEXT,
            author_id TEXT,
            inbound INTEGER,
            inbound_raw TEXT NOT NULL,
            created_at_raw TEXT NOT NULL,
            created_at_utc TEXT,
            text_missing INTEGER NOT NULL,
            response_ids_json TEXT NOT NULL,
            parent_id TEXT,
            parent_raw TEXT NOT NULL,
            flags_json TEXT NOT NULL,
            row_signature TEXT NOT NULL
        );
        """
    )
    counts: Counter[str] = Counter()
    record_offset = 0
    reader = pd.read_csv(
        csv_path,
        usecols=list(REQUIRED_COLUMNS),
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        chunksize=chunk_size,
    )
    insert_sql = "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"

    for chunk in reader:
        raw_times = chunk["created_at"].astype(str).str.strip()
        parsed_times = pd.to_datetime(
            raw_times.where(raw_times.ne("")),
            format="%a %b %d %H:%M:%S %z %Y",
            errors="coerce",
            utc=True,
        )
        iso_times = parsed_times.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        rows: list[tuple[Any, ...]] = []
        for position, values in enumerate(chunk.itertuples(index=False, name=None)):
            raw = dict(zip(REQUIRED_COLUMNS, values, strict=True))
            source_record = record_offset + position + 2
            tweet_id = _clean_id(raw["tweet_id"])
            author_id = _clean_id(raw["author_id"])
            inbound, flags = _inbound(raw["inbound"])
            parent_id, parent_flags = _parent_id(raw["in_response_to_tweet_id"])
            flags.extend(parent_flags)
            response_ids = _response_ids(raw["response_tweet_id"])
            created_raw = str(raw["created_at"]).strip()
            created_utc = None if pd.isna(iso_times.iloc[position]) else iso_times.iloc[position]
            text = str(raw["text"])
            if tweet_id is None:
                flags.append("missing_tweet_id")
                counts["missing_tweet_id_records"] += 1
            if author_id is None:
                flags.append("missing_author_id")
            if not created_raw:
                flags.append("missing_timestamp")
                counts["missing_timestamp_records"] += 1
            elif created_utc is None:
                flags.append("invalid_timestamp")
                counts["invalid_timestamp_records"] += 1
            if not text.strip():
                flags.append("missing_text")
                counts["missing_text_records"] += 1
            if inbound is None:
                counts["invalid_inbound_records"] += 1
            normalized = (
                author_id,
                inbound,
                created_utc or created_raw,
                text,
                response_ids,
                parent_id or str(raw["in_response_to_tweet_id"]).strip(),
            )
            signature = hashlib.sha256(
                json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            rows.append(
                (
                    source_record,
                    tweet_id,
                    author_id,
                    inbound,
                    str(raw["inbound"]).strip(),
                    created_raw,
                    created_utc,
                    int(not text.strip()),
                    json.dumps(response_ids),
                    parent_id,
                    str(raw["in_response_to_tweet_id"]).strip(),
                    json.dumps(sorted(set(flags))),
                    signature,
                )
            )
        with connection:
            connection.executemany(insert_sql, rows)
        record_offset += len(chunk)

    counts["total_rows_scanned"] = record_offset
    connection.executescript(
        """
        CREATE INDEX records_tweet_id_idx ON records(tweet_id);
        CREATE TABLE tweet_stats AS
            SELECT tweet_id,
                   MIN(source_record) AS canonical_source_record,
                   COUNT(*) AS record_count,
                   COUNT(DISTINCT row_signature) AS variant_count
            FROM records
            WHERE tweet_id IS NOT NULL
            GROUP BY tweet_id;
        CREATE UNIQUE INDEX tweet_stats_id_idx ON tweet_stats(tweet_id);
        CREATE TABLE tweets AS
            SELECT r.*, s.record_count AS duplicate_count,
                   CASE WHEN s.variant_count > 1 THEN 1 ELSE 0 END AS duplicate_conflict,
                   NULL AS text, 0 AS text_hydrated
            FROM records r
            JOIN tweet_stats s
              ON r.tweet_id = s.tweet_id
             AND r.source_record = s.canonical_source_record;
        CREATE UNIQUE INDEX tweets_id_idx ON tweets(tweet_id);
        CREATE INDEX tweets_parent_idx ON tweets(parent_id);
        CREATE INDEX tweets_author_idx ON tweets(author_id);
        """
    )
    duplicate = connection.execute(
        """SELECT COUNT(*), COALESCE(SUM(record_count - 1), 0),
                  COALESCE(SUM(CASE WHEN variant_count > 1 THEN 1 ELSE 0 END), 0)
           FROM tweet_stats WHERE record_count > 1"""
    ).fetchone()
    counts["duplicate_tweet_ids"] = int(duplicate[0])
    counts["duplicate_extra_records"] = int(duplicate[1])
    counts["conflicting_duplicate_tweet_ids"] = int(duplicate[2])
    return dict(counts)


def _index_responses(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE response_claims (
               parent_id TEXT NOT NULL, target_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
               PRIMARY KEY (parent_id, target_id)
           )"""
    )
    cursor = connection.execute("SELECT tweet_id, response_ids_json FROM tweets")
    while batch := cursor.fetchmany(50_000):
        rows = [
            (parent_id, target_id, ordinal)
            for parent_id, response_json in batch
            for ordinal, target_id in enumerate(_json_list(response_json))
        ]
        with connection:
            connection.executemany(
                "INSERT OR IGNORE INTO response_claims VALUES (?, ?, ?)", rows
            )
    connection.execute("CREATE INDEX response_target_idx ON response_claims(target_id)")


def _find_relevant_ids(connection: sqlite3.Connection, support_author_id: str) -> set[str]:
    variants = connection.execute(
        """SELECT author_id, COUNT(*) FROM tweets
           WHERE lower(author_id) = lower(?) GROUP BY author_id""",
        (support_author_id,),
    ).fetchall()
    if not variants:
        raise ExtractionError(f"Support author_id {support_author_id!r} was not found")
    exact_count = sum(count for author, count in variants if author == support_author_id)
    if exact_count == 0:
        found = ", ".join(repr(author) for author, _ in variants)
        raise ExtractionError(
            f"Expected exact support author_id {support_author_id!r}; found {found}"
        )

    connection.execute("CREATE TABLE relevant_ids (tweet_id TEXT PRIMARY KEY)")
    connection.execute(
        "INSERT INTO relevant_ids SELECT tweet_id FROM tweets WHERE author_id = ?",
        (support_author_id,),
    )
    while True:
        before = connection.total_changes
        connection.execute(
            """INSERT OR IGNORE INTO relevant_ids
               SELECT parent.tweet_id
               FROM tweets child
               JOIN relevant_ids known ON known.tweet_id = child.tweet_id
               JOIN tweets parent ON parent.tweet_id = child.parent_id"""
        )
        connection.execute(
            """INSERT OR IGNORE INTO relevant_ids
               SELECT child.tweet_id
               FROM tweets child
               JOIN relevant_ids known ON known.tweet_id = child.parent_id"""
        )
        if connection.total_changes == before:
            break
    return {row[0] for row in connection.execute("SELECT tweet_id FROM relevant_ids")}


def _hydrate_relevant_text(
    csv_path: Path,
    connection: sqlite3.Connection,
    relevant_ids: set[str],
    chunk_size: int,
) -> None:
    canonical = dict(
        connection.execute(
            "SELECT tweet_id, source_record FROM tweets JOIN relevant_ids USING(tweet_id)"
        )
    )
    record_offset = 0
    reader = pd.read_csv(
        csv_path,
        usecols=["tweet_id", "text"],
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        chunksize=chunk_size,
    )
    for chunk in reader:
        updates = []
        for position, (raw_id, text) in enumerate(
            chunk[["tweet_id", "text"]].itertuples(index=False, name=None)
        ):
            tweet_id = _clean_id(raw_id)
            source_record = record_offset + position + 2
            if tweet_id in relevant_ids and canonical[tweet_id] == source_record:
                updates.append((str(text), tweet_id))
        with connection:
            connection.executemany(
                "UPDATE tweets SET text = ?, text_hydrated = 1 WHERE tweet_id = ?",
                updates,
            )
        record_offset += len(chunk)
    hydrated = connection.execute(
        "SELECT COUNT(*) FROM tweets JOIN relevant_ids USING(tweet_id) WHERE text_hydrated = 1"
    ).fetchone()[0]
    if hydrated != len(relevant_ids):
        raise ExtractionError(
            f"Hydrated {hydrated} of {len(relevant_ids)} relevant canonical tweets"
        )


def _components(nodes: dict[str, dict[str, Any]]) -> tuple[list[list[str]], set[str]]:
    adjacency: dict[str, set[str]] = {tweet_id: set() for tweet_id in nodes}
    for tweet_id, node in nodes.items():
        parent_id = node["parent_id"]
        if parent_id in nodes:
            adjacency[tweet_id].add(parent_id)
            adjacency[parent_id].add(tweet_id)

    groups: list[list[str]] = []
    unseen = set(nodes)
    while unseen:
        root = min(unseen)
        stack = [root]
        group: list[str] = []
        unseen.remove(root)
        while stack:
            current = stack.pop()
            group.append(current)
            for neighbour in adjacency[current]:
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    stack.append(neighbour)
        groups.append(sorted(group))

    cycle_nodes: set[str] = set()
    completed: set[str] = set()
    for start in nodes:
        if start in completed:
            continue
        path: list[str] = []
        positions: dict[str, int] = {}
        current: str | None = start
        while current in nodes and current not in completed:
            if current in positions:
                cycle_nodes.update(path[positions[current] :])
                break
            positions[current] = len(path)
            path.append(current)
            current = nodes[current]["parent_id"]
        completed.update(path)
    return groups, cycle_nodes


def _timestamp_key(node: dict[str, Any]) -> tuple[int, str, int]:
    timestamp = node["created_at_utc"]
    return (0 if timestamp else 1, timestamp or "", int(node["source_record"]))


def _write_parquet(rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    pd.DataFrame(rows, columns=columns).to_parquet(path, index=False)


def _reconstruct(
    connection: sqlite3.Connection,
    support_author_id: str,
    source_name: str,
    source_sha256: str,
    output_dir: Path,
    ingest_counts: dict[str, int],
    audit_example_count: int,
) -> dict[str, Any]:
    relevant = pd.read_sql_query(
        """SELECT t.*,
                  CASE WHEN t.parent_id IS NULL THEN NULL
                       WHEN p.tweet_id IS NULL THEN 0 ELSE 1 END AS parent_exists
           FROM tweets t JOIN relevant_ids r USING(tweet_id)
           LEFT JOIN tweets p ON p.tweet_id = t.parent_id""",
        connection,
    )
    nodes: dict[str, dict[str, Any]] = {}
    for record in relevant.to_dict(orient="records"):
        record["response_tweet_ids"] = _json_list(record.pop("response_ids_json"))
        record["quality_flags"] = set(_json_list(record.pop("flags_json")))
        record["parent_id"] = record["parent_id"] or None
        if int(record["duplicate_count"]) > 1:
            record["quality_flags"].add("duplicate_tweet_id")
        if int(record["duplicate_conflict"]):
            record["quality_flags"].add("conflicting_duplicate_tweet_id")
        if record["parent_raw"] and (
            record["parent_id"] is None or record["parent_exists"] == 0
        ):
            record["quality_flags"].add("missing_parent")
        nodes[str(record["tweet_id"])] = record

    groups, cycle_nodes = _components(nodes)
    thread_for: dict[str, str] = {}
    component_for: dict[str, list[str]] = {}
    for group in groups:
        thread_id = _stable_id("thread", group)
        for tweet_id in group:
            thread_for[tweet_id] = thread_id
            component_for[tweet_id] = group

    claim_rows = connection.execute(
        """SELECT c.parent_id, c.target_id, c.ordinal,
                  child.tweet_id, child.parent_id, child.author_id, child.inbound
           FROM response_claims c
           JOIN relevant_ids relevant_parent ON relevant_parent.tweet_id = c.parent_id
           LEFT JOIN tweets child ON child.tweet_id = c.target_id
           ORDER BY c.parent_id, c.ordinal"""
    ).fetchall()
    claims = {(parent, target) for parent, target, *_ in claim_rows}
    cross_brand_threads: set[str] = set()
    relationship_rows: list[dict[str, Any]] = []

    for tweet_id, node in nodes.items():
        parent_id = node["parent_id"]
        if not parent_id:
            continue
        flags: list[str] = []
        response_claim = (parent_id, tweet_id) in claims
        if parent_id not in nodes:
            status = "missing_parent_target"
            flags.append("missing_parent")
        elif response_claim:
            status = "consistent"
        elif nodes[parent_id]["response_tweet_ids"]:
            status = "parent_response_disagrees"
            flags.append("conflicting_link")
            node["quality_flags"].add("parent_response_disagrees")
            nodes[parent_id]["quality_flags"].add("response_child_disagrees")
        else:
            status = "parent_response_unspecified"
        relationship_rows.append(
            {
                "thread_id": thread_for[tweet_id],
                "parent_tweet_id": parent_id,
                "child_tweet_id": tweet_id,
                "direct_parent_claim": True,
                "response_claim": response_claim,
                "status": status,
                "quality_flags": flags,
            }
        )

    response_conflicts = Counter()
    for parent_id, target_id, _, target_exists, target_parent, author, inbound in claim_rows:
        if target_exists and target_parent == parent_id:
            continue
        if not target_exists:
            status = "response_target_missing"
            response_conflicts[status] += 1
        elif not target_parent:
            status = "response_only_unconfirmed"
            response_conflicts[status] += 1
        else:
            status = "conflicting_parent_claim"
            response_conflicts[status] += 1
        nodes[parent_id]["quality_flags"].add(status)
        if inbound == 0 and author != support_author_id:
            cross_brand_threads.add(thread_for[parent_id])
        relationship_rows.append(
            {
                "thread_id": thread_for[parent_id],
                "parent_tweet_id": parent_id,
                "child_tweet_id": target_id,
                "direct_parent_claim": False,
                "response_claim": True,
                "status": status,
                "quality_flags": ["conflicting_link"],
            }
        )

    children: dict[str, list[str]] = defaultdict(list)
    for tweet_id, node in nodes.items():
        if node["parent_id"] in nodes:
            children[node["parent_id"]].append(tweet_id)

    conversation_rows: list[dict[str, Any]] = []
    component_flags: dict[str, set[str]] = {}
    for group in groups:
        thread_id = thread_for[group[0]]
        flags: set[str] = set()
        if any(tweet_id in cycle_nodes for tweet_id in group):
            flags.add("cyclic_relationships")
        if any(nodes[tweet_id]["duplicate_conflict"] for tweet_id in group):
            flags.add("conflicting_duplicates")
        if any("missing_parent" in nodes[tweet_id]["quality_flags"] for tweet_id in group):
            flags.add("missing_links")
        other_brands = sorted(
            {
                str(nodes[tweet_id]["author_id"])
                for tweet_id in group
                if nodes[tweet_id]["inbound"] == 0
                and nodes[tweet_id]["author_id"] != support_author_id
            }
        )
        if other_brands or thread_id in cross_brand_threads:
            flags.add("cross_brand_ambiguous")
            cross_brand_threads.add(thread_id)
        component_flags[thread_id] = flags
        valid_times = sorted(
            node["created_at_utc"]
            for tweet_id in group
            if (node := nodes[tweet_id])["created_at_utc"]
        )
        conversation_rows.append(
            {
                "thread_id": thread_id,
                "tweet_ids": group,
                "tweet_count": len(group),
                "inbound_tweet_count": sum(nodes[x]["inbound"] == 1 for x in group),
                "outbound_tweet_count": sum(nodes[x]["inbound"] == 0 for x in group),
                "spotify_tweet_count": sum(
                    nodes[x]["author_id"] == support_author_id for x in group
                ),
                "other_outbound_authors": other_brands,
                "started_at_utc": valid_times[0] if valid_times else None,
                "ended_at_utc": valid_times[-1] if valid_times else None,
                "quality_flags": sorted(flags),
            }
        )

    claimed_spotify_parents = {
        parent
        for parent, _, _, exists, _, author, _ in claim_rows
        if exists and author == support_author_id
    }
    direct_spotify: dict[str, list[str]] = defaultdict(list)
    for parent_id, child_ids in children.items():
        reply_ids = [
            child_id
            for child_id in child_ids
            if nodes[child_id]["author_id"] == support_author_id
            and nodes[child_id]["inbound"] == 0
        ]
        if reply_ids:
            direct_spotify[parent_id] = reply_ids
    candidate_ids = set(direct_spotify) | claimed_spotify_parents
    example_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []

    for customer_id in sorted(candidate_ids):
        customer = nodes.get(customer_id)
        if not customer or customer["inbound"] != 1:
            continue
        thread_id = thread_for[customer_id]
        replies = direct_spotify.get(customer_id, [])
        reasons: list[str] = []
        if not replies:
            reasons.append("no_verified_direct_spotify_reply")
        if "cross_brand_ambiguous" in component_flags[thread_id]:
            reasons.append("cross_brand_ambiguous")
        if "conflicting_duplicates" in component_flags[thread_id]:
            reasons.append("conflicting_duplicates")
        if "cyclic_relationships" in component_flags[thread_id]:
            reasons.append("cyclic_relationships")
        if customer["text_missing"]:
            reasons.append("missing_customer_text")
        if any(nodes[reply]["text_missing"] for reply in replies):
            reasons.append("missing_spotify_reply_text")
        if reasons:
            exclusion_rows.append(
                {
                    "thread_id": thread_id,
                    "customer_tweet_id": customer_id,
                    "direct_spotify_reply_ids": sorted(replies),
                    "reason_codes": sorted(set(reasons)),
                }
            )
            continue

        lineage: list[str] = []
        seen = {customer_id}
        parent_id = customer["parent_id"]
        while parent_id in nodes and parent_id not in seen:
            seen.add(parent_id)
            lineage.append(parent_id)
            parent_id = nodes[parent_id]["parent_id"]
        causal_order = list(reversed(lineage))
        context_ids = sorted(causal_order, key=lambda item: _timestamp_key(nodes[item]))
        reply_ids = sorted(replies, key=lambda item: _timestamp_key(nodes[item]))
        flags = set(customer["quality_flags"])
        for related_id in context_ids + reply_ids:
            flags.update(nodes[related_id]["quality_flags"])
        if context_ids != causal_order:
            flags.add("context_timestamp_order_differs_from_reply_chain")
        if customer["parent_raw"] and customer["parent_id"] not in nodes:
            flags.add("missing_ancestor")
        if customer["created_at_utc"]:
            for reply_id in reply_ids:
                reply_time = nodes[reply_id]["created_at_utc"]
                if reply_time and reply_time < customer["created_at_utc"]:
                    flags.add("reply_timestamp_not_after_customer")
        example_rows.append(
            {
                "example_id": _stable_id("example", [customer_id]),
                "thread_id": thread_id,
                "customer_tweet_id": customer_id,
                "customer_text": customer["text"],
                "customer_created_at_utc": customer["created_at_utc"],
                "context_tweet_ids": context_ids,
                "context_author_ids": [nodes[x]["author_id"] for x in context_ids],
                "context_inbound": [bool(nodes[x]["inbound"]) for x in context_ids],
                "context_created_at_utc": [nodes[x]["created_at_utc"] for x in context_ids],
                "context_texts": [nodes[x]["text"] for x in context_ids],
                "reference_reply_ids": reply_ids,
                "reference_reply_created_at_utc": [
                    nodes[x]["created_at_utc"] for x in reply_ids
                ],
                "reference_reply_texts": [nodes[x]["text"] for x in reply_ids],
                "quality_flags": sorted(flags),
                "source_dataset": source_name,
                "source_sha256": source_sha256,
                "customer_source_record": int(customer["source_record"]),
            }
        )

    tweet_rows: list[dict[str, Any]] = []
    for tweet_id, node in nodes.items():
        tweet_rows.append(
            {
                "tweet_id": tweet_id,
                "thread_id": thread_for[tweet_id],
                "source_record": int(node["source_record"]),
                "author_id": node["author_id"],
                "inbound": None if pd.isna(node["inbound"]) else bool(node["inbound"]),
                "created_at_raw": node["created_at_raw"],
                "created_at_utc": node["created_at_utc"],
                "text": node["text"],
                "response_tweet_ids": node["response_tweet_ids"],
                "in_response_to_tweet_id": node["parent_id"],
                "duplicate_count": int(node["duplicate_count"]),
                "quality_flags": sorted(node["quality_flags"]),
            }
        )

    duplicate_frame = pd.read_sql_query(
        """SELECT r.source_record, r.tweet_id, r.author_id, r.inbound_raw,
                  r.created_at_raw, r.response_ids_json, r.parent_raw,
                  r.flags_json, s.record_count, s.variant_count
           FROM records r JOIN tweet_stats s USING(tweet_id)
           WHERE s.record_count > 1 ORDER BY r.tweet_id, r.source_record""",
        connection,
    )
    duplicate_frame = duplicate_frame.rename(
        columns={
            "response_ids_json": "response_tweet_ids_json",
            "parent_raw": "in_response_to_tweet_id_raw",
            "flags_json": "quality_flags_json",
        }
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_parquet(
        tweet_rows,
        [
            "tweet_id", "thread_id", "source_record", "author_id", "inbound",
            "created_at_raw", "created_at_utc", "text", "response_tweet_ids",
            "in_response_to_tweet_id", "duplicate_count", "quality_flags",
        ],
        output_dir / OUTPUT_FILENAMES["tweets"],
    )
    _write_parquet(
        example_rows,
        [
            "example_id", "thread_id", "customer_tweet_id", "customer_text",
            "customer_created_at_utc", "context_tweet_ids", "context_author_ids",
            "context_inbound", "context_created_at_utc", "context_texts",
            "reference_reply_ids", "reference_reply_created_at_utc",
            "reference_reply_texts", "quality_flags", "source_dataset",
            "source_sha256", "customer_source_record",
        ],
        output_dir / OUTPUT_FILENAMES["examples"],
    )
    _write_parquet(
        conversation_rows,
        [
            "thread_id", "tweet_ids", "tweet_count", "inbound_tweet_count",
            "outbound_tweet_count", "spotify_tweet_count", "other_outbound_authors",
            "started_at_utc", "ended_at_utc", "quality_flags",
        ],
        output_dir / OUTPUT_FILENAMES["conversations"],
    )
    _write_parquet(
        relationship_rows,
        [
            "thread_id", "parent_tweet_id", "child_tweet_id",
            "direct_parent_claim", "response_claim", "status", "quality_flags",
        ],
        output_dir / OUTPUT_FILENAMES["relationships"],
    )
    _write_parquet(
        exclusion_rows,
        [
            "thread_id", "customer_tweet_id", "direct_spotify_reply_ids",
            "reason_codes",
        ],
        output_dir / OUTPUT_FILENAMES["exclusions"],
    )
    duplicate_frame.to_parquet(output_dir / OUTPUT_FILENAMES["duplicates"], index=False)

    sizes = np.asarray([len(group) for group in groups], dtype=float)
    exclusion_counts = Counter(
        reason for row in exclusion_rows for reason in row["reason_codes"]
    )
    representative = sorted(
        example_rows, key=lambda row: hashlib.sha256(row["example_id"].encode()).hexdigest()
    )[:audit_example_count]
    audit: dict[str, Any] = {
        "source": {
            "dataset": source_name,
            "sha256": source_sha256,
            "required_columns": list(REQUIRED_COLUMNS),
            "support_author_id": support_author_id,
            "support_author_variants": {
                author: int(count)
                for author, count in connection.execute(
                    """SELECT author_id, COUNT(*) FROM tweets
                       WHERE lower(author_id) = lower(?)
                       GROUP BY author_id ORDER BY author_id""",
                    (support_author_id,),
                )
            },
            "inbound_values": [
                value
                for (value,) in connection.execute(
                    "SELECT DISTINCT inbound_raw FROM records ORDER BY inbound_raw"
                )
            ],
        },
        "counts": {
            **{key: int(value) for key, value in ingest_counts.items()},
            "unique_tweet_ids": int(
                connection.execute("SELECT COUNT(*) FROM tweets").fetchone()[0]
            ),
            "spotify_tweets": sum(
                node["author_id"] == support_author_id for node in nodes.values()
            ),
            "relevant_tweets": len(nodes),
            "relevant_customer_tweets": sum(
                node["inbound"] == 1 for node in nodes.values()
            ),
            "conversation_groups": len(groups),
            "eligible_customer_examples": len(example_rows),
            "eligible_spotify_replies": sum(
                len(row["reference_reply_ids"]) for row in example_rows
            ),
            "exclusion_records": len(exclusion_rows),
        },
        "data_quality": {
            "relevant_missing_parent_links": sum(
                "missing_parent" in node["quality_flags"] for node in nodes.values()
            ),
            "relevant_invalid_timestamps": sum(
                "invalid_timestamp" in node["quality_flags"] for node in nodes.values()
            ),
            "relevant_missing_timestamps": sum(
                "missing_timestamp" in node["quality_flags"] for node in nodes.values()
            ),
            "relevant_missing_text": sum(
                "missing_text" in node["quality_flags"] for node in nodes.values()
            ),
            "relevant_conflicting_duplicate_ids": sum(
                bool(node["duplicate_conflict"]) for node in nodes.values()
            ),
            "cycle_groups": sum(
                "cyclic_relationships" in row["quality_flags"]
                for row in conversation_rows
            ),
            "cycle_tweets": len(cycle_nodes),
            "direct_parent_response_disagreements": sum(
                row["status"] == "parent_response_disagrees"
                for row in relationship_rows
            ),
            "missing_links_total": sum(
                "missing_parent" in node["quality_flags"] for node in nodes.values()
            )
            + response_conflicts["response_target_missing"],
            "conflicting_links_total": sum(
                row["status"] == "parent_response_disagrees"
                for row in relationship_rows
            )
            + response_conflicts["conflicting_parent_claim"],
            "response_claim_issues": dict(sorted(response_conflicts.items())),
            "exclusions_by_reason": dict(sorted(exclusion_counts.items())),
        },
        "conversation_size": {
            "minimum": int(sizes.min()) if len(sizes) else 0,
            "median": float(np.median(sizes)) if len(sizes) else 0.0,
            "mean": float(sizes.mean()) if len(sizes) else 0.0,
            "p90": float(np.percentile(sizes, 90)) if len(sizes) else 0.0,
            "maximum": int(sizes.max()) if len(sizes) else 0,
        },
        "representative_examples": [
            {
                "example_id": row["example_id"],
                "thread_id": row["thread_id"],
                "customer_tweet_id": row["customer_tweet_id"],
                "customer_text_redacted": _redact(row["customer_text"]),
                "context_tweet_ids": row["context_tweet_ids"],
                "context_texts_redacted": [_redact(text) for text in row["context_texts"]],
                "reference_reply_ids": row["reference_reply_ids"],
                "reference_reply_texts_redacted": [
                    _redact(text) for text in row["reference_reply_texts"]
                ],
            }
            for row in representative
        ],
        "limitations": [
            "Threads are complete only to the extent that direct parent records exist in the source.",
            "A SpotifyCares reply is a reference response, not proof that the issue was resolved.",
            "Audit excerpt redaction is best-effort and the audit remains local and Git-ignored.",
        ],
    }
    with (output_dir / OUTPUT_FILENAMES["audit"]).open("w", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return audit


def extract_spotify_conversations(
    csv_path: Path,
    output_dir: Path,
    temp_database: Path,
    *,
    support_author_id: str = "SpotifyCares",
    source_name: str = "thoughtvector/customer-support-on-twitter",
    chunk_size: int = 50_000,
    audit_example_count: int = 5,
) -> ExtractionResult:
    """Extract SpotifyCares-connected threads and verified direct support examples."""

    csv_path = csv_path.resolve()
    output_dir = output_dir.resolve()
    temp_database = temp_database.resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Dataset not found at {csv_path}. Put the Kaggle twcs.csv file there."
        )
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    _validate_header(csv_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_database.parent.mkdir(parents=True, exist_ok=True)
    if temp_database.exists():
        temp_database.unlink()

    source_sha256 = _hash_file(csv_path)
    connection = _connect(temp_database)
    try:
        ingest_counts = _ingest_metadata(csv_path, connection, chunk_size)
        _index_responses(connection)
        relevant_ids = _find_relevant_ids(connection, support_author_id)
        _hydrate_relevant_text(csv_path, connection, relevant_ids, chunk_size)
        audit = _reconstruct(
            connection,
            support_author_id,
            source_name,
            source_sha256,
            output_dir,
            ingest_counts,
            audit_example_count,
        )
    finally:
        connection.close()
    temp_database.unlink(missing_ok=True)
    return ExtractionResult(
        output_paths={key: output_dir / name for key, name in OUTPUT_FILENAMES.items()},
        audit=audit,
    )
