# Annotation workflow and queue construction

Stage 4 reads the Stage 3 manifest, verifies every declared output SHA-256, reruns the nine leakage checks, and then samples without changing split membership. Queue files contain identifiers and sampling provenance; the interface joins redacted inputs and separately stored replies only when displaying one item.

## Deterministic queues

The project seed is 42. Selection order is a SHA-256 rank of the seed, a fixed namespace, and the stable example ID. Every queue keeps at most one example per conversation and combined duplicate group.

- Training (300): deterministic coverage enrichment over observable keyword proxies derived after reviewing the training-only discovery sample, followed by a deterministic remainder. The proxies cover security, billing, membership, accounts, catalog, library/playlists, playback, app/device, feature/market, short/context-limited, and general cases. They are sampling tags, not labels. This intentionally enriched batch must not be reported as natural intent prevalence. Later batches must remain training-only.
- Development (80): deterministic hash-ranked sample from the development pool, reserved for later tuning and development checks.
- Golden (200): 150 deterministic random eligible test candidates, then 50 additional challenge cases from remaining groups. The challenge selector round-robins over five predeclared observable flags: at most 40 characters, no preceding context, at least two question marks, security wording, and account-specific payment-dispute wording. These are sampling flags, not human labels.

No selected development or test message was displayed or manually inspected while defining the taxonomy or rules. Human golden annotation can record ambiguity after the guide is frozen, but it must not drive system design.

The generated training queue has 27 records in each of the 11 named coverage buckets plus 3 deterministic remainder records. The golden challenge set has 10 records assigned to each of its five flags. These are measured queue-construction counts, not class prevalence or labelled outcomes.

Named training-only extensions can be appended later with `extend-training-queue`. Existing IDs and positions are preserved, used conversations and duplicate groups are excluded, and rerunning `prepare-annotations` preserves recorded extensions. An optional observable coverage bucket supports intentional enrichment when genuine labels reveal a thin class; the batch metadata records that choice and never presents it as a label.

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

## Coverage review navigation

In the local app choose **Queue: training**, then **Training view: Coverage review**.
The example selector jumps directly to any of the 20 agreed training records and
shows its original queue position and stable ID. Back, Next, and Resume first
incomplete operate within this view. Full queue retains the original training
order; both views edit the same training CSV through the existing audited store.

The local, ignored `data/labels/annotation/coverage_review.json` pins the IDs
resolved from positions 31–32, 55–56, 82–83, 109–110, 136–137, 163–164,
190–191, 217–218, 244–245, and 271–272 before navigation was implemented.
The selector verifies that each ID remains at its recorded position. A missing
or moved ID is reported instead of silently selecting a replacement. The source
queue fingerprint records the original selection; appending later training rows
does not invalidate unchanged pinned IDs. This file is local review material and
is not distributed with the repository. If missing, Coverage review displays its
expected path; the ordinary Full queue view remains available.

Sampling proxies are not displayed as proposed answers. Unsaved judgments remain
blank and future replies follow the existing reveal gate. Navigation itself
creates no labels, rewrites no queue, and changes no provenance. Existing local
assistance declarations and audit records remain intact. Changes arising from
the conversational pilot review require the owner's decision for each case;
assistant suggestions do not authorize edits. The flagged pilot review is now
complete; four uncertainties remain explicitly recorded. Coverage review remains
optional (0/20 at policy consolidation), not a new freeze prerequisite.

The active v0.2 policy leaves existing human labels under their original versions.
They are reported stale until individually re-reviewed. Final approval may use an
explicit prior-version-pilot acknowledgement without changing any row. Separate
machine-label commands and their freeze, privacy, and validation gates are documented
in [machine_annotation.md](machine_annotation.md). Machine output is never loaded
into the human annotation UI or counted as human completion.
