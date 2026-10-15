# Contributing to SpotifyCares Support Agent

Thank you for your interest in contributing to the SpotifyCares Support Agent!

This project implements an open-source, reproducible customer-support agent for Spotify inquiries. It uses Retrieval-Augmented Generation (RAG) with local historical vector search and deterministic safety policies to assist support teams by drafting replies and routing high-risk inquiries.

We welcome contributions across four main tracks:
- **Labelling**: Measuring inter-annotator agreement and adjudicating difficult customer support boundaries.
- **Modelling**: Experimenting with zero-shot/few-shot intent classification and improved retrieval techniques.
- **Evaluation**: Building automated response-quality judges and evaluating safety trade-offs.
- **Taxonomy**: Refining intent definitions, boundary edge cases, and escalation criteria based on real support data.

---

## 1. Development Setup

### Requirements
- **Python 3.11** (`pyproject.toml` requires `>=3.11,<3.12`)
- [`uv`](https://docs.astral.sh/uv/) package manager

### Environment Installation
Install the project dependencies and optional toolchains with `uv`:
```bash
uv sync --extra dev --extra annotation
```
- `dev`: installs `pytest`.
- `annotation`: installs `streamlit` for the annotation interface.

### Running Automated Tests
All unit tests are offline, deterministic, and mock external API dependencies. Run:

**Windows (PowerShell):**
```powershell
$env:TMP="C:\temp"
$env:TEMP="C:\temp"
uv run pytest -q --tb=short --basetemp=C:\temp\ptsc
```

**macOS / Linux:**
```bash
uv run pytest -q
```

---

## 2. Local Data & Pipeline Rebuilding

The raw dataset, processed parquet splits, human labels, and local embeddings are **not** committed to the repository to protect privacy and respect licensing constraints.

To reproduce the pipeline from raw Twitter Support data locally:
1. Review the data ingestion and splitting guides in [`docs/extraction.md`](docs/extraction.md) and [`docs/preprocessing.md`](docs/preprocessing.md).
2. Extract conversations:
   ```bash
   uv run spotify-cares extract
   ```
3. Preprocess and split into leakage-resistant pools:
   ```bash
   uv run spotify-cares preprocess
   uv run spotify-cares validate-splits
   ```
4. Prepare annotation queues:
   ```bash
   uv run spotify-cares prepare-annotations
   ```

---

## 3. API Keys & Rate Limit Handling

- Store API credentials only in a local `.env` file at the repository root. Never commit `.env` or hardcode credentials anywhere.
- Copy `.env.example` as a template:
  ```bash
  cp .env.example .env
  ```
- Supported providers:
  - **Groq** (`GROQ_API_KEY`): Primary provider (`openai/gpt-oss-120b`).
  - **Google Gemini** (`GEMINI_API_KEY`): Fallback provider.
- **Free-Tier Limits**: Free-tier provider endpoints enforce strict token and request ceilings (e.g., Groq ~8,000 TPM and 1,000 requests/day; Gemini ~20 requests/day). The pipeline uses a local rate-limit ledger to pace requests (~30–60s spacing). Evaluations pause or stop when physical daily quotas are depleted; they can be resumed once quotas reset.

---

## 4. Sacred Rules & Evaluation Integrity

### The Golden Set Rule
- The 150 human golden labels in `data/labels/annotation/labels/golden.csv` are **strictly frozen**.
- **Never** tune prompts, train classifiers, optimize retrieval thresholds (`min_similarity`), or select models against golden set results.
- All exploratory analysis, prompt engineering, and hyperparameter tuning must be performed exclusively on the **development queue** (`--queue development`).
- Evaluating against the golden queue requires the explicit `--golden-confirmed` CLI flag to prevent accidental unblinding:
  ```bash
  uv run --env-file .env spotify-cares evaluate --queue golden --live --golden-confirmed
  ```

### Evaluation Honesty Rule
- **Always** report the generation fallback rate alongside every accuracy, precision, and recall metric.
- **Never** report or count runs with generation fallback as pure LLM capability; degraded fallback predictions reflect the baseline fallback policy, not model quality.

---

## 5. Labelling Contributions

We welcome additional human review and agreement studies:
- The active taxonomy is defined in [`configs/taxonomy.yaml`](configs/taxonomy.yaml) and the annotation guidelines in [`docs/annotation_guide.md`](docs/annotation_guide.md).
- To launch the local annotation web interface:
  ```bash
  uv run --extra annotation streamlit run app/annotation_app.py
  ```
- **Second-Annotator Independence**: Annotations from additional annotators must be saved to a separate file (e.g. `data/labels/annotation/labels/golden_annotator2.csv`) to calculate inter-annotator agreement (Cohen's kappa). **Never overwrite, modify, or merge into the existing `golden.csv`**.

---

## 6. How to Contribute Code

1. **Discuss First**: Before starting major work, check open GitHub issues or create an issue describing your proposed change and approach.
2. **Keep PRs Small & Scoped**: Focus each pull request on a single improvement or bug fix.
3. **Preserve Package Architecture**: The core package in `src/spotify_cares` must remain strictly independent of Streamlit UI components.
4. **Include Tests**: Add unit tests in `tests/` covering any new functionality or edge cases. Tests must be fast, self-contained, and mocked (no network calls, no live API keys).
5. **Describe Verification**: In your pull request description, explain the commands you ran to verify your changes and report test results.

---

## 7. Contributors

<!-- Fill in contributor names, handles, and roles below -->
- **Project Lead**: nayanhasnolyf
- *Open for community contributors!*
