# Data directories

- `raw/`: locally supplied, unmodified source files; ignored by Git.
- `interim/`: rebuildable intermediate tables; ignored by Git.
- `processed/`: rebuildable Parquet tables; ignored by Git.
- `labels/`: genuine human labels in CSV format, created in a later stage. They are ignored by default until redistribution and privacy checks pass.

Do not put secrets or unnecessary personal data in any tracked file. No real or synthetic assignment examples are included at scaffold time.

Stage 3 writes redacted and normalized split outputs under `processed/splits/`. They remain ignored because automated redaction is imperfect and normalized fields can contain source personal information.
