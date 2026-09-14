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
Account-specific model access and schema acceptance have since been exercised by
the live smoke test and continuation below; rate/quota capacity remains a blocker.
`--model` is an optional explicit override of project configuration.
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
queue size. The limit counts all API attempts, including bounded retries. Provider
errors stop the invocation except for identified temporary 429s handled by the
bounded scheduler below. HTTP 400/401/403/404/405/410/422
failures are recorded and block automatic retries even on rerun; correct the
configuration and inspect the local run before explicit recovery. Unknown 429s
require an explicit quota-availability check before a retry. SDK retries are disabled.
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

## Historical preparation blocker (superseded by live continuation below)

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

## Latest live continuation: incomplete after HTTP 429

The owner's five training smoke-test successes were verified from actual stored
JSONL, not inferred from the reported counts. All five match the current run's
frozen contract, input fingerprints, model, prompt, and schema. Their IDs were
absent from the 265 pending IDs selected by the existing resume logic.

After inspecting CLI help, the full-run command was:

```powershell
uv run --env-file .env spotify-cares machine-annotate --queue training
```

It saved six new successes and one failed attempt, then stopped on HTTP 429.
The saved error identifies rate/quota limiting but does not identify which limit
or its reset time. No immediate retry or development API request was made after
the error. There was no policy/prompt/model change and no fabricated response.

| Queue | Validated successes | Unresolved failures | Human records protected | Not attempted | Remaining labels |
|---|---:|---:|---:|---:|---:|
| Training | 11 | 1 | 30 | 258 | 259 |
| Development | 0 | 0 | 0 | 80 | 80 |

Both output validators returned incomplete (exit 1), not a completed generation
stage. All 12 training events are `machine_annotated`. The original five-record
byte prefix is unchanged and each original ID occurs exactly once. All 39
protected local artifact hashes are unchanged, including all human annotation
and assistance history, freeze state, golden queue, and split assignments. The
30 prior-version human annotations still report stale. The machine-workflow
test module passed 26 tests using synthetic fixtures and fake providers only.
Schema/provenance validation does not establish semantic accuracy. No classifier
training or evaluation occurred; future development comparisons remain model
agreement, not independent human accuracy.

After resolving the rate/quota limit, see the diagnostic continuation below for
the explicit acknowledgement required for the old unknown 429; do not blindly rerun.
Resume training with that command;
it will skip the 11 successes and retry the failed example. Then run development
and validate both queues:

```powershell
uv run --env-file .env spotify-cares machine-annotate --queue development
uv run spotify-cares validate-machine-annotations --queue training
uv run spotify-cares validate-machine-annotations --queue development
```

Do not repeatedly rerun against an unresolved limit. Generated JSONL and the
credential file stay local and Git-ignored; no golden messages were read.

## Saved 429 diagnosis and bounded scheduling

The original failed event contains HTTP 429, `provider_error`, timestamp, input ID,
and provenance, but no error body, quota metric/ID, retry delay, or response headers.
The old runner discarded those details. Consequently the saved evidence cannot
distinguish request-per-minute, token, daily, or billing limits, and cannot establish
that any retry interval has elapsed. No new API requests were made to diagnose it.
Do not infer billing activation, a quota upgrade, or a reset time from this record.

Check the affected project's active limits and usage through the
[official rate-limit guidance](https://ai.google.dev/gemini-api/docs/rate-limits).
That is a read-only diagnostic step, not an instruction to enable billing, rotate
keys, or switch models. The unknown saved error does not establish a specific
account action beyond checking which limit was reached and whether it is available.
After confirming quota availability, explicitly retry the still-eligible failed
example using the unchanged model/prompt/policy run:

```powershell
uv run --env-file .env spotify-cares machine-annotate --queue training --retry-unknown-quota
```

The flag acknowledges only a saved ambiguous 429. It does not create an automatic
unknown-error retry loop or bypass explicit daily/billing/permanent-error stops.
Once training succeeds, run development without the acknowledgement flag, then
validate both queues. Existing successes remain skipped; no failed example is
marked complete or excluded to bypass a quota error.

Scheduling settings are under `annotation.machine_rate` in `configs/project.yaml`:
15 seconds between request starts (updated after the owner's 5-RPM dashboard), at most two automatic retries per example,
5-second exponential base capped at 30 seconds with up to 1 second of jitter,
30-second maximum individual wait, and 60 seconds total retry-wait budget per run.
These are conservative operational defaults, not inferred project quota values.
Each request records its scheduler settings without changing the run hash or
regenerating existing labels. Changes do not alter the frozen policy, model,
generation settings, prompt, input IDs, or existing output bytes.

Future SDK errors retain only allowlisted quota metric/ID/value, recognized reason
codes, parsed `RetryInfo.retryDelay`, and parsed HTTP `Retry-After`. Arbitrary error
messages, project dimensions, response bodies, and other headers are not logged.
Generic wording about checking billing is not treated as proof of a billing error.
Server-provided delay is a minimum: the scheduler never truncates it to fit a cap.
A long wait is deferred without another request; persisted retry deadlines also
apply on resume. Known daily limits, zero quota, and explicit billing reasons stop
cleanly even if a short retry hint is present. Unknown limits stop for review.
Temporary errors alone receive bounded exponential backoff with jitter.

References: Google's [RetryInfo contract](https://docs.cloud.google.com/storage/docs/reference/rpc/google.rpc#retryinfo)
and [Gemini API errors](https://ai.google.dev/gemini-api/docs/api-errors).
The rate handler and legacy-record compatibility are exercised with synthetic
errors, fake providers, and fake sleeps; no live quota behavior is claimed as tested.
Verification: 82 tests passed. All 40 protected local artifact hashes, including
the complete existing machine JSONL, human records, assistance history, frozen
state, golden queue, and split assignments, are unchanged. Both actual output
validators still report 11/270 training successes and 0/80 development successes
under the same run hashes; this diagnosis did not spend quota or refresh labels.

## Optional Groq and explicit mixed-provider selection

Groq is optional; Gemini remains supported and the default provider. Select
`--provider groq` or set `annotation.machine_provider: groq`. Groq uses
`annotation.groq_model` (`openai/gpt-oss-20b`); Gemini uses `machine_model`.
`--model` explicitly overrides either provider's model. There is no automatic
model/provider fallback. Do not switch defaults or expand generation while the
smoke review below is unresolved.

Configure `GROQ_API_KEY` in the existing ignored project-root `.env`, alongside
`GEMINI_API_KEY`. Never copy the example over an existing credential file, paste
keys into chat, or commit `.env`. Invoke the CLI with `uv run --env-file .env`.

Official sources checked for this implementation:

- [Groq supported models](https://console.groq.com/docs/models) lists GPT-OSS 20B;
  the authenticated `/models` endpoint also listed it for these credentials.
- [Groq structured outputs](https://console.groq.com/docs/structured-outputs)
  supports strict JSON schema for GPT-OSS 20B and 120B. The adapter supplies the
  same taxonomy-constrained Pydantic schema and validates responses locally.
- [Groq rate limits](https://console.groq.com/docs/rate-limits) distinguishes
  organization limits from published examples: request headers mean RPD and token
  headers mean TPM. RPM, TPD, and possible separate input/output caps require
  account evidence; the advertised limits are not assumed to be this account's.
- [GPT-OSS tokenizer source](https://github.com/openai/gpt-oss/blob/main/gpt_oss/tokenizer.py)
  establishes the Harmony tokenizer family used for local reservations.

New v3 runs record provider, requested model, transport/library version, frozen
policy hashes, prompt/schema/input/queue hashes, and actual generation settings.
Groq uses temperature 0, low reasoning effort, a 2,048-token completion cap, no
streaming, and strict JSON schema. Refusals, truncated outputs, invalid fields,
provider failures, and unknown limits never produce substitute labels.

The original v2 Gemini JSONL is not migrated or rewritten. Its provider is
explicitly declared in `annotation.retained_machine_runs`, with its run hash and
model. The combined loader validates its original provenance, input fingerprints,
and decisions, then skips its successful IDs. Its failed ID remained pending and
was the first Groq request. An unchanged failed Gemini event remains in history.

Selection order is explicit: protect every human record, then choose the first
valid configured retained source, then the active run. No glob-based provider
mixing occurs. Each ignored, content-addressed combined manifest pins source file
hashes, record hashes, input IDs, models, provider names, protected human IDs, and
remaining IDs. It contains at most one selected machine label per example. Old
human labels are not adopted or silently upgraded. Schema-valid selection is not
semantic approval or authorization to train.

Run histories stay separate under `data/labels/annotation/machine/<queue>/<hash>.jsonl`;
provider is part of the new run hash. Combined manifests live under
`machine/combined/<queue>/`. To adopt another run after an intentional model/prompt
change, review and configure its source explicitly; don't remove history or
regenerate existing successful IDs to conceal changes. Current retained-source
validation fails closed on policy/prompt/environment drift rather than adopting
incompatible labels. Missing configured local sources also block generation.

### Request and token scheduling

`annotation.groq_rate` has operator RPM/TPM ceilings and optional RPD/TPD and
input/output TPM caps. Current settings use 5 RPM as an operator ceiling, with
8,000 TPM and 1,000 RPD observed in the live response. The account's RPM and TPD
remain unverified. The global machine lock serializes providers and queues.

Groq's ignored append-only budget ledger reserves each request before sending it,
surviving process restarts and spanning training/development. Minute windows count
requests plus token reservations; optional daily ceilings use conservative rolling
24-hour accounting. Token reservation includes the serialized prompt and schema,
local `o200k_harmony` tokens plus 10% and 512 framing tokens, and the maximum
completion budget. This is conservative scheduling, not measured billed usage.
Tokenizer files stay under ignored `.cache/tiktoken`.

Observed headers can lower ceilings, never raise them automatically. Insufficient
remaining allowance honors reset timing; missing reset evidence stops for review.
Identified temporary errors receive bounded backoff/jitter and server minimum
waits; long waits defer. Daily/billing/permanent errors stop without deleting
outputs, and require review before recovery. Do not delete ledger history to
bypass a stop. This scheduler cannot coordinate other clients in the organization,
so concurrent external usage can still trigger an API limit.

### Actual live smoke checkpoint

The owner configured the key locally. Account listing and one live strict-schema
completion succeeded. Response headers showed 8,000 TPM, 1,000 RPD, and 999 remaining
daily requests at that response timestamp, not a guarantee of current availability.
The first request reserved 7,036 input tokens plus 2,048 output tokens (9,084 total).
After learning the 8,000 TPM limit, the next request stopped locally because its
conservative single-request reservation could not fit. There was no Groq HTTP
error and no failed label was fabricated for the unsent request.

The saved result passed schema, enum, input, and frozen-provenance checks. Its
AI-assisted semantic review found two concerns: an account-access intent unsupported
by the visible entitlement issue, and reply guidance offering account review while
choosing no escalation. Safe self-service clarification itself may be allowed;
the review does not establish a replacement human judgment. The detailed finding
is local/ignored at `machine/reviews/groq_smoke_review.json`. No label was edited.

Actual counts: 1/5 Groq smoke responses obtained, zero Groq failed completions;
training has 11 Gemini + 1 Groq schema-valid labels, 30 protected stale human
records, and 258 pending machine labels. Development has zero labels/failures and
80 pending. The old Gemini failure remains recorded, with a structurally valid
Groq output now covering that ID. This is an incomplete smoke test with concerns,
not measured annotation accuracy. No full run, development request, classifier
training, evaluation, or golden access occurred.

The next step is to review these concerns and the per-request token budget. A
smaller output cap or revised prompt must be explicit, with new run provenance
and retained-source handling; it was not silently applied during this test.
Read-only commands now:

```powershell
uv run spotify-cares validate-machine-annotations --queue training --provider groq
uv run spotify-cares validate-machine-annotations --queue development --provider groq
uv run spotify-cares guide-status
```

Commands available for later use, **not authorization to bypass the smoke checkpoint**:

```powershell
uv run --env-file .env spotify-cares check-groq
uv run --env-file .env spotify-cares machine-annotate --queue training --provider groq --limit 5
uv run spotify-cares combine-machine-annotations --queue training --provider groq
# Only after the smoke checkpoint succeeds and account budgets are suitable:
uv run --env-file .env spotify-cares machine-annotate --queue training --provider groq
uv run --env-file .env spotify-cares machine-annotate --queue development --provider groq
```

`--limit` bounds attempts, not guaranteed successes; automatic retries consume it.
Resume excludes retained and active successes and protects every human record.
Machine-labelled development scores would measure model agreement, never independent
human accuracy. The golden set still requires genuine human annotation.

Verification: 99 tests passed, including 17 synthetic Groq/mixed-provider cases;
compilation and whitespace checks passed. Actual validators confirm 12/270
structurally valid machine training labels and 0/80 development labels, so both
remain incomplete. All 39 pre-existing protected annotation artifacts are unchanged.
Frozen taxonomy SHA-256: `15809663951befd9688aae18c301d85f159d3d95d22e153ce754f949b9b7a688`.
Frozen guide SHA-256: `3cc6c56f8b954e12000eeec501d1bdd4b1f1a6a123a53aa10faf7868e27016c3`.
