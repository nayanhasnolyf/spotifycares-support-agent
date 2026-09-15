# Training-only baseline checkpoint

The owner ended annotation tuning. Five held cases stay excluded without another
manual-review prerequisite. The 30 prior-version human records remain unchanged
and are not classifier training data. Annotation completeness is not a gate for
retrieval, drafting interfaces or implementation of the later evaluation harness.

## Actual training selection

The pinned combined manifest is
`3de2c4e48978fd743028104d9bf25b0fd4a6d463fef77a7b3128beea4ec8591b`.
Its 16 eligible machine labels contain:

| Intent | Count |
|---|---:|
| billing_and_payment | 13 |
| library_and_playlists | 2 |
| playback_and_audio | 1 |

All six other frozen intents have **zero** examples: account access/profile,
app/device technical, catalog/content, feature/market availability, other/unclear,
and plan/membership. Logistic Regression fits three classes, but cannot predict
the absent classes. The billing-heavy majority baseline always predicts billing.
No training accuracy or cross-validation score was computed. Successful fitting
and CLI execution do not demonstrate useful model quality.

Every selected label is `machine_annotated`, not an independent human judgment:

| Source | Selected | Run hash prefix | Prompt/schema |
|---|---:|---|---|
| Gemini gemini-2.5-flash | 11 | 7ca82b285845 | original full schema; temperature 0; max output 2048 |
| Groq openai/gpt-oss-20b | 2 | 639b2f0ab749 | v2 compact/full schema; temperature 0; low reasoning; max output 1024 |
| Groq openai/gpt-oss-20b | 3 | a056fc3bd6b9 | v3 classification-only; same Groq generation settings |

Policy versions remain `spotify-intents-v0.2-proposed` and
`spotify-annotation-v0.2-proposed`, frozen despite their historical names.
Taxonomy SHA-256: `15809663951befd9688aae18c301d85f159d3d95d22e153ce754f949b9b7a688`.
Guide SHA-256: `3cc6c56f8b954e12000eeec501d1bdd4b1f1a6a123a53aa10faf7868e27016c3`.
`baseline-inspect` prints full run/prompt/schema/policy hashes and generation
settings directly from selected records. The loader verifies current manifest,
record and input hashes and rejects unknown intents, duplicate IDs and held/human
IDs. It never changes label eligibility to obtain more training data.

## Implementation and reproduction

```powershell
uv sync --extra dev
uv run spotify-cares baseline-inspect
uv run spotify-cares baseline-demo --baseline trivial --message "Music stops when I try to listen. What can I try?"
uv run spotify-cares baseline-demo --baseline tfidf --message "Music stops when I try to listen. What can I try?"
uv run pytest tests/test_baselines.py
```

The quoted message is illustrative command input, not a dataset record, annotation
or evaluation example. Both demos ran locally. Both predicted billing/payment;
the trivial baseline returned its fixed acknowledgement and escalated, while
TF-IDF returned a safe clarification with retrieved evidence IDs. This result is
reported as execution behavior, not scored, tuned against, or advertised as accuracy.
Optional `--context` arguments supply preceding context in order. Optional
`--output artifacts/baselines/new-name.jsonl` records local output and provenance;
existing files are never overwritten. No API credentials are needed for baselines.

The trivial baseline is the most-common eligible intent (lexical tie-break), a
fixed acknowledgement, and unconditional escalation. Its escalation is explicitly
not a fabricated case-policy reason.

TF-IDF + Logistic Regression fits vocabulary/IDF and classifier on **only the 16
selected inputs and their preceding contexts**. It never fits on historical
answers or the larger retrieval corpus. Defaults in `configs/baselines.yaml` are
word unigrams/bigrams, at most 30,000 features, sublinear TF, C=1, 1,000 iterations,
seed 42; none was chosen using development/golden results. Fewer than two classes
produces a specific fitting blocker; empty vocabulary/non-convergence is surfaced.
Models are rebuilt in memory per invocation rather than loading unsafe pickles.
The current fitted classifier has 505 features. Verification: 130 tests passed,
including 20 baseline-specific synthetic checks covering leakage, exclusions,
unknown classes, fitting blockers, empty retrieval and unsafe copied actions.
Compilation, CLI help and staged checks passed. All 67 existing annotation files
remain byte-for-byte unchanged.

The independent retrieval index uses all **27,455 eligible training historical
conversations**, including unlabeled inputs. Historical examples underlying held
or stale annotations can remain in this unlabeled corpus; their annotations are
never used. The loader checks the Stage 3 corpus/input fingerprints and verifies
every retrieval ID, thread and combined group against the training input pool.
Only redacted columns are loaded. Separate TF-IDF vocabulary/IDF is fit to training
customer inputs/preceding context, never reference replies. Retrieval uses sparse
cosine similarity, returns at most three positive-overlap hits, and resolves ties
by stable ID. The package interface supports self-ID and group exclusions for
future evaluations. No development/golden files are required or opened.

## Reply safety and explicit routing

Historical output is a **safe projection**, not a verbatim quote or a verified
resolution. A narrow allowlist can project a reversible restart instruction.
Account/action/payment/credential claims suppress the historical snippet; links,
signatures and arbitrary prose are never copied. Withheld snippets remain empty
with an explicit status. Evidence includes historical reply IDs and example IDs.
If no safe step is available, the draft asks a clarification instead of inventing
a fix. This conservative filter sacrifices usefulness; it is not general-purpose
PII anonymization or a guarantee that a retrieved conversation is relevant.

`PolicySignals` and `route_policy` implement the frozen reason codes independently
of predicted intent and retrieved replies: security/payment reasons take priority
over general account work; safe clarification is allowed when no human-required
signal is established. The demo's `detect_signals` adapter is deliberately narrow
regex logic, **not complete semantic enforcement**. It can miss incidents and
mishandle negation, time references, or multiple issues; no policy-compliance rate
has been established. The structured interface supports all six reason codes for
later richer evidence extraction without changing the policy. Empty retrieval
adds a separate conservative agent fallback, not a fabricated case-policy label.
Escalation drafts request private support without claiming a ticket, refund,
transaction check, account change or completed support action.

## One future coverage option — not executed

Groq lists `openai/gpt-oss-120b` and documents strict structured outputs for it:
[model catalog](https://console.groq.com/docs/models),
[structured-output support](https://console.groq.com/docs/structured-outputs).
An authenticated read-only model-list check in this stage confirmed it is listed
for the local credentials. Its exact schema execution and account generation
limits remain unverified; published limits are not this account's limits.

A concrete future option is to use that model, in a separate provenance-bound run,
to label a fixed, training-only sample spanning the six currently missing intent
areas (sampling proxies are not verified labels). Keep the five held cases and
all human records excluded, validate outputs and coverage, and select usable
records explicitly. A larger model is not assumed more accurate. No model switch,
generation experiment, quota workaround or billing change was performed here.

## Remaining evaluation requirements

Implementing retrieval/drafting/evaluation code need not wait for complete labels.
However, honest accuracy still needs independent labels: human-reviewed development
data (machine-labelled development would measure model agreement only), 150–250
genuinely hand-labelled golden examples (target 200), human reply ratings, and an
LLM judge validated against those ratings. No baseline accuracy, routing metrics,
reply-quality scores or under-15-minute headline evaluation result exists yet.
The system/prompt/retrieval configuration must be frozen before one-shot golden
evaluation; the current policy freeze is not a system/results freeze. Five failure
modes and misleading-headline analysis must ultimately be backed by evaluation,
not replaced with these software tests or illustrative demos.
