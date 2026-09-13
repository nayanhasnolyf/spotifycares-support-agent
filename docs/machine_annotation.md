# Policy approval and machine annotation

## Approved and frozen locally

Active versions are `spotify-intents-v0.2-proposed` and
`spotify-annotation-v0.2-proposed`. Read the active guide, then run
`uv run spotify-cares guide-status` to see its exact hashes and matching checkpoint.
The owner subsequently approved and froze these exact versions using annotator
`NAYAN` and `--acknowledge-prior-version-pilot`. The version suffix and guide's
original proposal wording remain unchanged to preserve the approved hashes;
the local freeze manifest, not a rewrite of those files, records approval.

Frozen taxonomy SHA-256: `15809663951befd9688aae18c301d85f159d3d95d22e153ce754f949b9b7a688`.
Frozen guide SHA-256: `3cc6c56f8b954e12000eeec501d1bdd4b1f1a6a123a53aa10faf7868e27016c3`.
All 30 existing annotations remain prior-version records and stale.

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

Executed once after explicit owner approval (do not repeat an existing freeze):

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

`configs/project.yaml` now selects `annotation.machine_model: gemini-2.5-flash`.
The [official model page](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash)
lists this stable model and structured-output support; the [schema documentation](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
documents enums, objects, arrays, nullable fields, and additional-properties rules.
The installed SDK accepts the implemented schema configuration in synthetic tests.
Account-specific model access and actual schema acceptance remain unverified without
credentials. `--model` is an optional explicit override of project configuration.
Configure
`GEMINI_API_KEY` locally in ignored `.env`, never in chat or a command argument.
The CLI does not implicitly load `.env`; uv can load it with `--env-file`.
No live API call or model-quality claim has been verified in this stage.

```powershell
uv run spotify-cares machine-annotate --help
uv run --env-file .env spotify-cares machine-annotate --queue training --limit 5
uv run spotify-cares validate-machine-annotations --queue training
uv run spotify-cares validate-machine-annotations --queue development
```

Rerun the same generation command to resume. `--limit` bounds attempts, not total
queue size. Each pending example gets one attempt per invocation. Provider errors
stop the invocation immediately, preserving successes. HTTP 400/401/403/404/405/410/422
failures are recorded and block automatic retries even on rerun; correct the
configuration and inspect the local run before explicit recovery. Other failed
attempts may retry on a later invocation. SDK retries are disabled.
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
ID, and locally configured credentials were required before a live run.

## Current live-run blocker

Freeze has since succeeded and the model is configured. Credential checks found
no key in the process environment, no user-scope Gemini key, and no existing `.env`.
A new ignored placeholder file was created at
`C:\Users\nayan\OneDrive\Documents\Spotify_Cares\.env`.
Open that file in your editor and set `GEMINI_API_KEY` locally. Never paste it into
chat, put it in a command argument, or stage the file. The CLI loads it only when
uv receives `--env-file .env`.

No API request or five-example smoke test has run yet. Current validation reports
training: 0 generated, 0 failed, 30 protected human records, 270 not attempted;
development: 0 generated, 0 failed, 0 protected records, 80 not attempted.
Empty-output validation is structurally clean but incomplete (exit 1), not a
successful smoke test. Golden data is untouched. No classifier has been trained.
After configuring credentials, run the five-example command above. Inspect and
validate the five actual outputs and resume behavior before expanding
within the already authorized workflow. Only then run the same command without
`--limit` for training and development. Machine-labelled development results must
remain labelled model agreement, never human accuracy.

Preparation verification: 65 synthetic tests passed, including configuration
selection, stop-on-provider-error, permanent-error retry prevention, and preserving
earlier successes. The 37 protected local files outside the intended freeze state
and freeze audit retained identical hashes. Frozen guide/taxonomy hashes match;
the pilot still reports 30 stale, zero current, zero missing/incomplete records.
The five-example live test remains blocked, not passed.
