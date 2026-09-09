# Implementation plan

This plan separates exploratory work, model development, frozen evaluation, and reporting. Stages 1 through 3 are complete. Stage 4 tooling and queues are ready, while its required human review and pilot remain open. Later stages may change as the real data reveals constraints; any meaningful change will be recorded in the decision log.

## Guardrails used throughout

- Use only real SpotifyCares conversations for task examples and measured results.
- Use synthetic data only in software tests, and label those fixtures clearly.
- Split examples before fitting or prompt selection, ideally grouping related conversation threads so one exchange cannot leak across splits.
- Discover intents and develop prompts without viewing golden-test outcomes.
- Freeze the golden set and evaluation contract before running the final comparison.
- Keep raw tweets, secrets, and unnecessary personal identifiers out of Git.
- Save processed datasets as Parquet, human labels as CSV, and predictions as JSONL.
- Keep pipeline modules callable without Streamlit.

## Version-control workflow

Each completed implementation prompt is checked, documented where appropriate, reviewed for secrets and unintended files, committed with a descriptive conventional commit, and pushed to the connected GitHub branch. Blocked stages may still commit verified progress, but the commit message and handoff must identify the incomplete outcome accurately. Force-pushes, empty commits, deployment, and assignment submission are outside this workflow.

## Stage 1 — Repository scaffold (complete)

Create the installable Python 3.11 package, uv environment, validated YAML configuration, CLI entry point, directory conventions, tests, README, implementation plan, and decision log. Verify CLI help, configuration loading, and tests. Do not fetch or inspect assignment data in this stage.

Exit criteria:

- `uv sync --extra dev` succeeds from a clean checkout.
- `uv run spotify-cares --help` succeeds.
- `uv run pytest` passes.
- Brand and file-format contracts are explicit in configuration.

## Stage 2 — Data ingestion and privacy audit (complete)

Implemented a chunked two-pass extractor with a temporary SQLite metadata index, source checksum, schema validation, exact SpotifyCares filtering, branch-safe conversation reconstruction, duplicate/conflict policies, local Parquet outputs, and a measured privacy-conscious audit. No task labels, split, redaction dataset, or model results were created.

Exit criteria met: the processed tables rebuild from the locally supplied real CSV in 520.4 seconds; aggregate counts and schemas were inspected; direct reply and no-leakage invariants pass; generated text remains Git-ignored; synthetic tests cover reconstruction edge cases.

## Stage 3 — Preprocessing and leakage-resistant pools (complete)

Implemented conservative normalization and role-aware redaction, structural eligibility revalidation, exact and blocked near-duplicate detection, conversation/duplicate combined groups, strict chronological splitting with boundary quarantine, separate input/reference exports, a training-only retrieval corpus, a deterministic 400-message discovery sample, an output-hashed manifest, and independent leakage validation.

Exit criteria met: all 41,339 real examples were processed; 27,455 train, 5,198 development, 5,172 test-candidate, and 3,514 cutoff-spanning examples were produced; strict chronology and all nine leakage checks pass; local derived text remains Git-ignored.

## Stage 4 — Intent discovery and annotation design (tooling and queues ready; human checkpoint pending)

Inspect only the 400-message training discovery sample, propose a compact taxonomy grounded in recurring requests, write a labelling guide, and build a local Streamlit annotation tool. Define intent, risk, ambiguity, expected-reply guidance, and policy escalation separately. Prepare deterministic 300/80/200 training/development/golden queues without moving examples across Stage 3 pools. Keep development and golden views locked until a human reviews a 30-item training pilot and freezes the exact guide hashes.

Implemented: nine proposed intents have inclusion/exclusion rules, training example IDs, local ignored redacted examples, and difficult-boundary rules; all 12 Stage 3 output hashes and nine leakage checks pass; the annotation UI and validators are usable; queues contain 300 training, 80 development, and exactly 200 golden examples with 150/50 strata and group separation.

Still required for Stage 4 completion: the project owner must review the proposal, genuinely label the 30-item training pilot, resolve or accept recorded ambiguities, and explicitly freeze the taxonomy/escalation/guide contract. Tool readiness is not human-labelling completion.

## Stage 5 — Golden-set annotation (blocked on Stage 4 human freeze)

Randomly select and genuinely hand-label a target of 200 examples (allowed range: 150–250). Preserve stable IDs and provenance. Double-label a subset to measure agreement and adjudicate disagreements without producing model predictions for the golden set.

Exit criteria: CSV has the required human fields, validation passes, the example count is in range, and the frozen split fingerprint is recorded.

## Stage 6 — Baselines and retrieval

Implement a trivial baseline, a simple scikit-learn baseline, and the proposed intent classifier. Embed historical training conversations with `all-MiniLM-L6-v2`; retrieve with NumPy cosine similarity. Fit and tune using training/development data only.

Exit criteria: deterministic training artifacts and development metrics are produced without reading golden labels during selection.

## Stage 7 — Reply drafting and routing

Use retrieved historical conversations as explicit grounding for Gemini drafts. Validate all structured model responses with Pydantic. Add deterministic policy signals plus model evidence for auto-handle versus human escalation, always storing a reason.

Exit criteria: every prediction has schema-valid intent, reply, retrieval provenance, handling decision, and reason; API failures are recoverable and observable.

## Stage 8 — Automated evaluation and judge validation

Freeze configurations, generate golden predictions once, compute classification and routing metrics with uncertainty intervals, and compare all baselines. Collect human reply ratings, run the LLM judge independently, and report association/agreement plus judge failure analysis.

Exit criteria: one command reproduces saved JSONL predictions, metrics, plots, and runtime in under the target budget on the documented machine/setup.

## Stage 9 — Final report and optional demo

Write the evidence-backed README report: framing, results, baseline comparison, five observed failure modes, “What is misleading about my headline number?”, and next steps. Optionally add a thin Streamlit demo that calls the same package APIs.

Exit criteria: every reported number traces to a generated artifact, instructions work from a clean checkout, and no secrets or raw personal data are tracked.
