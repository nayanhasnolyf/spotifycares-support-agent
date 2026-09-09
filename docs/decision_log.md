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
