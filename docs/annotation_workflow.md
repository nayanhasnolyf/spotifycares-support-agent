# Annotation workflow and queue construction

Stage 4 reads the Stage 3 manifest, verifies every declared output SHA-256, reruns the nine leakage checks, and then samples without changing split membership. Queue files contain identifiers and sampling provenance; the interface joins redacted inputs and separately stored replies only when displaying one item.

## Deterministic queues

The project seed is 42. Selection order is a SHA-256 rank of the seed, a fixed namespace, and the stable example ID. Every queue keeps at most one example per conversation and combined duplicate group.

- Training (300): deterministic coverage enrichment over observable keyword proxies derived after reviewing the training-only discovery sample, followed by a deterministic remainder. The proxies cover security, billing, membership, accounts, catalog, library/playlists, playback, app/device, feature/market, short/context-limited, and general cases. They are sampling tags, not labels. This intentionally enriched batch must not be reported as natural intent prevalence. Later batches must remain training-only.
- Development (80): deterministic hash-ranked sample from the development pool, reserved for later tuning and development checks.
- Golden (200): 150 deterministic random eligible test candidates, then 50 additional challenge cases from remaining groups. The challenge selector round-robins over five predeclared observable flags: at most 40 characters, no preceding context, at least two question marks, security wording, and account-specific payment-dispute wording. These are sampling flags, not human labels.

No selected development or test message was displayed or manually inspected while defining the taxonomy or rules. Human golden annotation can record ambiguity after the guide is frozen, but it must not drive system design.

The generated training queue has 27 records in each of the 11 named coverage buckets plus 3 deterministic remainder records. The golden challenge set has 10 records assigned to each of its five flags. These are measured queue-construction counts, not class prevalence or labelled outcomes.

## Local files

`spotify-cares prepare-annotations` writes beneath `data/labels/annotation/`:

- `queues/{training,development,golden}.parquet`: IDs, conversation/group IDs, position, seed, stratum, rule, and candidate-pool hash.
- `labels/{training,development,golden}.csv`: human entries, created on first save.
- `audit/*.jsonl`: append-only edit, reveal, and freeze events.
- `state/guide_state.json`: proposed/frozen checkpoint plus taxonomy and guide hashes.
- `taxonomy_examples.parquet`: real redacted training examples for local guide review.
- `annotation_manifest.json`: aggregate queue sizes, hashes, and readiness states.

All of these files are Git-ignored because they contain source-derived IDs/text, annotations, or local review state. CSV rewrites use an adjacent temporary file and atomic replacement so prior saved rows are retained. An audit event records every save, edit, skip, reveal, and final guidance save.

Run:

```powershell
uv run spotify-cares prepare-annotations
uv run spotify-cares validate-annotations
uv run --extra annotation streamlit run app/annotation_app.py
```

The checked-in Streamlit configuration binds to `127.0.0.1` and disables usage telemetry. It does not deploy the application.
