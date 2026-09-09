# Project agent instructions

These instructions apply to the entire repository and persist the owner's requested implementation workflow.

## Scope and evidence

- The final brand is SpotifyCares; do not compare or switch brands.
- Implement only the stage requested in the current prompt.
- Never invent data, annotations, API outputs, human ratings, or measured results.
- Never train, tune, or select prompts using golden-test results.
- Keep the core pipeline independent of Streamlit.
- Do not publish, deploy, or submit the assignment.

## Privacy and repository safety

- Never commit secrets, `.env` files, credentials, raw datasets, unredacted customer data, downloaded models, or large generated outputs.
- Keep `.env.example` limited to placeholders.
- Commit source-derived data or evaluation artifacts only after confirming redistribution is permitted and personal information is appropriately handled.
- Preserve unrelated and pre-existing work. Never force-push or rewrite history.

## Completion workflow for every implementation prompt

1. Run checks relevant to the changes.
2. Update `docs/implementation_plan.md` and `docs/decision_log.md` when the stage or a real non-obvious decision changes.
3. Review the working tree and stage only files belonging to that stage.
4. Inspect staged filenames and content for secrets and unintended files without printing secret values.
5. Create one descriptive conventional commit when there are verified changes; never create an empty commit.
6. Push to the connected GitHub branch without asking for routine confirmation.
7. Report the commit hash, branch, repository link, check results, and remaining blockers.

If a stage is blocked by data, genuine human labels, or credentials, commit verified implementation progress with an accurate message and do not describe the stage as complete. If checks remain failing, report that accurately.
