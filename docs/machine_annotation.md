# Policy approval and machine annotation

## Classification-only bounded experiment

The owner authorized one experiment containing three previously held training
cases and five new training cases. The new IDs were selected before viewing
their messages or outputs, using the lowest SHA-256 values of
`classification-v1-new-training:` plus each eligible ID, excluding every human
record and every previously attempted machine ID. The ignored selection file
pins all eight IDs, the run hash and `one_attempt_per_example: true`.

Prompt `spotify-machine-v3-classification` requests only intent, escalation,
reason code, ambiguity and a short evidence-based rationale. Machine storage
allows optional guidance but generation does not request it. Older full-schema
records remain readable, and omitted risk flags are not negative risk labels.
The frozen taxonomy and guide are unchanged. The model remains
`openai/gpt-oss-20b`, temperature 0, low reasoning, 1,024 maximum output tokens.
Reservations still expire after 60 seconds without speculative token refunds.

The previous Gemini run remains retained. The prior Groq v2 run is now explicitly
retained under its original prompt/profile/schema/settings, with its three held
records excluded. New attempts record explicit supersession of held originals;
they never overwrite those originals. New run:
`a056fc3bd6b9fcc929a3d7d57f410b1f681017716a91c8b91168b0b45bd1cb45`.

The bounded resume command cannot expand beyond the pinned IDs or retry an
already attempted ID. It is not authorization for bulk generation:

```powershell
uv run --env-file .env spotify-cares machine-annotate --queue training --provider groq --selection data/labels/annotation/machine/reviews/classification_v1_selection.json --limit 8
```

### Actual eight-case result

- All eight responses passed the five-field schema and ended with `stop`; zero
  API failures, automatic retries, duplicate attempts or unfinished selected IDs.
- Regression checks: all three still held. Paid entitlement was again assigned
  account-access/credential reasoning; unclear financial wording was marked clear;
  payment receipt wording was again rewritten as duplicate charges. The shorter
  output removed reply-action promises but did not fix these semantic failures.
- Five new cases, assessed separately: three provisionally eligible (playback
  failure, disappearing downloads, accidental library removal); two held (an
  existing sharing-feature regression labelled feature availability, and an
  ambiguous platform complaint asserted to mean unavailable integration).
- These findings are AI-assisted inspection, not independent human ratings or
  measured annotation accuracy. The three provisional labels are not certified
  correct; in particular, a recovery request does not establish an automatic
  recovery capability or exclude later human handling.
- Actual provider usage: 27,486 input + 1,348 completion = **28,834 tokens**.
  Input reservations ranged from 4,482 to 4,672 tokens; with 1,024 output tokens
  each, total reservations were 44,441. Each request fits the observed 8,000-TPM
  limit; two concurrent reservations do not. Resumes respected the rolling window.
  Reservations were not refunded from observed usage. RPM 5 remains an operator
  ceiling, not a verified account RPM allowance.
- Final combined selection: **16 labels (11 Gemini + 5 Groq)**, 30 protected stale
  human records, 249 unattempted, 5 held, **254 remaining**. The active run has
  eight schema successes but only three usable selections. Development is still
  0/80 and was not generated or semantically inspected in this experiment.

The eight-case experiment is finished, not the full queue. Consequently the CLI
reports `complete: false` and exit code 1 without implying an API/schema failure.
An actual-data resume using a provider that raises on any invocation made zero
calls and left response/ledger bytes unchanged. The original ledger prefix and
all 53 other original non-registry/non-ledger annotation artifacts are unchanged;
the exclusion registry preserves previous entries and adds five current holds.
Human labels, older model outputs, splits and frozen policy remain unchanged.

**Stop here:** repeated errors persist. Keep the five uncertain records explicitly
excluded and request targeted human review. Do not repeat prompt experiments,
switch models or run bulk annotation without a new authorized step. Detailed
input/output comparisons and the pinned selection are in ignored local review
files. The final combined manifest is
`3de2c4e48978fd743028104d9bf25b0fd4a6d463fef77a7b3128beea4ec8591b`.

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

## Revised bounded smoke test

This checkpoint supersedes the incomplete smoke above. The frozen taxonomy and
guide hashes, human annotations, Gemini outputs, split assignments and golden data
were preserved. Only five pinned training examples were requested; no development
generation, bulk generation, classifier training or evaluation occurred.

### Token diagnosis and changes

The old request estimated 7,036 input tokens and reserved a maximum 2,048 output
tokens: 9,084 total, above the observed 8,000 TPM ceiling even in an empty window.
Its minute reservation had expired before this follow-up. Waiting alone could not
solve that single-request check. Actual usage from the old response was discarded;
neither the remaining-token header nor tokenizing its stored decision can recover
the provider's prompt/completion/reasoning usage. It remains unknown.

The versioned `configs/machine_annotation_prompt_v2.txt` and `compact-v1` renderer
retain all intent inclusion/exclusion rules, tie-breakers, flags, and escalation
definitions, plus the guide's distinct judgment, ambiguity, escalation and reply
constraints. They omit example IDs, repeated descriptions and human/UI workflow
instructions. No customer/context text is shortened; no frozen policy file changes.
The eight output fields remain required; notes and guidance are requested concisely.

`annotation.groq_max_completion_tokens: 1024` is now configurable and recorded in
run provenance. The model remains `openai/gpt-oss-20b`. Five input reservations were
4,537–4,553 tokens, plus 1,024 output: 5,561–5,577 per request. This fits individually,
but two such reservations exceed 8,000 within a minute. The runner paused between
cases and resumed after expiry instead of bypassing its limiter. The 5-RPM setting
is an operator ceiling, not a newly verified account allowance.

Minute reservations expire at 60 seconds; conservative daily accounting is rolling
24 hours. Every attempted retry reserves again. Tests cover both expiry boundaries,
two failed reservations, and an actual fake-HTTP retry through the adapter. Actual
usage is now recorded in label provenance controls and ledger responses, including
reasoning tokens when supplied. Absent usage remains null, not invented. We do not
refund unused completion reservations merely because billed usage is smaller:
[Groq's rate-limit documentation](https://console.groq.com/docs/rate-limits) does
not establish that such a refund is safe for this accounting scheme.

### Actual bounded result and semantic review

All five distinct IDs returned complete (`finish_reason: stop`), schema-valid
responses. No API failures or live retries occurred. Actual provider-reported usage:

| Measure | Tokens |
|---|---:|
| Prompt | 17,266 |
| Completion | 1,066 |
| Total | 18,332 |
| Reasoning, already included in completion | 388 |

Completion sizes ranged from 160 to 276 tokens, including reasoning; all fit the
1,024 cap. This is smoke-test usage and format evidence, not annotation accuracy.

The original problematic output classified an entitlement issue as account access
without credential/profile/access evidence, contradicting the taxonomy's explicit
account exclusions and paid-entitlement membership inclusion. It also offered
account review while choosing no escalation; the guide permits customer-side safe
clarification but not an assistant promise of private investigation. The revised
response fixes that guidance offer but repeats the unsupported intent.

AI-assisted inspection found two other unresolved records: ambiguous payment
wording was presented as definite evidence, and one response also offered checking
transactions/opening a ticket rather than a bounded human handoff. Those records
are excluded, not silently corrected. Two other responses have no blocking issue
identified by this inspection; they are not independently human-approved. Detailed
evidence and cautions stay local at `machine/reviews/groq_smoke_v2_review.json`.
The recurring intent/ambiguity/action-boundary problems mean **not ready for bulk**.

### Eligible runs, exclusions, and supersession

- Retained Gemini run `7ca82b285845f6cfdbf6f4dffc4a89d083bb0101959997718f602c45bf28fb4e`:
  11 successes selected under its original prompt and frozen-policy provenance.
- Old Groq run `c34713655e61fb0b06836a6724f2dd9834e3d8303bad1c188fdd4b0fd5fd7eea`:
  explicitly excluded from usable selection; original response untouched.
- Revised Groq run `639b2f0ab7493e927ce4dcc0bf125f6a48704e181ce4908fe4a398df29aeb659`:
  five saved responses, three held by the ignored record-exclusion registry and two
  eligible for the combined machine-label manifest. Eligibility is not accuracy.

The registry path is configured by `machine_record_exclusions_path`; missing or
invalid configured registries fail closed. Old snapshots are historical and must
not be used to bypass current exclusions. New combined manifests embed the current
exclusions and old-source fingerprints. The revised flagged response explicitly
links to the excluded original through `supersedes`. Neither record is relabelled.
Retained sources now pin their own prompt paths rather than inheriting the active
prompt. Any future change must preserve/review source eligibility explicitly.

Current training selection: 13 machine labels (11 Gemini + 2 Groq), 254 unattempted
and 3 held IDs; all 30 human records remain stale and protected. Development: 0/80.
No independent human ratings were created, and machine-labelled development would
still measure model agreement rather than independent human accuracy.

The selection file pins exactly the flagged training ID and four following eligible
queue IDs, plus this run hash. A network-disabled resume skipped all five stored
successes—including held records—without creating duplicates or mutating the
ledger. A held success is not automatically retried under the same run; a reviewed
new run is required. The smoke is complete; **do not generate more now**.

Read-only next command:

```powershell
uv run spotify-cares validate-machine-annotations --queue training --provider groq
```

For reproducing the no-op resume check only (not selecting five new examples):

```powershell
uv run --env-file .env spotify-cares machine-annotate --queue training --provider groq --selection data/labels/annotation/machine/reviews/groq_smoke_v2_selection.json --limit 5
```

Verification: 106 tests passed, including 24 Groq/mixed-provider tests. CLI help,
compilation and whitespace checks passed. The five requests reserved 27,844 tokens
in total across separate windows; actual usage was 18,332, with no speculative
credit returned. Starts were 84.68, 139.69, 66.86 and 98.90 seconds apart. All 43
pre-existing non-ledger artifacts are unchanged, and the ledger's original prefix
is preserved. Frozen policy hashes still match; all 30 human labels remain stale.
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
