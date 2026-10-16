# Development-only intent taxonomy proposal (#2)

**Status: candidate for maintainer review; no taxonomy, annotation guide, labels,
prompts, thresholds, or routing code changed.** Reviewed on 2026-10-16.

## Recommendation

Propose a development-only comparison of merging `playback_and_audio` and
`app_device_technical` into one primary intent, `technical_troubleshooting`.
Keep the other seven primary intents unchanged. Retain observable distinctions
as optional review attributes, such as `playback_symptom` and
`explicit_app_or_device_fault`, rather than requiring an inferred root cause
to choose a primary intent. These attributes are proposals, not new annotations.

The checked-in taxonomy is `spotify-intents-v0.2-proposed`, not the older label
names in the issue description. It already combines playback/audio and several
app/device/connectivity problems. This proposal concerns the remaining boundary
between those two current classes; it does not propose those existing merges again.

The reason to consider a further merge is that the next useful support step can
be technical clarification in either class, while a playback symptom alone may
not establish its cause. The trade-off is lost technical specificity: the first
case below has a clear device-control problem. Preserve that evidence and compare
the candidate with the existing boundary rule before adopting a new version.
This small review does not justify additional primary-intent splits.

## Evidence: four development conversations

Only the incoming customer message and its available preceding context were
used. Excerpts are shortened from redacted text; no future reply was used to
infer a diagnosis or successful resolution. Interpretations below are review
judgments, not independent human labels or measured model errors.

| Development position / example ID | Conversation ID | Short excerpt | Boundary observation and next step |
| --- | --- | --- | --- |
| 11 / `example_498f599ee1f7612c` | `thread_870541aac5f93984` | “don't adjust the Chromecast volume” | The incoming message explicitly describes Android casting volume controls failing inside and outside the app. The current guide supports `app_device_technical`. A merged primary class must retain this explicit integration evidence for device-specific diagnostics. No preceding context is available. |
| 27 / `example_f7376fb671ededcc` | `thread_850f21187e7d61e7` | “27 minutes into a 30 second” | The customer reports a stuck advertisement and an unsuccessful cookie-clearing attempt. This is a playback symptom with a possible client issue, not proof of a broken app or a browser diagnosis. Ask for the client/device and reproduction details rather than infer the cause from the attempted fix. No preceding context is available. |
| 41 / `example_52823ff13e5ff62e` | `thread_f5b5efb92cc61f9c` | “notifications still stop my music” (preceding customer message) | Earlier customer context links notifications and an iOS beta to interrupted music requiring the app to be reopened. The current message reports that disabling notification sounds did not resolve the interruptions. Both playback and client-interaction evidence are present; the explicit interaction supports the current app/device rule. Preserve both facts for technical triage. |
| 77 / `example_b21a74e5afa5fca6` | `thread_768ef364e2250542` | “no longer automatically switches song” | The customer mentions the app, but the reported fault is failure to advance tracks. Without a crash, broken control, or identified integration fault, the current guide supports `playback_and_audio`; the word app alone is not a diagnosis. Clarify queue/reproduction details. No preceding context is available. |

Cases 11 and 77 are useful contrast cases; they do not demonstrate annotator
disagreement. Cases 27 and 41 motivate reviewing symptom-versus-cause boundaries.
Together they support investigating a shared triage class, not claiming that a
merge has already improved classification.

## Routing and migration impact

- A candidate merged label should select technical troubleshooting material;
  the optional attributes should preserve playback versus device/control detail.
  Do not infer a backend fault or recommend an account-specific action from the
  primary label alone.
- Keep escalation independent of intent. Current security, private-account,
  payment-investigation, and other human-required signals still override routine
  technical handling. A merged class must not turn a security case into an
  automatic troubleshooting reply. See the [current guide](annotation_guide.md).
- Leave account, plan, and billing intents separate in this proposal. Shared
  account vocabulary is not evidence that credential help, enrollment, and a
  disputed transaction have the same safe next action.
- If accepted for a trial, use a separately versioned development mapping and
  retrieval/routing configuration. Keep original labels and provenance intact;
  do not rewrite frozen annotations or silently aggregate old evaluation reports.

## What would justify adoption?

Have independent reviewers label development inputs under the existing policy
before comparing the candidate mapping. Record disagreements and the next useful
action, including the four contrast/overlap cases above. Compare agreement,
triage correctness, and loss of device-specific retrieval detail. Retaining the
current labels with clearer boundary examples is a valid alternative if it
preserves useful distinctions without causing disagreements.

No independent development labels were available in this checkout, so there is
**no empirical confusion matrix or accuracy claim** here. Fewer classes can
mechanically raise apparent accuracy; that alone is not evidence of better
support. Any later model comparison must report generation fallback alongside
accuracy/precision/recall and use development data only. No model inference or
provider requests were used for this review; fallback rate is not applicable.

## Reproduction and scope

The unmodified extraction/preprocessing pipeline at commit
`54f39ea89f3ddc63352fc25e536695cd326b1995` produced 41,339 eligible examples and
5,198 development inputs; all nine split leakage checks passed. The review used
the configured seed 42 and `sample_uniform_queue(..., queue_name="development",
size=80, ...)`, the same development sampler used by `prepare-annotations`.
Only that queue was reconstructed for review; no guide freeze was fabricated
and no real golden labels were loaded, created, or edited.

After supplying the original CSV, run:

```bash
uv run spotify-cares extract
uv run spotify-cares preprocess
uv run spotify-cares validate-splits
```

Reconstruct just the development selection in Python:

```python
from pathlib import Path
import hashlib
import pandas as pd
from spotify_cares.annotation import sample_uniform_queue

path = Path("data/processed/splits/development_inputs.parquet")
pool = pd.read_parquet(path)
queue = sample_uniform_queue(
    pool, queue_name="development", size=80, seed=42,
    pool_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
)
selected = queue.merge(pool, on=["example_id", "thread_id", "combined_group_id"])
# Inspect only selected customer_text_redacted and context_texts_redacted locally.
```

Source CSV SHA-256:
`cd297fcfa1bf6f99938be242e8e578980bc6d1b96adc8691abec9a39175b03c0`.
The four IDs and positions above were verified against this reconstructed queue.
Raw data, complete redacted messages/context, queues, and generated artifacts
remain local and Git-ignored. Manual excerpt review also removed the need to
publish names that automated context redaction can miss.

## Attribution and assistance

Source: *Customer Support on Twitter*, Thought Vector / Stuart Axelbrooke,
[Kaggle dataset, version 10](https://www.kaggle.com/datasets/thoughtvector/customer-support-on-twitter/versions/10).
This proposal and its adapted excerpts are provided under
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
Excerpts were shortened from the repository's normalized/redacted development
inputs; surrounding observations are paraphrased. No endorsement is implied.

OpenAI Codex assisted with rebuilding the data, reviewing the selected examples,
drafting this proposal, and verification. This is not independent human
annotation or approval to change the frozen policy.
