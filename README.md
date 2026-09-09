# SpotifyCares Support Agent

This repository is the staged implementation of a Hiver SDE Intern take-home assignment. It will use real SpotifyCares conversations from Kaggle's `thoughtvector/customer-support-on-twitter` dataset to classify support intents, retrieve relevant historical conversations, draft grounded replies, and decide whether each case can be auto-handled or needs a human.

Stages 1 and 2 are implemented. The real local source CSV has been validated and extracted, but raw and derived customer text remain Git-ignored. No examples have been intent-labelled, no model has been trained, and no model-evaluation results are claimed yet.

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/) and network access for the first dependency install.

```bash
uv python install 3.11
uv sync --extra dev
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
usage: spotify-cares [-h] [--version] {config,extract} ...

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

## Repository structure

```text
.
├── artifacts/                 # Generated predictions, metrics, and figures
├── configs/project.yaml       # Brand, seed, paths, and artifact formats
├── data/
│   ├── raw/                   # Unmodified Kaggle files; never committed
│   ├── interim/               # Rebuildable intermediate data; never committed
│   ├── processed/             # Rebuildable Parquet datasets
│   └── labels/                # Human-created CSV labels (added in a later stage)
├── docs/
│   ├── decision_log.md        # Decisions that have actually been made
│   └── implementation_plan.md # Stage boundaries and leakage controls
├── src/spotify_cares/         # UI-independent Python package and CLI
└── tests/                     # Fast software tests using synthetic fixtures only
```

`data/labels/` is separate from generated data because genuine human annotations are source material, while processed Parquet files and JSONL predictions are reproducible outputs. Empty placeholder directories are retained with `.gitkeep`; their contents remain ignored where appropriate.

## Assignment report

The final report will live here. Its required sections are scaffolded below, but evidence-based content is intentionally pending.

### Framing and discovered intents

Stage 2 identified 41,339 eligible customer messages with direct SpotifyCares replies. Intent discovery and the annotation guide remain pending and will use a development-only sample.

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

No source-derived text or examples are committed. See `docs/extraction.md` for the field separation and quality policies.

## Reproducibility target

The final-code Stage 2 extraction completed in 520.4 seconds (8 minutes 40 seconds) on the development machine. This is an ingestion runtime, not the future model-evaluation runtime. The final headline experiment will be timed and recorded separately.
