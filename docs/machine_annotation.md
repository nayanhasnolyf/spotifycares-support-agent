# Policy approval and machine annotation

## Awaiting final approval

Active versions are `spotify-intents-v0.2-proposed` and
`spotify-annotation-v0.2-proposed`. Read the active guide, then run
`uv run spotify-cares guide-status` to see its exact hashes and checkpoint mismatch.
No local freeze state has been rewritten during consolidation.

The consolidated rules are: current unresolved request rather than history;
resolved acknowledgements use other/unclear; unavailable links supply no evidence;
most-specific supported routing reason; safe clarification is allowed without an
already-supported human-required issue; ambiguous wording does not prove multiple
problems; historical compromise is not an ongoing incident or proof of safety;
exposure needs disclosure evidence and is separate from private-information
requests; ordinary frustration is not automatically abuse or a threat.

No additional mandatory policy choice has been identified. Private-information
requests use notes/guidance, not a new flag. Historical compromise alone uses notes,
not the active-security flag. Earlier case decisions are not silently revised to
match these definitions. Four pilot records retain uncertainty, and all 30 labels
remain under their old contract. The pilot's security-heavy, partly AI-assisted
coverage cannot establish correctness across every intent. The 20 optional coverage
examples are not a new prerequisite. Final approval accepts these limitations,
not independent human labelling or row-level re-review.

After explicit owner approval only (not run during this stage):

```powershell
uv run spotify-cares freeze-guide `
  --annotator-id NAYAN `
  --confirm-taxonomy-version spotify-intents-v0.2-proposed `
  --confirm-guide-version spotify-annotation-v0.2-proposed `
  --acknowledge-prior-version-pilot
```

The acknowledgement is audited with the pilot counts; it does not refresh human
label versions. The ordinary current-pilot gate remains the default. Never rerun
queue preparation merely to update a policy version.

## Generation and validation commands (after freeze only)

Use an explicitly chosen Gemini model ID; none is silently selected. Configure
`GEMINI_API_KEY` locally in ignored `.env`, never in chat or a command argument.
The CLI does not implicitly load `.env`; uv can load it with `--env-file`.
No live API call or model-quality claim has been verified in this stage.

```powershell
uv run spotify-cares machine-annotate --help
uv run --env-file .env spotify-cares machine-annotate --queue training --model YOUR_GEMINI_MODEL_ID --limit 10
uv run --env-file .env spotify-cares machine-annotate --queue development --model YOUR_GEMINI_MODEL_ID --limit 10
uv run spotify-cares validate-machine-annotations --queue training --model YOUR_GEMINI_MODEL_ID
uv run spotify-cares validate-machine-annotations --queue development --model YOUR_GEMINI_MODEL_ID
```

Rerun the same generation command to resume. `--limit` bounds attempts, not total
queue size. Each pending example gets one attempt per invocation; explicit failed
attempts retry on a later invocation. No retry loop incurs unbounded spend.
Validation needs no credentials but still requires matching frozen files.
Exit 0 means all missing IDs have valid machine records; exit 1 means incomplete
coverage or unresolved failures; exit 2 means a gate/configuration/integrity error.
Neither command trains or evaluates anything.

## Separation, resume, and failure behavior

- Only missing entries in the existing training/development annotation queues
  qualify, not the entire source pools. Every human CSV record is protected,
  including stale, partial, or skipped entries. No human labels are written.
- JSONL events live in ignored `data/labels/annotation/machine/<queue>/<run-hash>.jsonl`.
  Every event is `machine_annotated`, with queue/input ID and hash, model ID,
  returned model version if available, timestamp, attempt, prompt/schema/guide/
  taxonomy/queue/pool hashes, and generation settings. Successes hold validated
  decisions; failures hold explicit sanitized codes and no invented label.
- The prompt treats conversation text as untrusted evidence, not instructions.
  Only redacted current text and preceding context with speaker-role markers are
  sent. No historical future replies, golden queues, or golden source files are read.
  Redaction is imperfect; outputs remain private, local, and ignored.
- Resume validates stored provenance, IDs, attempts, decisions, and input hashes.
  A different model, prompt, schema, input pool, or policy creates a different run;
  prior events are retained, never mistaken for current labels. Later human labels
  supersede machine records without deleting history. Human-store changes during
  generation abort the run before saving that response.
- A per-run exclusive lock prevents concurrent writers. After a crash, confirm
  no process is running before manually removing its `.lock`. Malformed/truncated
  JSONL fails closed: preserve it for local inspection, do not silently discard it.
  A crash after an API reply but before persistence may require a repeat call.
- Validation proves structure and provenance, not semantic accuracy or safe replies.
  Machine-labelled development results must be called model agreement, never
  independent human accuracy. These labels cannot satisfy the genuine human golden
  examples or human reply ratings required by the assignment.

The Gemini adapter follows the [official structured-output API documentation](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
and is tested against the installed SDK configuration schema with a fake client.
Tests use synthetic fixtures and fake API outputs only; live credentials, model
availability, costs, and output quality are not validated by those tests.

Verified at this stage: `uv run pytest` passed 57 tests; CLI help and guide status
worked; all 38 protected local files (annotations, review provenance, state,
queues, and split assignments) retained their SHA-256 hashes.
No real machine-output files were created. The key was absent from the process
environment and no local `.env` existed at verification. Approval/freeze, a model
ID, and locally configured credentials are required before a live run.
