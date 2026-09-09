"""Synthetic tests for privacy preprocessing and leakage-safe splitting."""

from pathlib import Path
import shutil

import pandas as pd
import pytest

from spotify_cares.preprocessing import (
    LeakageError,
    OUTPUT_FILES,
    normalize_text,
    preprocess_and_split,
    redact_text,
    validate_split_outputs,
)


def _timestamp(day: int, minute: int = 0) -> str:
    return f"2017-10-{day:02d}T00:{minute:02d}:00Z"


@pytest.fixture(scope="module")
def split_fixture(tmp_path_factory):
    """Create Stage 2-shaped synthetic tables; no real customer text is used."""

    root = tmp_path_factory.mktemp("synthetic_preprocessing")
    messages = [
        ("a", 1, "Playback stops with error 17"),
        ("b", 9, "Playback stops with error 17"),
        ("c", 2, "Spotify app crashes whenever I open settings"),
        ("d", 3, "Spotify app crashes whenever I open the settings"),
        ("e", 4, "I can't play songs on Android error 42"),
        ("f", 5, "Playlist order changed unexpectedly"),
        ("g", 6, "Family plan invitation is not working"),
        ("h", 7, "Downloaded music disappeared"),
        ("i", 8, "Desktop app volume is too quiet"),
        ("j", 10, "Podcast episode will not resume"),
        ("k", 11, "Student verification failed"),
        ("l", 12, "Bluetooth playback skips tracks"),
        ("m", 13, "Timestamp is unavailable"),
    ]
    example_rows = []
    tweet_rows = []
    conversation_rows = []
    for key, day, text in messages:
        customer_id, reply_id, thread_id = f"c_{key}", f"r_{key}", f"thread_{key}"
        customer_time = None if key == "m" else _timestamp(day)
        reply_time = None if key == "m" else _timestamp(day, 1)
        example_rows.append(
            {
                "example_id": f"example_{key}",
                "thread_id": thread_id,
                "customer_tweet_id": customer_id,
                "customer_text": text,
                "customer_created_at_utc": customer_time,
                "context_tweet_ids": [],
                "context_author_ids": [],
                "context_inbound": [],
                "context_created_at_utc": [],
                "context_texts": [],
                "reference_reply_ids": [reply_id],
                "reference_reply_created_at_utc": [reply_time],
                "reference_reply_texts": [f"Synthetic reply for {key}"],
                "quality_flags": ["missing_ancestor", "missing_parent"] if key == "l" else [],
                "source_dataset": "synthetic-test-fixture",
                "source_sha256": "0" * 64,
                "customer_source_record": day,
            }
        )
        tweet_rows.extend(
            [
                {
                    "tweet_id": customer_id,
                    "author_id": f"customer_{key}",
                    "inbound": True,
                    "in_response_to_tweet_id": "missing_parent" if key == "l" else None,
                },
                {
                    "tweet_id": reply_id,
                    "author_id": "SpotifyCares",
                    "inbound": False,
                    "in_response_to_tweet_id": customer_id,
                },
            ]
        )
        conversation_rows.append({"thread_id": thread_id, "quality_flags": []})
    paths = {
        "examples": root / "support_examples.parquet",
        "tweets": root / "relevant_tweets.parquet",
        "conversations": root / "conversations.parquet",
    }
    pd.DataFrame(example_rows).to_parquet(paths["examples"], index=False)
    pd.DataFrame(tweet_rows).to_parquet(paths["tweets"], index=False)
    pd.DataFrame(conversation_rows).to_parquet(paths["conversations"], index=False)
    outputs = []
    for name in ("out_one", "out_two"):
        output = root / name
        preprocess_and_split(
            paths["examples"],
            paths["tweets"],
            paths["conversations"],
            output,
            train_fraction=0.5,
            development_fraction=0.25,
            test_fraction=0.25,
            near_duplicate_threshold=0.90,
            discovery_sample_size=4,
        )
        outputs.append(output)
    return root, paths, outputs


def test_normalization_preserves_negation_codes_products_and_punctuation():
    value = normalize_text("  I can't use Spotify on iPhone 15 — Error 42! 😭  ")
    assert value == "I can't use Spotify on iPhone 15 — Error 42! 😭"


def test_redaction_is_consistent_and_role_aware():
    source = (
        "@SpotifyCares ask @person at name@example.com or +1 (212) 555-0199; "
        "IP 192.168.1.2, account 12345678. "
        "https://support.spotify.com/article?id=person and https://example.com/u/person"
    )
    redacted, counts = redact_text(source)
    assert "[BRAND]" in redacted and "[CUSTOMER]" in redacted
    assert "[EMAIL]" in redacted and "[PHONE]" in redacted and "[IP]" in redacted
    assert "[NUMBER]" in redacted
    assert "[URL:support.spotify.com]" in redacted
    assert "[URL]" in redacted
    assert sum(counts.values()) >= 8


def test_exact_and_near_duplicates_form_indivisible_groups(split_fixture):
    _, _, outputs = split_fixture
    assignments = pd.read_parquet(outputs[0] / OUTPUT_FILES["assignments"]).set_index(
        "example_id"
    )
    mapping = pd.read_parquet(outputs[0] / OUTPUT_FILES["duplicates"]).set_index(
        "example_id"
    )
    assert mapping.loc["example_a", "combined_group_id"] == mapping.loc[
        "example_b", "combined_group_id"
    ]
    assert assignments.loc["example_a", "split"] == assignments.loc[
        "example_b", "split"
    ] == "quarantine"
    assert mapping.loc["example_c", "combined_group_id"] == mapping.loc[
        "example_d", "combined_group_id"
    ]
    assert assignments.loc["example_c", "split"] == assignments.loc[
        "example_d", "split"
    ]
    manifest = pd.read_json(outputs[0] / OUTPUT_FILES["manifest"], typ="series")
    assert manifest["duplicate_statistics"]["near_duplicate_groups"] >= 1


def test_boundary_and_missing_timestamp_groups_are_quarantined(split_fixture):
    _, _, outputs = split_fixture
    assignments = pd.read_parquet(outputs[0] / OUTPUT_FILES["assignments"]).set_index(
        "example_id"
    )
    assert "combined_group_spans_chronological_cutoff" in assignments.loc[
        "example_a", "reason_codes"
    ]
    assert assignments.loc["example_m", "split"] == "quarantine"
    assert "combined_group_contains_unusable_timestamp" in assignments.loc[
        "example_m", "reason_codes"
    ]


def test_split_is_deterministic_and_metadata_ids_are_unchanged(split_fixture):
    _, _, outputs = split_fixture
    first = pd.read_parquet(outputs[0] / OUTPUT_FILES["assignments"]).sort_values(
        "example_id"
    )
    second = pd.read_parquet(outputs[1] / OUTPUT_FILES["assignments"]).sort_values(
        "example_id"
    )
    pd.testing.assert_frame_equal(first.reset_index(drop=True), second.reset_index(drop=True))
    exported = pd.concat(
        [pd.read_parquet(outputs[0] / OUTPUT_FILES[f"{split}_inputs"]) for split in ("train", "development", "test_candidate")]
    )
    assert set(exported["customer_tweet_id"]).issubset(
        {f"c_{letter}" for letter in "abcdefghijklm"}
    )


def test_deliberately_contaminated_split_fails_validation(split_fixture, tmp_path):
    _, paths, outputs = split_fixture
    contaminated = tmp_path / "contaminated"
    shutil.copytree(outputs[0], contaminated)
    train = pd.read_parquet(contaminated / OUTPUT_FILES["train_inputs"])
    development_path = contaminated / OUTPUT_FILES["development_inputs"]
    development = pd.read_parquet(development_path)
    assert not train.empty and not development.empty
    development.loc[development.index[0], "combined_group_id"] = train.iloc[0][
        "combined_group_id"
    ]
    development.to_parquet(development_path, index=False)
    with pytest.raises(LeakageError, match="combined_group_id overlaps"):
        validate_split_outputs(contaminated, paths["tweets"])
