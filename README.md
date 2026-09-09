# SpotifyCares Support Agent

This repository is the staged implementation of a Hiver SDE Intern take-home assignment. It will use real SpotifyCares conversations from Kaggle's `thoughtvector/customer-support-on-twitter` dataset to classify support intents, retrieve relevant historical conversations, draft grounded replies, and decide whether each case can be auto-handled or needs a human.

The repository currently contains **only the Stage 1 scaffold**. No dataset has been downloaded, no examples have been labelled, no model has been trained, and no evaluation results are claimed yet.

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
usage: spotify-cares [-h] [--version] {config} ...

SpotifyCares support-agent project tools.
```

The initial `config` command prints and validates the central YAML configuration:

```bash
uv run spotify-cares config
uv run spotify-cares config --path configs/project.yaml
```

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

Pending data ingestion, development-only intent discovery, and completion of the annotation guide.

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

The source dataset is not redistributed here. A later stage will document an explicit download and filtering command. Raw tweets can contain handles and other personal data, so raw and interim files stay outside source control. Human labels will be stored as CSV, processed datasets as Parquet, and predictions as JSONL.

## Reproducibility target

The final headline experiment is designed to run in under 15 minutes after prerequisites and cached model/data assets are available. The future evaluation command will time itself and record environment metadata; no runtime claim has been measured in this scaffold stage.
