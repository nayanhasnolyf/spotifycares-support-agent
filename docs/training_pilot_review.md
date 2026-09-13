# Training pilot review — pending owner decisions

Historical snapshot below: its original counts and proposals are retained for audit,
not presented as current annotations. The flagged-case decisions have now been
reviewed with the owner and recorded locally with AI-assistance provenance.
The active v0.2 guide supersedes the original proposals, particularly item 3:
privacy-sensitive requests are not exposure events. The owner has also explicitly
removed completion of the 20-example coverage sample as a freeze prerequisite.
See `docs/annotation_guide.md` and `docs/machine_annotation.md` for the current
contract, limited coverage, and final approval steps. No freeze has been performed.

Review date: 2026-09-11. This is an assistant review of the 30 completed training-pilot annotations, not an independent human adjudication. No proposed changes below have been applied to the annotation guide, taxonomy, labels, or queues.

## Scope and provenance

Only the completed training records at positions 1–30 and their redacted incoming messages and preceding context were reviewed. Historical future replies were not used to resolve intent or escalation disagreements. Audit metadata for these same records was checked for edits after reference reveal. No development or golden messages were inspected. Other training-queue metadata was used only to propose additional review positions; their text was not inspected.

The owner reports that some annotations were made with ChatGPT assistance. Treat this pilot as user-entered annotations with mixed/partly ChatGPT-assisted provenance, with the affected rows and extent of assistance unspecified. Do not count it as independently human-labelled data or as independent human agreement with an LLM. Do not infer the assisted subset from wording, repeated guidance, or timestamps. Preserve the existing judgments. A local provenance declaration ties this statement to the reviewed CSV fingerprint without editing its rows.

The recorded annotator ID has two casing variants (29 records in uppercase and one title-case record). This is an identity-normalization issue to confirm with the owner, not evidence of two independent annotators.

## Observed counts

| Primary intent | Count |
|---|---:|
| account_access_and_profile | 20 |
| billing_and_payment | 4 |
| library_and_playlists | 2 |
| catalog_and_content | 1 |
| playback_and_audio | 1 |
| feature_and_market_availability | 1 |
| app_device_technical | 1 |
| plan_and_membership | 0 |
| other_or_unclear | 0 |
| Total | 30 |

Escalation: 27 yes (90%), 3 no (10%). Reasons: 19 security, 4 refund/payment investigation, 2 private-account investigation/action, 1 unavailable current fact/policy, and 1 multiple issues requiring a human. Three non-escalations have no reason code.

Ambiguity: 3 ambiguous, 27 clear. Risk flags (multiple may occur per record): 21 security/compromise, 9 personal-data exposure, 4 payment dispute, and no legal/safety or abusive/threatening flags. All 30 records have a reference-reveal marker. The audit contains one event changing a risk flag after reference reveal; it is preserved, not counted as independent agreement.

The existing training store accepts all 30 records, and the pilot checker reports 30 complete/current with zero missing, incomplete, or stale. This validates fields and versions, not the correctness or independence of the judgments.

## Coverage finding

The pilot comprises 27 security-proxy selections (90%) and 3 billing-proxy selections. This is an implementation sampling-order issue: the training sampler appends coverage buckets consecutively, with security first, while the guide calls the first 30 records the pilot. The broader 300-record queue is enriched across topics, but its first 30 are not balanced.

Proxy flags are not confirmed labels: 21 records carry a human-entered security flag, and 19 use security as their escalation reason. Some security-proxy matches are unrelated to account compromise. Even so, the pilot strongly emphasizes security and escalation. It has no primary plan or other/unclear examples, no meaningful coverage of routine login, and only one playback and one app/device label. It is insufficient to assess the remaining boundaries. Do not report these counts as population prevalence or model performance.

## Review findings requiring human decisions

- Two cases describing restored access followed by missing playlists receive different primary intents. The current guide lacks a clear rule for resolved security history versus the next active task.
- One resolved playback/security follow-up is labelled playback, although the guide also assigns resolved acknowledgements to other/unclear. Its non-escalation is defensible if a routine acknowledgement is sufficient and it makes no account-security claim.
- Two explicit compromise cases use the broad private-account reason rather than the more specific security reason. Both decisions escalate; this is reason-code consistency, not evidence of unsafe automatic handling.
- One playlist-recovery case has a security reason but no security risk flag, while its explanation refers to restoration. Review whether the security issue is still active before choosing which field, if any, needs revision.
- Eight personal-data-exposure flags are not directly supported by visible disclosure or explicit data-leak evidence in the reviewed input. Account takeover can create exposure risk, but the current guide does not define whether that possibility alone qualifies. One additional flagged case does explicitly reference personal contact details in redacted form.
- The three marked ambiguous cases concern an unspecified limit/feature discussion, a security-feature request that might allude to compromise, and an app failure after subscription payment. Their notes should be adjudicated before freezing. A vague paid-app failure does not itself establish multiple separate issues requiring account action.
- One expected-reply guidance entry assumes a second reported problem that is absent from the visible input. Review copied guidance against each case. Another mentions password blame without a password discussion; that caution is harmless but unnecessarily generic.
- A hostile billing message has no abusive/threatening flag. This is a boundary-review candidate because the current guide lists the flag without defining casual profanity, hostility, and credible threats separately.

Detailed case positions and IDs are in the ignored local review file. These findings are assistant suggestions, not corrected labels or an error-rate estimate.

## Specific proposed guide additions — not yet adopted

1. **Current task versus resolved history:** “Label the next unresolved customer request. If access is explicitly restored and only playlists remain missing, prefer library_and_playlists. If unauthorized activity continues, prioritize account_access_and_profile and security escalation. A resolution/thanks message with no remaining request uses other_or_unclear. Earlier security history does not establish verified present security.”
2. **Reason specificity:** “For suspected active compromise, prefer security_or_account_compromise over private_account_investigation_or_action. Use the broad reason when account work is required but no more specific reason fits. Use multiple_issues_include_human_required only when distinct issues are established and at least one requires a human; state which one.”
3. **Risk evidence:** “Use personal_data_exposure for visible disclosure (including redacted personal-data placeholders), explicit reported leakage, or a request to disclose private information. Do not add it solely because account compromise is suspected; capture that with security_or_compromise. Explain any uncertainty.”
4. **Feature requests and clarifying questions:** “A general security-feature request without evidence of an incident may receive a routine acknowledgement or clarifying question without escalation. Explicit or context-supported suspected unauthorized access requires escalation. A safe clarifying question can be routine; use materially_insufficient_context when even a responsible routine next step cannot be chosen.”
5. **Missing links and provisional intents:** “Do not infer the contents of inaccessible links. If the visible input cannot distinguish a library limit from a product-feature discussion, use other_or_unclear with ambiguity and record the competing interpretations. A paid-app complaint alone does not prove payment failure or multiple independent issues.”
6. **Case-specific guidance and tone flags:** “Ground guidance in the visible message/context; do not assume additional symptoms from a reused template. Flag explicit abusive or threatening wording and distinguish it in notes from casual frustration; assess credible safety concerns separately.”
7. **Provenance and calibration:** “Record assistance per record when known; otherwise attach a scoped provenance declaration with the unknown subset stated. Pilot completion is a coverage/adjudication checkpoint as well as a record-count check. Include routine and escalation cases across the observed intent boundaries before freezing.”

If accepted, adopt these through a versioned guide/taxonomy revision and review affected stale annotations explicitly. Until then, the current versions and hashes remain unchanged. The freeze command's count check can pass even though coverage and adjudication remain insufficient; it cannot establish human approval or annotation independence.

## Proposed additional review: 20 existing training records

Use the next two uncompleted records in each of the ten named non-security coverage buckets (excluding the remainder bucket). This is a metadata-only proposal, with no new text reviewed, no labels inferred, no queue appended, and no records replaced.

| Existing training positions | Sampling proxy |
|---|---|
| 31, 32 | billing |
| 55, 56 | membership |
| 82, 83 | account |
| 109, 110 | catalog |
| 136, 137 | library_playlist |
| 163, 164 | playback |
| 190, 191 | app_device |
| 217, 218 | feature_market |
| 244, 245 | short_or_context_limited |
| 271, 272 | general |

These proxies cannot guarantee final intent coverage or routine cases. After the owner labels this small sample, check the actual labels and unresolved boundaries again. Retain all original 30 records and their audit history.

Recommendation: keep the guide proposed, review the flagged cases and proposed wording, and complete this additional sample before considering freeze. No freeze, classifier training, prediction generation, or scoring was performed.
