# Data directories

- `raw/`: locally supplied, unmodified source files; ignored by Git.
- `interim/`: rebuildable intermediate tables; ignored by Git.
- `processed/`: rebuildable Parquet tables; ignored by Git.
- `labels/`: local annotation queues, state, audit logs, and genuine human-label CSVs. They are ignored by default until redistribution and privacy checks pass.

Do not put secrets or unnecessary personal data in any tracked file. No real or synthetic assignment examples are included at scaffold time.

Stage 3 writes redacted and normalized split outputs under `processed/splits/`. They remain ignored because automated redaction is imperfect and normalized fields can contain source personal information.

Stage 4 writes all annotation materials beneath `labels/annotation/`. Do not move these files into tracked paths: even redacted source text is not guaranteed anonymous, and human notes may contain sensitive details.
