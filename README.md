# SpotifyCares Support Agent

This repository is the staged implementation of a Hiver SDE Intern take-home assignment. It will use real SpotifyCares conversations from Kaggle's `thoughtvector/customer-support-on-twitter` dataset to classify support intents, retrieve relevant historical conversations, draft grounded replies, and decide whether each case can be auto-handled or needs a human.

Stages 1 through 3 are complete. The owner-approved v0.2 policy is frozen locally. The 30 completed, partly AI-assisted training annotations retain their older versions and remain stale, not silently re-reviewed. Live `gemini-2.5-flash` annotation has 11 validated machine-labelled training examples, one failed attempt (HTTP 429), and 258 unattempted examples; development remains 0/80 and golden remains human-only and untouched. Generation is incomplete and paused on rate/quota limiting. No classifier training or evaluation has run. All source-derived text remains Git-ignored. See [the frozen-policy and machine workflow](docs/machine_annotation.md).

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/) and network access for the first dependency install.

```bash
uv python install 3.11
uv sync --extra dev --extra annotation
uv run spotify-cares --help
uv run pytest
```

For later Gemini-powered stages, create a local environment file and add your own API key:

```bash
cp .env.example .env
```

On PowerShell, use `Copy-Item .env.example .env` instead. The `.env` file and raw data are ignored by Git.

## Current CLI

```text
usage: spotify-cares [-h] [--version] {config,extract,preprocess,validate-splits,prepare-annotations,validate-annotations,extend-training-queue,guide-status,freeze-guide,machine-annotate,validate-machine-annotations} ...

SpotifyCares support-agent project tools.
```

The initial `config` command prints and validates the central YAML configuration:

```bash
uv run spotify-cares config
uv run spotify-cares config --path configs/project.yaml
```

Place the Kaggle CSV at `data/raw/twcs.csv`, then run the complete Stage 2 extraction:

```bash
uv run spotify-cares extract
```

The command reads 50,000 records at a time by default. Use `--chunk-size` only for memory-constrained machines or software checks:

```bash
uv run spotify-cares extract --chunk-size 10000
```

### Stage 2 measured extraction audit

Source file SHA-256: `cd297fcfa1bf6f99938be242e8e578980bc6d1b96adc8691abec9a39175b03c0`.

| Measure | Observed value |
|---|---:|
| Source rows scanned | 2,811,774 |
| Unique tweet IDs | 2,811,774 |
| SpotifyCares tweets | 43,265 |
| Relevant customer tweets | 48,543 |
| Available conversation groups | 28,280 |
| Eligible customer examples | 41,339 |
| Direct SpotifyCares reference replies | 42,830 |
| Exclusion records | 246 |

Observed quality conditions were 974 missing link targets (69 missing direct parents and 905 missing declared response targets) and 246 cross-brand candidate exclusions. There were no duplicate tweet IDs, conflicting links, cycles, invalid timestamps, missing timestamps, or missing text in the relevant records.

Conversation groups contain 2 tweets at the minimum and median, 3.25 on average, 6 at the 90th percentile, and 354 at the maximum. “Conversation” means the complete **available** connected group; missing source records prevent a guarantee of real-world completeness.

This audit reports dataset construction, not support quality. A SpotifyCares reply may be a question or a request to continue privately and does not prove resolution.

### Stage 3 preprocessing and chronological pools

```bash
uv run spotify-cares preprocess
uv run spotify-cares validate-splits
```

The final Stage 3 run completed in 136.6 seconds and produced:

| Assignment | Examples | Complete content date range (UTC) |
|---|---:|---|
| Training/retrieval | 27,455 | 2014-05-15 23:34:20 to 2017-11-15 23:20:34 |
| Development | 5,198 | 2017-11-15 23:24:19 to 2017-11-25 22:26:20 |
| Held-out test candidates | 5,172 | 2017-11-25 22:28:46 to 2017-12-03 22:56:04 |
| Quarantined | 3,514 | Combined groups spanning a chronological cutoff |

All 41,339 Stage 2 examples passed structural revalidation. The target fractions were 70%/15%/15%, but exact ratios were not forced: conversation and duplicate groups remain indivisible, and boundary-spanning groups are quarantined. Stage 4 subsequently selected a 200-example golden queue from the test-candidate pool; its human labels remain outstanding.

The duplicate audit found 165 exact groups covering 775 examples and 145 conservative near-duplicate groups covering 360 representatives from 280 accepted links. Near matching evaluated 252,967 blocked candidates, while 425 messages shorter than 20 characters participated only in exact matching. The largest conversation-plus-duplicate group contains 624 examples across 129 threads; it was kept intact. Transitive grouping can be broader than any one pair, which is a known conservative risk.

Across customer, context, and reply fields, preprocessing replaced 42,026 brand handles, 94,046 other handles, 37,129 URLs, 1,561 IP addresses, 244 phone-like strings, and 15 long numbers. No email patterns were detected. Automated redaction is imperfect and is not a claim of anonymity.

All nine leakage checks pass: example, conversation, combined-group, and tweet IDs are disjoint; retrieval and discovery data are training-only; context is ancestor-only; future replies stay outside inputs; and strict chronology holds.

### Stage 4 proposed taxonomy and annotation workflow

Only the 400 redacted training discovery messages were inspected to propose these nine primary intents: `playback_and_audio`, `app_device_technical`, `account_access_and_profile`, `plan_and_membership`, `billing_and_payment`, `library_and_playlists`, `catalog_and_content`, `feature_and_market_availability`, and `other_or_unclear`. Security, payment, personal-data, safety, and abusive-content risks are separate flags. The intent and human-escalation judgments are independent.

| Queue | Size | Construction | Current label state |
|---|---:|---|---|
| Training | 300 | Topic-proxy coverage enrichment plus deterministic remainder | 30 completed under v0.1, stale under v0.2 |
| Development | 80 | Deterministic hash-ranked sample | Freeze gate satisfied; 0 complete |
| Golden | 200 | 150 random plus 50 challenge | Human-only; 0 complete |

Every queue has unique conversation and combined duplicate-group IDs. The golden challenge stratum has 10 selections for each predeclared flag: very short text, missing context, multiple question clauses, security wording, and account-specific payment-dispute wording. These are selection flags—not intent or escalation labels. There is no cross-queue example overlap. The training coverage sample is intentionally enriched and must not be used as an estimate of natural intent frequencies.

Prepare or reproduce the local ignored files, validate them, and start the app:

```bash
uv run spotify-cares prepare-annotations
uv run spotify-cares validate-annotations
uv run --extra annotation streamlit run app/annotation_app.py
```

The app binds to `http://127.0.0.1:8501` by default and does not deploy. Labels are saved atomically as CSV under `data/labels/annotation/labels/`; queues, audit JSONL, hashes, local state, and redacted taxonomy examples live beside them and are also ignored.

The flagged pilot review is complete. The owner approved and froze v0.2, acknowledging limited coverage and unchanged older label versions. The 20-example Coverage review is optional, not a new prerequisite. The following workflow was executed once; do not repeat an existing freeze:

```bash
uv run spotify-cares freeze-guide \
  --annotator-id YOUR_ID \
  --confirm-taxonomy-version spotify-intents-v0.2-proposed \
  --confirm-guide-version spotify-annotation-v0.2-proposed \
  --acknowledge-prior-version-pilot
```

The default freeze gate requires a complete/current pilot. The explicit acknowledgement above accepts a complete prior-version pilot and records its staleness without editing labels. Missing/incomplete records still block freeze. Freezing records the current hashes and unlocks human development/golden annotation; machine generation never accepts golden. The next action is configuring the ignored `.env` locally and running the five-example training smoke test documented in `docs/machine_annotation.md`.

If the genuinely labelled training set later lacks coverage, append a named training-only batch without replacing the initial 300 or any existing extension:

```bash
uv run spotify-cares extend-training-queue --name batch2 --size 100
```

An optional `--coverage-bucket billing` (or another documented observable proxy) can enrich a later batch, but that proxy is not a human intent label and the resulting batch does not represent natural frequency.

## Repository structure

```text
.
├── artifacts/                 # Generated predictions, metrics, and figures
├── app/                       # Optional local Streamlit annotation UI
├── configs/                   # Project settings and proposed taxonomy
├── data/
│   ├── raw/                   # Unmodified Kaggle files; never committed
│   ├── interim/               # Rebuildable intermediate data; never committed
│   ├── processed/             # Rebuildable Parquet datasets
│   └── labels/                # Local queues, state, audit, and human CSV labels
├── docs/
│   ├── annotation_guide.md    # Proposed human labelling contract
│   ├── decision_log.md        # Decisions that have actually been made
│   └── implementation_plan.md # Stage boundaries and leakage controls
├── src/spotify_cares/         # UI-independent Python package and CLI
└── tests/                     # Fast software tests using synthetic fixtures only
```

`data/labels/` is separate from generated data because genuine human annotations are source material, while processed Parquet files and JSONL predictions are reproducible outputs. Empty placeholder directories are retained with `.gitkeep`; their contents remain ignored where appropriate.

## Assignment report

The final report will live here. Its required sections are scaffolded below, but evidence-based content is intentionally pending.

### Framing and discovered intents

Stage 3 produced a deterministic training-only discovery sample of 400 redacted customer messages. Stage 4 used only that sample to propose nine intents and an independent escalation policy. The taxonomy remains proposed pending human pilot review; no labels or performance results exist yet.

### Results and baseline comparison

Pending frozen evaluation against the trivial baseline, simple baseline, and proposed system.

### LLM reply-judge validation

Pending collection of genuine human reply ratings and an independent comparison between those ratings and the LLM judge.

### Five observed failure modes

Pending evaluation errors. Failure modes will be reported from inspected real examples, not anticipated examples presented as findings.

### What is misleading about my headline number?

Pending the final metric, uncertainty analysis, dataset coverage analysis, and judge validation.

### Next steps

Pending evidence from the completed evaluation.

## Data and privacy

The source dataset is not redistributed here. Obtain `twcs.csv` from Kaggle's `thoughtvector/customer-support-on-twitter` dataset and place it at `data/raw/twcs.csv`. Raw tweets can contain handles and other personal data, so raw, interim, processed, label, and evaluation artifact contents are ignored by default. Human labels will use CSV, processed datasets use Parquet, and predictions will use JSONL.

The local extraction writes:

- `data/processed/relevant_tweets.parquet`
- `data/processed/support_examples.parquet`
- `data/processed/conversations.parquet`
- `data/processed/relationships.parquet`
- `data/processed/exclusions.parquet`
- `data/processed/duplicate_records.parquet`
- `data/processed/extraction_audit.json`

No source-derived text or examples are committed. See `docs/extraction.md` for reconstruction details and `docs/preprocessing.md` for redaction, duplicate grouping, split rules, and Stage 3 output schemas.

## Reproducibility target

The final-code Stage 2 extraction completed in 520.4 seconds (8 minutes 40 seconds) on the development machine. This is an ingestion runtime, not the future model-evaluation runtime. The final headline experiment will be timed and recorded separately.
