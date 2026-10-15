# SpotifyCares Support Agent

A retrieval-grounded customer-support drafting agent for SpotifyCares, built on the public Customer Support on Twitter dataset.

The repository implements an end-to-end pipeline: data extraction and conversation reconstruction, redaction and leakage-resistant splitting, a frozen intent taxonomy and annotation guide, machine annotation of training examples (Groq with Gemini fallback), 150 human golden labels, trivial and TF-IDF baselines, a semantic-retrieval LLM agent with deterministic policy routing, and an offline evaluation harness. Drafts are never sent; the agent only proposes a reply and an auto-handle/escalate decision.

> [!IMPORTANT]
> There is currently **no clean, reproducible agent result** for the current configuration. Every agent run so far was affected by free-tier provider quota exhaustion. See [Results](#2-results) for exactly what the saved artifacts do and do not show.

## Final Report

### 1. Framing

The agent is meant to help human support staff by pre-drafting replies and proposing a routing decision. For each customer message it:

1. Retrieves up to 5 similar historical SpotifyCares conversations from the **training split only** (`all-MiniLM-L6-v2` embeddings, cosine similarity, `min_similarity` 0.20). Retrieved replies are passed to the model as *untrusted historical examples*, not verified resolutions or current policy.
2. Asks the LLM (Groq `openai/gpt-oss-120b`, Gemini fallback) for a schema-validated draft, the evidence IDs it used, and an intent from the frozen 9-intent taxonomy. Drafts citing unknown evidence or making unsupported action/current-fact claims are rejected.
3. Applies deterministic policy rules (current security incident, payment investigation, private account action) that force escalation regardless of the LLM output.

A case is proposed for **auto-handling only** when no policy rule fires, generation succeeded, and the draft cites retrieved evidence. Otherwise it is escalated. If generation fails, the reply falls back to a fixed acknowledgement template and the **intent falls back to the TF-IDF baseline classifier**.

### 2. Results

Evaluation set: **150 golden examples**, each hand-labelled by a single annotator (the project owner) under the frozen guide; 83 should escalate and 67 can be auto-handled. These are the 150 random test-candidate examples; the 50 planned challenge cases were not labelled. Training labels for the classifier (265 examples) are **machine-generated**, not human.

**Latest saved report** (`artifacts/evaluation/report.json`, generated 2026-09-20; local, Git-ignored):

| System | Intent accuracy | Escalation recall | Escalation precision | Unsafe auto-handles | Generation fallback rate |
|---|---|---|---|---|---|
| Trivial (majority intent, always escalate) | 12.0% (18/150) | 100% (83/83) | 55.3% | 0 of 0 auto-handled | n/a |
| TF-IDF + logistic regression | 16.0% (24/150) | 0% (0/83) | 0.0% (0/3) | 83 of 147 auto-handled (56.5%) | n/a |
| Agent | 16.0% (24/150) | 100% (83/83) | 55.3% | 0 of 0 auto-handled | **100%** |

The agent row in this report is **not a measurement of the LLM**. Every one of its 150 generations fell back (provider unavailable), so every case was escalated and every intent came from the TF-IDF fallback, which is why it matches the TF-IDF accuracy exactly.

Baseline predictions are replayed from a cache written on 2026-09-18, so they may predate the current 265-label training set.

**Earlier run, now superseded and not reproducible** (recorded in commit `278ad81`, 2026-09-19): agent intent accuracy 36.0% (54/150), escalation recall 45.8% (38/83), 45 unsafe auto-handles out of 72 proposed auto-handles (62.5%), and 52.0% (78/150) of cases flagged for insufficient retrieval or generation evidence. Treat these numbers as historical only:

- The run was assembled across resumed sessions (102 examples, then 48 the next day) from a prediction cache that keeps fallback predictions, so it mixes successful LLM outputs with TF-IDF fallback intents; its fallback rate was not recorded.
- Its prediction cache is no longer retained, and the model, prompt and retrieval settings have changed since, so it does not describe the current configuration.

Reply quality has **not** been evaluated: no human reply ratings or LLM-judge scores exist yet (`pending_human_ratings` in the report).

### 3. Baseline Comparison

Two automated baselines are compared against the agent:

1. **Trivial baseline:** always predicts the majority training intent (`feature_and_market_availability`) and always escalates. 12.0% intent accuracy; perfect escalation recall by construction, with zero auto-handling coverage.
2. **TF-IDF baseline:** TF-IDF + logistic regression intent classifier trained on the 265 machine-labelled examples, plus lexical retrieval and a narrower heuristic version of the keyword policy rules. 16.0% intent accuracy, but it auto-handles 98% of cases and misses every true escalation.

No valid agent-versus-baseline comparison exists yet for the current agent configuration (see Results).

### 4. Failure Modes

Observed in saved artifacts or logs:

1. **Provider quota exhaustion collapses the agent into the baseline.** Free-tier limits (Groq ~8,000 TPM and 1,000 requests/day; Gemini 20 requests/day) repeatedly stopped evaluations. On failure the agent escalates with a template reply and takes its intent from TF-IDF, producing the 100%-fallback report above.
2. **Weak, majority-biased intent classification in the baselines.** Trained on only 265 machine labels, the TF-IDF classifier predicts just 5 of the 9 intents on the golden set and assigns `feature_and_market_availability` to 131 of 150 cases, while the most common golden intent is `app_device_technical` (40/150).
3. **Unsafe auto-handling when escalation depends on narrow keyword rules.** The deterministic policy rules match specific phrases (e.g. "hacked", "duplicate charge", "refund my"). The TF-IDF system auto-handled all 83 cases a human said should escalate, and the superseded agent run still auto-handled 45 of them.

Hypothesised, not yet measured:

4. **Retrieval mismatch:** short or vague messages may retrieve irrelevant historical conversations. The "insufficient retrieval or generation evidence" rate cannot isolate this yet, because it also counts generation failures.
5. **Prompt-injection bleed:** customer text or retrieved historical replies could influence the draft despite being labelled untrusted.

### 5. What is misleading about my headline number?

- **The agent numbers are not LLM measurements.** The latest agent row is 100% fallback, and the superseded 36.0% run mixes LLM outputs with TF-IDF fallback intents.
- **Escalation recall alone rewards doing nothing.** Always escalating scores 100% recall; precision (55.3%) and auto-handling coverage (0%) must be read alongside it.
- **The golden labels have a single annotator.** No double-labelling or inter-annotator agreement has been measured, so label noise is unknown.
- **The classifier learns from machine labels.** Intent accuracy reflects agreement between a model trained on Groq/Gemini labels and one human's judgement.
- **The data is public Twitter support traffic.** Short public complaints differ from chat or email support, so results may not transfer.

### 6. Next Steps

1. **Re-run a clean agent evaluation** when provider quotas allow: start from an empty agent prediction cache and report the fallback rate next to every metric. Do not count runs with fallback as LLM results.
2. **Tune only on development data.** Prompt or threshold changes must be selected on the development queue, never on golden results.
3. **Measure label reliability** by double-labelling a golden subset and reporting agreement.
4. **Evaluate reply quality** with human ratings, then validate any LLM judge against them.

---

## Running the Application

### 1. Requirements

- Python 3.11 (`pyproject.toml` requires `>=3.11,<3.12`)
- [`uv`](https://docs.astral.sh/uv/) package manager
- For live agent calls: `GROQ_API_KEY` and/or `GEMINI_API_KEY` in a local `.env` (copy `.env.example`; never commit `.env`)
- The raw dataset, processed splits, labels and embedding model are **not** in the repository. Rebuild them locally with the pipeline commands described in `docs/` (`extract`, `preprocess`, `prepare-annotations`).

### 2. Setup

```powershell
uv sync --extra dev --extra annotation
```

`dev` installs pytest; `annotation` installs Streamlit.

### 3. Agent Demo (CLI)

```powershell
uv run --env-file .env spotify-cares agent-demo --message "My music stops playing randomly"
```

### 4. Machine Annotation with Provider Fallback

Groq is the primary annotation provider and Gemini is the fallback when a Groq request fails. Groq's local token pacing (`ProviderPause`) is respected rather than bypassed. Machine labels are written only for the training and development queues; human golden labels are never read or modified by this workflow.

```powershell
uv run --env-file .env spotify-cares machine-annotate --queue training --provider groq --fallback-provider gemini --limit 5
```

### 5. Evaluation

```powershell
uv run --env-file .env spotify-cares evaluate --queue golden --live --golden-confirmed
```

Golden evaluation requires the explicit `--golden-confirmed` flag. Predictions are cached in `artifacts/evaluation/` and reused on later runs.

### 6. Agent Demo (Streamlit)

```powershell
uv run --extra annotation streamlit run app/agent_app.py
```

### 7. Automated Tests

```powershell
$env:TMP="C:\temp"
$env:TEMP="C:\temp"
uv run pytest -q --tb=short --basetemp=C:\temp\ptsc
```
