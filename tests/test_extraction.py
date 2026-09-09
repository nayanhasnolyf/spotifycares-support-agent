"""Synthetic software fixtures for Stage 2 reconstruction behavior."""

from pathlib import Path

import pandas as pd
import pytest

from spotify_cares.extraction import ExtractionError, extract_spotify_conversations


COLUMNS = [
    "tweet_id",
    "author_id",
    "inbound",
    "created_at",
    "text",
    "response_tweet_id",
    "in_response_to_tweet_id",
]


def _row(
    tweet_id: str,
    author: str,
    inbound: str,
    minute: int,
    text: str,
    responses: str = "",
    parent: str = "",
) -> dict[str, str]:
    return {
        "tweet_id": tweet_id,
        "author_id": author,
        "inbound": inbound,
        "created_at": f"Tue Oct 31 22:{minute:02d}:00 +0000 2017",
        "text": text,
        "response_tweet_id": responses,
        "in_response_to_tweet_id": parent,
    }


@pytest.fixture(scope="module")
def extracted(tmp_path_factory):
    """One deliberately synthetic graph exercises all reconstruction edge cases."""

    root = tmp_path_factory.mktemp("synthetic_extraction")
    csv_path = root / "synthetic_twcs.csv"
    rows = [
        _row("1", "customer_a", "True", 0, "simple question", "2"),
        _row("2", "SpotifyCares", "False", 1, "simple answer", parent="1"),
        _row("10", "customer_b", "True", 2, "first turn", "11"),
        _row("11", "SpotifyCares", "False", 3, "first reply", "12", "10"),
        _row("12", "customer_b", "True", 4, "follow up", "13", "11"),
        _row("13", "SpotifyCares", "False", 5, "follow-up answer", parent="12"),
        _row("20", "customer_c", "True", 6, "branch root", "21,22"),
        _row("21", "SpotifyCares", "False", 7, "branch one reply", "23", "20"),
        _row("22", "SpotifyCares", "False", 8, "branch two reply", "24", "20"),
        _row("23", "customer_c", "True", 9, "branch one follow-up", "25", "21"),
        _row("24", "customer_c", "True", 10, "branch two follow-up", "26", "22"),
        _row("25", "SpotifyCares", "False", 11, "branch one answer", parent="23"),
        _row("26", "SpotifyCares", "False", 12, "branch two answer", parent="24"),
        _row("30", "customer_d", "True", 13, "missing ancestor", "31", "999"),
        _row("31", "SpotifyCares", "False", 14, "available answer", parent="30"),
        _row("40", "customer_e", "True", 15, "contradictory links", "41"),
        _row("41", "SpotifyCares", "False", 16, "claimed answer", parent="999"),
        _row("42", "SpotifyCares", "False", 17, "actual direct answer", parent="40"),
        _row("43", "customer_e", "True", 18, "response-only claim", "41", "42"),
        _row("50", "customer_f", "True", 18, "exact duplicate", "51"),
        _row("50", "customer_f", "True", 18, "exact duplicate", "51"),
        _row("51", "SpotifyCares", "False", 19, "duplicate-safe answer", parent="50"),
        _row("52", "customer_g", "True", 20, "conflict version one", "53"),
        _row("52", "customer_g", "True", 20, "conflict version two", "54"),
        _row("53", "SpotifyCares", "False", 21, "answer one", parent="52"),
        _row("54", "SpotifyCares", "False", 22, "answer two", parent="52"),
        _row("60", "customer_h", "True", 23, "two brands", "61,62"),
        _row("61", "SpotifyCares", "False", 24, "spotify answer", parent="60"),
        _row("62", "OtherCare", "False", 25, "other brand answer", parent="60"),
        _row("70", "customer_i", "True", 26, "cycle customer", "72", "71"),
        _row("71", "customer_i", "True", 27, "cycle parent", "70", "70"),
        _row("72", "SpotifyCares", "False", 28, "cycle answer", parent="70"),
        {
            **_row("80", "customer_j", "True", 29, "invalid time", "81"),
            "created_at": "not-a-timestamp",
        },
        _row("81", "SpotifyCares", "False", 30, "time answer", parent="80"),
        _row("90", "customer_k", "True", 31, "", "91"),
        _row("91", "SpotifyCares", "False", 32, "missing-input answer", parent="90"),
    ]
    pd.DataFrame(rows, columns=COLUMNS).to_csv(csv_path, index=False)
    output = root / "processed"
    result = extract_spotify_conversations(
        csv_path,
        output,
        root / "interim" / "index.sqlite3",
        chunk_size=1,
        audit_example_count=2,
        source_name="synthetic-test-fixture",
    )
    return result, {
        name: pd.read_parquet(path)
        for name, path in result.output_paths.items()
        if path.suffix == ".parquet"
    }, len(rows)


def test_simple_exchange_and_cross_chunk_relationship(extracted):
    _, tables, _ = extracted
    example = tables["examples"].set_index("customer_tweet_id").loc["1"]
    assert list(example["reference_reply_ids"]) == ["2"]
    relationship = tables["relationships"].query(
        "parent_tweet_id == '1' and child_tweet_id == '2'"
    ).iloc[0]
    assert relationship["status"] == "consistent"


def test_multiturn_context_excludes_future_reply(extracted):
    _, tables, _ = extracted
    example = tables["examples"].set_index("customer_tweet_id").loc["12"]
    assert list(example["context_tweet_ids"]) == ["10", "11"]
    assert "13" not in example["context_tweet_ids"]
    assert "follow-up answer" not in example["context_texts"]
    assert list(example["reference_reply_ids"]) == ["13"]


def test_branch_context_has_no_sibling_contamination(extracted):
    _, tables, _ = extracted
    example = tables["examples"].set_index("customer_tweet_id").loc["23"]
    assert list(example["context_tweet_ids"]) == ["20", "21"]
    assert not {"22", "24", "26"}.intersection(example["context_tweet_ids"])


def test_multiple_direct_brand_replies_share_one_example(extracted):
    _, tables, _ = extracted
    matches = tables["examples"].query("customer_tweet_id == '20'")
    assert len(matches) == 1
    assert list(matches.iloc[0]["reference_reply_ids"]) == ["21", "22"]


def test_missing_ancestor_is_preserved_and_flagged(extracted):
    _, tables, _ = extracted
    example = tables["examples"].set_index("customer_tweet_id").loc["30"]
    assert list(example["context_tweet_ids"]) == []
    assert "missing_ancestor" in example["quality_flags"]


def test_broken_and_contradictory_links_are_audited(extracted):
    _, tables, _ = extracted
    statuses = set(tables["relationships"]["status"])
    assert "missing_parent_target" in statuses
    assert "conflicting_parent_claim" in statuses
    assert "parent_response_disagrees" in statuses
    response_only = tables["exclusions"].set_index("customer_tweet_id").loc["43"]
    assert "no_verified_direct_spotify_reply" in response_only["reason_codes"]


def test_duplicate_ids_are_retained_and_conflicts_excluded(extracted):
    _, tables, _ = extracted
    duplicates = tables["duplicates"]
    assert len(duplicates.query("tweet_id == '50'")) == 2
    assert len(duplicates.query("tweet_id == '52'")) == 2
    assert "50" in set(tables["examples"]["customer_tweet_id"])
    excluded = tables["exclusions"].set_index("customer_tweet_id").loc["52"]
    assert "conflicting_duplicates" in excluded["reason_codes"]


def test_cross_brand_component_is_excluded(extracted):
    _, tables, _ = extracted
    excluded = tables["exclusions"].set_index("customer_tweet_id").loc["60"]
    assert "cross_brand_ambiguous" in excluded["reason_codes"]
    assert "60" not in set(tables["examples"]["customer_tweet_id"])


def test_cycle_is_flagged_and_excluded(extracted):
    result, tables, _ = extracted
    excluded = tables["exclusions"].set_index("customer_tweet_id").loc["70"]
    assert "cyclic_relationships" in excluded["reason_codes"]
    assert result.audit["data_quality"]["cycle_groups"] == 1


def test_reference_targets_never_enter_model_input_fields(extracted):
    _, tables, _ = extracted
    for example in tables["examples"].to_dict(orient="records"):
        input_ids = {example["customer_tweet_id"], *example["context_tweet_ids"]}
        assert input_ids.isdisjoint(example["reference_reply_ids"])
        assert set(example["reference_reply_texts"]).isdisjoint(example["context_texts"])


def test_audit_uses_measured_fixture_counts(extracted):
    result, _, row_count = extracted
    assert result.audit["counts"]["total_rows_scanned"] == row_count
    assert result.audit["source"]["dataset"] == "synthetic-test-fixture"
    assert result.audit["source"]["inbound_values"] == ["False", "True"]


def test_invalid_timestamp_is_retained_and_missing_text_is_excluded(extracted):
    result, tables, _ = extracted
    invalid_time = tables["examples"].set_index("customer_tweet_id").loc["80"]
    assert invalid_time["customer_created_at_utc"] is None
    assert "invalid_timestamp" in invalid_time["quality_flags"]
    missing_text = tables["exclusions"].set_index("customer_tweet_id").loc["90"]
    assert "missing_customer_text" in missing_text["reason_codes"]
    assert result.audit["data_quality"]["relevant_invalid_timestamps"] == 1


def test_required_schema_is_validated(tmp_path: Path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"tweet_id": ["1"]}).to_csv(path, index=False)
    with pytest.raises(ExtractionError, match="missing required columns"):
        extract_spotify_conversations(path, tmp_path / "out", tmp_path / "index.sqlite3")
