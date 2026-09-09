# Stage 3 preprocessing and split contract

## Commands

```bash
uv run spotify-cares preprocess
uv run spotify-cares validate-splits
```

The first command consumes Stage 2's local Parquet outputs and writes ignored files under `data/processed/splits/`. The second command independently reloads those files and fails if a leakage or chronology invariant is violated.

## Text representations and redaction

Preprocessing version `spotify-preprocess-v1` applies Unicode NFC normalization, repairs a small explicit set of common encoding artifacts, removes zero-width markers, and collapses whitespace. It does not remove stop words, stem words, or strip punctuation. Negation, error codes, product/device names, emojis, and meaningful punctuation remain intact.

Normalized text is retained separately from redacted text in local ignored files. Duplicate detection uses normalized, unredacted customer messages only; downstream model-facing work should use fields ending in `_redacted`. This prevents two different handles from creating an exact match merely because both become `[CUSTOMER]`.

Redaction replaces detected customer handles with `[CUSTOMER]`, Spotify handles with `[BRAND]`, and detectable emails, phones, IP addresses, and long numbers with typed placeholders. URLs lose paths, queries, fragments, and user information. Approved Spotify domains may remain as `[URL:domain]`; other URLs become `[URL]`. The same procedure covers customer messages, ancestor context, and historical replies.

This is deterministic risk reduction, not anonymization. Names and unusual identifiers can survive automated patterns, so every derived text file remains local and Git-ignored.

## Eligibility

The preprocessor revalidates each customer and direct SpotifyCares reply against `relevant_tweets.parquet`. Missing customer text, invalid customer/brand links, cross-brand ambiguity, future-answer leakage, and unresolved relationship conflicts are excluded or quarantined with reason codes. Difficult, sarcastic, short, multi-issue, and missing-ancestor messages are not removed merely for being difficult.

All 41,339 Stage 2 examples passed structural eligibility in the measured run. Missing source ancestors remain explicit flags.

## Duplicate grouping

Exact duplicates share a case-folded, whitespace-normalized form of the unredacted customer message. Near-copy detection skips messages shorter than 20 characters, creates candidates only when texts share one of four selected rare character four-grams, ignores blocks above 100 texts, and accepts a pair at a deterministic `SequenceMatcher` ratio of at least 0.92 with the same minimum length ratio.

This is conservative lexical similarity, not semantic similarity. It evaluated 252,967 candidates instead of all 854 million possible pairs. Conversation membership, exact groups, and accepted near-copy links are joined by transitive closure into one indivisible combined group.

Short messages still participate in exact grouping but not near matching. Personal details are not redacted before matching. These choices reduce generic placeholder matches, but rare-shingle blocking can miss rephrasings. Conversely, transitive closure can create a broad group even when every individual edge passes the threshold. The largest measured group has 624 examples across 129 threads; it is kept intact rather than silently broken.

## Strict chronological split

Target fractions are 70% training, 15% development, and 15% test candidates. Cutoffs are calculated from the timestamps of all included content: ancestor context, the customer message, and reference replies.

A combined group is assigned only when its entire time interval fits before or after a cutoff. Groups crossing either cutoff are quarantined. Groups containing any unusable timestamp are also quarantined. Consequently, actual pool percentages may differ from targets.

The measured cutoffs are:

- training/development: `2017-11-15T23:22:34Z`
- development/test: `2017-11-25T22:27:56Z`

Strict chronology was achieved. In particular, the latest training reference precedes the earliest development content, and the latest development reference precedes the earliest test-candidate content.

## Output contract

- `{train,development,test_candidate}_inputs.parquet`: input-only IDs, context, normalized/redacted text, flags, and time bounds.
- `{train,development,test_candidate}_references.parquet`: separately linked historical reply IDs/text/timestamps.
- `training_retrieval_corpus.parquet`: training inputs paired with training-only historical replies.
- `taxonomy_discovery_sample.parquet`: deterministic 400-message training-only sample without reply text.
- `quarantined_examples.parquet`: redacted examples and reasons.
- `split_assignments.parquet`: every Stage 2 example's assignment.
- `duplicate_groups.parquet`: exact and combined group mapping.
- `near_duplicate_pairs.parquet`: accepted pair scores and local redacted review text.
- `preprocessing_manifest.json`: inputs/outputs hashes, configuration, cutoffs, counts, redaction totals, duplicate statistics, and leakage results.

Historical replies are references only. They are not proof of issue resolution and not guaranteed to represent current Spotify policy.
