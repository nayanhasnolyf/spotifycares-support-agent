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

Implemented: nine proposed intents have inclusion/exclusion rules, training example IDs, local ignored redacted examples, and difficult-boundary rules; all 12 Stage 3 output hashes and nine leakage checks pass; the annotation UI and validators are usable; queues contain 300 training, 80 development, and exactly 200 golden examples with 150/50 strata and group separation. The freeze gate requires 30 complete, current pilot annotations. Reproducible named training-only extensions can later be appended without replacing prior queue entries.

Still required for Stage 4 completion: the project owner must review the pilot findings, resolve or accept recorded ambiguities, assess missing topic boundaries, and explicitly freeze the accepted taxonomy/escalation/guide contract. Tool readiness and a complete record count do not establish annotation independence or adequate pilot coverage.

Pilot review checkpoint (2026-09-11): 30/30 pilot records are complete/current, with 270 further training, 80 development, and 200 golden annotations outstanding. The owner reports some ChatGPT assistance; the assisted subset is unknown, so this pilot does not establish independent human labelling. Assistant review found a security-heavy pilot caused by consecutive sampling buckets, three marked ambiguous cases, and reason/flag/guidance issues for human adjudication. See `docs/training_pilot_review.md` for exact proposed guide additions and a 20-record supplemental review proposal drawn from existing training-queue metadata. The guide remains proposed; existing labels, guide hashes, queues, and freeze state are preserved. Completion count alone is not enough to recommend freezing.

Stage 4 review continuation: the local annotation app now has a Coverage review
view of the 20 agreed existing training records, pinned by stable ID. It shares
the original training label store and preserves queue order. One-at-a-time case
adjudication has since been completed for the flagged pilot cases, with explicit
owner decisions and local AI-assistance provenance. Final guide approval remains pending.

Stage 4 policy consolidation (2026-09-13): active taxonomy and guide are now
`spotify-intents-v0.2-proposed` and `spotify-annotation-v0.2-proposed`.
All 30 existing completed annotations retain their prior versions and are stale
under the new contract, not silently re-reviewed. Queues, split assignments,
annotation revisions, and local assistance records are preserved. The owner may
explicitly acknowledge the completed prior-version pilot at final freeze without
refreshing its labels. The 0/20 Coverage review is a documented limitation, not
a new prerequisite. Human coverage remains concentrated in account/security,
with no current pilot playback or membership labels and four retained ambiguities.

Machine-annotation tooling is implemented separately from human CSVs, with a
matching-freeze gate for both training and development, provenance-bound resumable
JSONL, strict response validation, and explicit failed attempts. Existing human
records of every status are excluded. Golden files and future replies are not
read by this workflow. Synthetic tests exercise its gates and persistence;
no real generation, classifier training, or evaluation is authorized in this stage.
Live Gemini integration remains unverified until approval/freeze and credentials
are available. Machine development labels support model-agreement measurements,
not independent human accuracy. See `docs/machine_annotation.md` for commands.
Verification: 57 tests passed using synthetic fixtures/fake providers; CLI help
and active contract/staleness reporting worked; all 38 protected local artifact
hashes were unchanged. No generation or freeze was executed.

Live-annotation preparation follow-up: the owner approved v0.2 and its limited
pilot coverage. The exact hashes were frozen through the existing audited workflow
with `NAYAN`; all 30 older labels remain stale and unchanged. The central config
now selects the documented structured-output model `gemini-2.5-flash`. Generation
stops on provider errors and refuses automatic retries of recorded permanent HTTP
errors. No API key was available; an ignored empty `.env` placeholder is ready for
local editing. The five-example training smoke test and subsequent 270 training /
80 development generation remain blocked, with zero generated and zero failed
attempts. No training or evaluation ran. This supersedes the earlier pending-freeze
status, not the historical verification record above.
Follow-up verification: 65 synthetic tests passed; both actual machine-output
validators report structurally clean but incomplete empty runs; 37 protected
local artifact hashes were preserved outside the intended freeze-state/audit writes.

Latest machine-run checkpoint: the owner's five-example live training smoke test
was validated against the frozen guide, taxonomy, prompt, model, queue, and input
hashes. Resuming through the existing CLI without `--limit` added six successful
records, then stopped on HTTP 429. Training now has 11 validated successes, one
unresolved provider failure, and 258 unattempted examples (259 still need labels).
Development generation was not started against the same rate/quota limit and
remains 0/80. Both validators report incomplete outputs. The original five records
remain byte-for-byte unchanged and each appears once. All 39 protected local
artifact hashes, including human annotations, frozen policy state, golden queue,
and split assignments, are unchanged. All 30 human annotations remain stale.
The machine-workflow test module passed 26 synthetic tests. No code, policy,
classifier, or evaluation changes were made to work around the provider limit.

Quota-diagnosis follow-up: the saved 429 retained no quota metric, delay, or error
details, so its limit category and reset time remain unknown. No further API calls
were made. Added allowlisted quota/retry evidence capture and configurable pacing,
bounded exponential backoff with jitter for identified temporary limits, and clean
daily/billing/long-wait stops. Scheduling metadata is separate from the label run
identity, preserving the 11 successes and failed example's retry eligibility.
An explicit quota-availability acknowledgement is required before retrying the
legacy unknown 429. Training remains 11 successes / 1 failure / 258 unattempted;
development remains 0 successes / 0 failures / 80 unattempted. No classifier work.
Verification: 82 tests passed; CLI help and compilation checks passed; all 40
protected local artifact hashes (including machine output) remain unchanged.

## Stage 5 — Golden-set annotation (freeze satisfied; human work outstanding)

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
