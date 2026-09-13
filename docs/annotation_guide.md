# SpotifyCares annotation guide

**Status: proposed — not reviewed or frozen by the project owner.**

- Taxonomy version: `spotify-intents-v0.2-proposed`
- Guide version: `spotify-annotation-v0.2-proposed`
- Source used for discovery: the 400-example training-only discovery sample
- Development and held-out test text used for taxonomy design: no

This guide tells a human annotator how to label one incoming customer message using only that message and its available preceding conversation. It does not tell a future model how confident to be.

## The two independent judgments

First choose one primary intent: the issue that the next useful support reply should address first. Then independently decide whether the case should be auto-handled or escalated under the written policy. An ordinary login how-to can be auto-handled; a suspected takeover with the same account-access intent must be escalated. Likewise, a general plan question is different from an account-specific charge investigation.

`should_escalate` describes the case itself. Do not use model confidence, retrieved examples, or a generated reply to set it. A later agent may escalate additional cases when its own evidence is weak.

## Proposed primary intents

| Label | Use it when |
|---|---|
| `playback_and_audio` | Available audio will not start, stops, skips, repeats, shuffles incorrectly, or sounds wrong. |
| `app_device_technical` | The app, web player, controls, operating system, device integration, or connection is malfunctioning. |
| `account_access_and_profile` | Credentials, login, identity, profile, account linkage, ownership, or account access is central. |
| `plan_and_membership` | Premium, Family, Student, trial, partner membership, invitations, eligibility, conversion, or cancellation steps are central. |
| `billing_and_payment` | A charge, refund, billing date, price, payment method, or transaction outcome is failing or disputed. |
| `library_and_playlists` | Saved items, downloads, personal playlists, queue contents, limits, transfers, or organization are central. |
| `catalog_and_content` | Global content availability, releases, attribution, metadata, credits, or editorial playlist placement is central. |
| `feature_and_market_availability` | A capability, device integration, country launch, unsupported platform, or general product how-to is requested. |
| `other_or_unclear` | The input is social, resolved, unrelated, or remains too vague after its preceding context is read. |

The complete inclusion/exclusion criteria and training example IDs are in `configs/taxonomy.yaml`. Redacted source examples are generated locally at `data/labels/annotation/taxonomy_examples.parquet`; that file is intentionally Git-ignored. The shareable guide does not reproduce customer text.

## Important boundaries

- Current task: label the current unresolved request, not an earlier resolved problem. Restored access followed by missing playlists is `library_and_playlists`; unresolved suspected unauthorized activity requires security escalation. Resolved acknowledgements with no remaining request use `other_or_unclear`.
- History and evidence: past compromise does not prove an ongoing issue or verified present security. Keep history in notes; reserve `security_or_compromise` for a current or unresolved suspected incident supported by the available report. A general security-feature request or fear of future hacking alone does not establish an incident. Clear intent does not mean verified account security.
- Unavailable links: never infer linked contents. If the visible input and context cannot support a specific intent, use `other_or_unclear`; record uncertainty rather than inventing the missing subject.
- Playback versus app/device: choose `playback_and_audio` when the product is available and the problem is what the audio does. Choose `app_device_technical` when a crash, broken client control, device integration, operating system, or connection is the identified failure—even if playback is the visible symptom.
- Plan versus billing: choose `plan_and_membership` for general enrollment, invitation, eligibility, cancellation, or feature steps. Choose `billing_and_payment` when a transaction, charge, refund, payment method, or incorrect price must be investigated.
- Login versus compromise: routine credential or linked-account help is `account_access_and_profile` and may be auto-handled. Suspected takeover, unauthorized change, or identity misuse keeps that intent but adds `security_or_compromise` and requires escalation.
- Library versus catalog: a track missing from one customer's saved collection or playlist is `library_and_playlists`; a track absent, region-blocked, or misattributed for the service is `catalog_and_content`.
- Catalog versus feature availability: a missing release is `catalog_and_content`; an unavailable country, device app, or product capability is `feature_and_market_availability`.
- Multiple issues: do not infer separate problems from ambiguous wording or payment background. Use `multiple_issues_include_human_required` only when distinct issues are established and at least one requires human handling; prefer a more specific supported security, payment, or account-action reason that explains routing.
- Short follow-ups: read preceding messages in displayed order before using `other_or_unclear`. Missing context is not the same as short text with sufficient context.

## Escalation policy

Auto-handle only when the customer message and preceding context support a routine response that does not need private account access, an account-specific action, or an unverified current-policy claim.

Safe clarification counts as a routine response when no supported human-required issue is already present. Asking what happens in the app or whether Premium appears active does not itself require private account investigation. Escalate later if the answer establishes an account-specific action or other human-required issue. Do not use clarification to defer an already-supported security incident or payment investigation. Ambiguous intent and missing diagnostic details alone do not require escalation.

Choose the most specific supported reason. Security incidents and payment investigations take their specific codes; use private-account investigation when account work is required and no more specific code fits.

Set `should_escalate = yes` and choose the best reason when:

- `security_or_account_compromise`: a current or unresolved takeover, unauthorized access/change, or identity misuse is suspected from the available report, not solely from history or fear.
- `private_account_investigation_or_action`: a specific account must be looked up, changed, restored, or verified.
- `refund_or_payment_investigation`: a refund, unknown/duplicate charge, or specific payment dispute needs investigation.
- `materially_insufficient_context`: even a responsible routine next step or safe clarification cannot be chosen from the available information.
- `multiple_issues_include_human_required`: a multi-issue case contains at least one human-required issue.
- `unavailable_current_fact_or_policy`: a responsible answer relies on current facts or policy unavailable to this historical prototype.

Do not escalate simply because the text contains “billing,” “subscription,” or “login.” General instructions can be auto-handled. Add an explanation that cites the evidence in the available case; never place secret or newly discovered personal information in notes.

## Risk flags and ambiguity

Risk flags are multi-select and do not replace intent or escalation: `security_or_compromise`, `payment_dispute`, `personal_data_exposure`, `legal_or_safety_concern`, and `abusive_or_threatening_content`.

- `personal_data_exposure` needs visible disclosure or an explicit report of disclosure/leakage, including redacted evidence of disclosure. Account compromise, unauthorized changes, and mention placeholders alone do not establish exposure. A reported event is not independently confirmed fact.
- Requests for another person's private information are separate privacy-sensitive requests, not evidence that exposure occurred. Record explicit requests in notes and reply guidance, without promising identification or disclosure. An ambiguous request to trace an intruder does not by itself establish a request for private identifying details. No new risk flag is introduced in this version.
- `abusive_or_threatening_content` requires context-supported targeted abuse or threatening content. Abuse may include directed degrading insults or harassment without a credible physical threat. Ordinary anger, emphatic complaints, or rhetorical confrontation alone does not automatically qualify. Interpret context, note uncertain boundaries, and assess credible threats and legal/safety concerns separately.

Mark `ambiguous` when two intents remain plausibly tied, essential context is unclear, language cannot be interpreted confidently, or the primary issue relies on an uncertain inference. Explain the competing interpretations in annotation notes. Ambiguity does not automatically decide escalation; insufficient context does.

## Historical reply protocol

The interface initially shows only information available to the agent. Save the initial intent, escalation, risk, and ambiguity judgments before revealing SpotifyCares' future historical reply. The reply appears in a separate panel and is used mainly to write expected reply guidance.

Historical replies are imperfect. They can ask questions, move the case to private messages, reflect outdated policy, or fail to resolve the issue. They are not guaranteed correct answers. Do not change an initial label merely to agree with one. If the reply reveals a genuine mistake, edit the label and explain it; the tool preserves the before/after record and notes that the reference had already been revealed.

Expected reply guidance should state what a good response needs to accomplish, including a safe next step or clarifying question. Do not copy private details, promise account action, or treat an old link or policy as current.

## Required workflow

1. Read the definitions, exclusions, boundaries, and escalation policy.
2. Start only the `training` queue. Label the first 30 items as the pilot.
3. Record difficult cases as `ambiguous` with a note. Use Skip only when work must pause; skipped items remain incomplete.
4. Review the pilot's ambiguities and recurring boundary problems. Policy revisions change both version strings and hashes, not existing queues or split assignments. Preserve old annotation versions, revisions, and assistance provenance. Old labels are stale under the new contract until individually reviewed; never silently refresh them.
5. Only after final owner approval, freeze the exact current file hashes. By default the command requires a complete/current 30-item pilot. For an explicitly approved policy revision, `--acknowledge-prior-version-pilot` allows a complete prior-version pilot and records its staleness and limited coverage in the freeze audit without relabelling any row. Missing/incomplete pilot records still block freezing. The optional 20-example Coverage review is not a new prerequisite.
6. Only after the freeze, annotate development and golden queues. Never use golden labels to tune the taxonomy, prompts, classifier, thresholds, or retrieval.

Freeze command for the current proposal:

```powershell
uv run spotify-cares freeze-guide `
  --annotator-id YOUR_ID `
  --confirm-taxonomy-version spotify-intents-v0.2-proposed `
  --confirm-guide-version spotify-annotation-v0.2-proposed `
  --acknowledge-prior-version-pilot
```

This writes only local ignored state and unlocks development/golden views. If either tracked file later changes, their hashes will no longer match the freeze. The tool blocks those queues and the validator flags older records as stale for human review; it never silently relabels them.

If later training analysis shows thin coverage, append a named training-only batch without replacing existing queue positions:

```powershell
uv run spotify-cares extend-training-queue --name batch2 --size 100
```

Optionally add an observable proxy such as `--coverage-bucket billing`. Such enrichment is a sampling aid, never a prefilled label or a natural-frequency sample.

## Annotation states

- Tooling ready: code and interface checks pass.
- Queue prepared: deterministic IDs and provenance exist locally.
- Human annotation in progress: at least one label is missing, skipped, judgment-only, or stale.
- Human annotations complete: every expected record is complete under the current frozen versions and hashes.

Stage 4 reaches tooling/queue readiness. It does not claim the human work is complete.

## Coverage and machine-label provenance

The reviewed pilot contains 30 user-entered, partly AI-assisted annotations, not independent human labels. Its last reviewed intent counts were account 19, billing 4, library 2, other 2, catalog 1, app/device 1, feature 1, playback 0, and membership 0. Four cases retain uncertainty. The 20-example Coverage review was 0/20 complete at consolidation; this limitation is disclosed, not a freeze requirement. These counts are not population prevalence or model accuracy.

Machine annotations use a separate JSONL store marked `machine_annotated`, never the human CSV. They may cover only missing training/development queue records after a matching freeze; any existing human record, including stale, skipped, or partial records, is protected. They receive only the current redacted message and preceding context, not future historical replies. Machine-labelled development results measure model agreement, not independent human accuracy. Golden annotation remains human-only. Schema validation establishes structural consistency, not correct labels or independent ratings.
