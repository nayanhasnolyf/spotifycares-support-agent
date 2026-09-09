# Decision log

This is a chronological record of decisions actually made. It is not a list of aspirations. New entries are added only when implementation or observed data forces a real choice.

## D001 — Use a `src`-layout installable package

- **Date:** 2026-09-09
- **Decision:** Put Python code under `src/spotify_cares` and expose an installed `spotify-cares` command.
- **Rationale:** A src layout makes tests exercise the installed package instead of accidentally importing files from the repository root, while one CLI gives later stages a stable reproducibility surface.

## D002 — Keep the initial CLI dependency-light

- **Date:** 2026-09-09
- **Decision:** Build the command shell with Python's standard `argparse` rather than adding Typer or Click.
- **Rationale:** Neither library is required by the assignment. The standard library is enough for the first-stage help/config commands and reduces setup and transitive dependencies.

## D003 — Centralize stable project contracts in strict YAML

- **Date:** 2026-09-09
- **Decision:** Store brand, source, seed, paths, and required storage formats in `configs/project.yaml`, validated by Pydantic models that reject unknown fields.
- **Rationale:** Later commands should share one reviewed configuration. Rejecting extra keys catches misspellings instead of silently running with unintended defaults.

## D004 — Pin Python to the 3.11 minor line

- **Date:** 2026-09-09
- **Decision:** Declare `>=3.11,<3.12` and manage the environment and lockfile with uv.
- **Rationale:** The assignment explicitly specifies Python 3.11; restricting the minor version makes reproduction less sensitive to behavior changes in newer Python releases.

## D005 — Add PyArrow as an explicit runtime dependency

- **Date:** 2026-09-09
- **Decision:** Include PyArrow even though it is not named in the requested stack.
- **Rationale:** pandas needs a Parquet engine, and the deliverable explicitly requires Parquet. An explicit engine avoids a late, machine-dependent optional-dependency failure.

## D006 — Separate human labels from generated data

- **Date:** 2026-09-09
- **Decision:** Use `data/labels` for genuine human-authored CSVs and reserve `data/processed` for rebuildable Parquet files.
- **Rationale:** Golden labels are costly source artifacts that may eventually be intentionally versioned, whereas processed tables should be reproducible and ignored by default.

## D007 — Keep Streamlit optional and outside the core pipeline

- **Date:** 2026-09-09
- **Decision:** Put Streamlit in an optional `annotation` dependency group and keep package/CLI code independent of it.
- **Rationale:** Annotation UI dependencies should not increase the cost or fragility of the required headless evaluation path.

## D008 — Do not claim placeholder results

- **Date:** 2026-09-09
- **Decision:** Scaffold the required README report headings as an explicit future contract without tables, example labels, ratings, runtimes, or metrics.
- **Rationale:** No real data or human evaluation exists in this stage, and filling the report early would risk presenting invented evidence.

## D009 — Default-exclude source-derived labels and evaluation artifacts

- **Date:** 2026-09-09
- **Decision:** Ignore `data/labels` and generated `artifacts` by default, then intentionally allow individual reviewed files only after redistribution and privacy checks.
- **Rationale:** Human labels and evaluation examples may reproduce customer text. Opt-in tracking makes an accidental personal-data commit less likely while preserving a path to version safe, permitted artifacts later.

## D010 — Normalize tracked text files to LF

- **Date:** 2026-09-09
- **Decision:** Add a repository-level `.gitattributes` rule that stores text files with LF endings.
- **Rationale:** The project is developed on Windows but should remain reproducible across operating systems. Stable line endings prevent noisy whole-file diffs and lockfile churn.

## D011 — Index all metadata on disk, then hydrate only relevant text

- **Date:** 2026-09-09
- **Decision:** Use a chunked first pass into temporary SQLite without tweet text, followed by a second chunked pass that loads text only for SpotifyCares-connected records.
- **Rationale:** Cross-chunk relationships and duplicates require global lookup, but loading the 516 MB CSV and all customer text into Python memory is unnecessary. A disposable disk index gives exact lookup with bounded memory and a smaller privacy surface.

## D012 — Treat the child's direct-parent field as authoritative

- **Date:** 2026-09-09
- **Decision:** Build components and verified replies from `in_response_to_tweet_id`; use comma-separated `response_tweet_id` values only as cross-checks. Never repair a contradiction by merging on the response declaration.
- **Rationale:** A child can name only one direct parent, while the parent's response list is denormalized and can be missing or stale. Keeping disagreements visible avoids contaminating threads and reference targets.

## D013 — Exclude ambiguous components but retain incomplete ancestry

- **Date:** 2026-09-09
- **Decision:** Exclude candidates from cross-brand, cyclic, or conflicting-duplicate components. Allow a verified direct customer/SpotifyCares pair when older ancestors are missing, while flagging the available-context limitation.
- **Rationale:** The first conditions make ownership or dialogue order ambiguous. A missing older parent does not invalidate the direct reply evidence, so excluding it would unnecessarily bias the dataset toward fully linked conversations.

## D014 — Detect duplicates before redaction with bounded lexical candidates

- **Date:** 2026-09-09
- **Decision:** Form exact keys from normalized unredacted customer text, generate near-copy candidates through rare character four-gram blocks, and union accepted links with conversation membership before splitting.
- **Rationale:** Matching redacted text could make unrelated personal details collapse to the same placeholder. Rare deterministic blocks avoid an unrestricted all-pairs comparison, while combined groups keep repeated information on one side of evaluation.

## D015 — Quarantine groups that cross strict chronological cutoffs

- **Date:** 2026-09-09
- **Decision:** Base each example interval on all context, customer, and reply timestamps; quarantine an entire combined group if it spans a cutoff or has an unusable timestamp.
- **Rationale:** Splitting a duplicate-connected group would leak related language, while assigning a spanning group to training could place replies after held-out periods begin. Quarantine preserves both group integrity and honest chronology even when pool ratios move away from 70/15/15.
