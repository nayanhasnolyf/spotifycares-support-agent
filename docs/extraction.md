# Stage 2 extraction contract

## Source and command

The extractor expects the real Kaggle file at `data/raw/twcs.csv` and validates these columns before scanning: `tweet_id`, `author_id`, `inbound`, `created_at`, `text`, `response_tweet_id`, and `in_response_to_tweet_id`.

```bash
uv run spotify-cares extract
```

The measured source uses the exact author ID `SpotifyCares`; inbound values are exactly `True` and `False`. Both facts are checked during extraction and recorded in the local audit.

## Memory-conscious strategy

The first CSV pass reads configurable chunks and writes metadata—not tweet text—to a temporary SQLite database. SQLite detects duplicate IDs and indexes direct parent relationships even when the records appear in different CSV chunks. After finding every component connected to a SpotifyCares tweet through valid direct-parent edges, a second chunked pass hydrates text only for those relevant canonical records. The temporary database is removed after a successful run.

This design trades local disk space for bounded Python memory. The original CSV remains the source of truth.

## Relationship policy

`in_response_to_tweet_id` is the authoritative direct-parent claim when it names one available tweet. `response_tweet_id` can contain several comma-separated child IDs; these declarations are normalized, deduplicated, and used to cross-check the child records. A response-only claim never merges components or becomes a verified reference answer. Missing targets, omitted children, and contradictory parent claims are retained in `relationships.parquet` with explicit statuses.

Conversation IDs are deterministic hashes of the sorted IDs in an available direct-parent connected component. They are stable for the same source records. “Complete available conversation” means all records connected by valid parent links that exist in this dataset; it is not a promise that deleted or absent tweets were recovered.

## Branch-safe examples

An eligible example must be an inbound customer record with at least one outbound `SpotifyCares` record whose direct parent is that customer record. Its model-input side contains the customer message and only the ancestors on that message's own parent chain. Ancestors are ordered by valid timestamp, falling back to source-record order. Descendants, sibling branches, and future replies are never included.

All direct SpotifyCares children are stored together as explicit reference replies, so multiple replies do not create indistinguishable duplicate customer examples. Reference replies are separate columns and are not evidence that the issue was resolved.

## Data-quality handling

- IDs are strings. Empty identifiers remain missing rather than becoming strings such as `nan`.
- `True` and `False` are parsed explicitly. Other inbound values are retained and flagged invalid.
- Empty text is retained and flagged; a candidate with missing customer or reference-reply text is excluded.
- Valid timestamps are normalized to UTC. Missing and invalid timestamps stay null and receive different flags.
- A parent field containing multiple IDs is invalid because a tweet can have only one direct parent. Its raw value is retained in the local index and the relationship is not inferred.
- Every duplicate record remains represented in `duplicate_records.parquet`. The first source record is canonical. Identical duplicates may remain usable; any component containing conflicting variants is excluded.
- Missing parents stop the available ancestor chain but do not by themselves exclude an otherwise verified direct customer/reply pair.
- Cyclic direct-parent components are retained in conversation metadata but excluded from eligible examples.
- A component containing an outbound author other than SpotifyCares is cross-brand ambiguous and excluded by default. Contradictory response claims to another brand also trigger this exclusion.
- Link disagreements are flagged rather than repaired by joining components.

## Local outputs

All outputs are Parquet except the JSON audit, and all remain Git-ignored because they contain or derive from customer text:

| File | Purpose |
|---|---|
| `relevant_tweets.parquet` | Canonical source records and per-tweet flags |
| `support_examples.parquet` | Separate model-input context and future reference replies |
| `conversations.parquet` | Available component membership and summary flags |
| `relationships.parquet` | Direct-parent and response-claim cross-checks |
| `exclusions.parquet` | Candidate IDs and explicit exclusion reasons |
| `duplicate_records.parquet` | Metadata for every occurrence of duplicated IDs |
| `extraction_audit.json` | Aggregate counts and local best-effort-redacted examples |

The audit's example redaction handles user handles, URLs, emails, phone-like strings, and long numbers, but it is still treated as local because free text can contain other identifiers.
