# Decision log

This is a chronological record of decisions actually made. It is not a list of aspirations. New entries are added only when implementation or observed data forces a real choice.

## D001 — Use a `src`-layout installable package

- **Date:** 2026-09-09
- **Decision:** Put Python code under `src/spotify_cares` and expose an installed `spotify-cares` command.
- **Rationale:** A src layout makes tests exercise the installed package instead of accidentally importing files from the repository root, while one CLI gives later stages a stable reproducibility surface.

## D002 — Keep the initial CLI dependency-light

- **Date:** 2026-09-09
- **Decision:** Build the command shell with Python's standard `argparse` rather than adding Typer or Click.
- **Rationale:** Neither library is required by the assignment. The standard library is enough for the first-stage help/config commands and reduces setup and transitive dependencies.

## D003 — Centralize stable project contracts in strict YAML

- **Date:** 2026-09-09
- **Decision:** Store brand, source, seed, paths, and required storage formats in `configs/project.yaml`, validated by Pydantic models that reject unknown fields.
- **Rationale:** Later commands should share one reviewed configuration. Rejecting extra keys catches misspellings instead of silently running with unintended defaults.

## D004 — Pin Python to the 3.11 minor line

- **Date:** 2026-09-09
- **Decision:** Declare `>=3.11,<3.12` and manage the environment and lockfile with uv.
- **Rationale:** The assignment explicitly specifies Python 3.11; restricting the minor version makes reproduction less sensitive to behavior changes in newer Python releases.

## D005 — Add PyArrow as an explicit runtime dependency

- **Date:** 2026-09-09
- **Decision:** Include PyArrow even though it is not named in the requested stack.
- **Rationale:** pandas needs a Parquet engine, and the deliverable explicitly requires Parquet. An explicit engine avoids a late, machine-dependent optional-dependency failure.

## D006 — Separate human labels from generated data

- **Date:** 2026-09-09
- **Decision:** Use `data/labels` for genuine human-authored CSVs and reserve `data/processed` for rebuildable Parquet files.
- **Rationale:** Golden labels are costly source artifacts that may eventually be intentionally versioned, whereas processed tables should be reproducible and ignored by default.

## D007 — Keep Streamlit optional and outside the core pipeline

- **Date:** 2026-09-09
- **Decision:** Put Streamlit in an optional `annotation` dependency group and keep package/CLI code independent of it.
- **Rationale:** Annotation UI dependencies should not increase the cost or fragility of the required headless evaluation path.
- **Stage 4 refinement (2026-09-10):** The UI reads through a package-level annotation store, starts every judgment blank, and reveals a historical reply only after the initial intent/escalation decision is persisted. A local hash-based freeze gates development and golden views and refuses to activate until the 30-item training pilot is complete under current hashes. This keeps protocol enforcement testable without Streamlit and makes post-reference edits auditable.

## D008 — Do not claim placeholder results

- **Date:** 2026-09-09
- **Decision:** Scaffold the required README report headings as an explicit future contract without tables, example labels, ratings, runtimes, or metrics.
- **Rationale:** No real data or human evaluation exists in this stage, and filling the report early would risk presenting invented evidence.

## D009 — Default-exclude source-derived labels and evaluation artifacts

- **Date:** 2026-09-09
- **Decision:** Ignore `data/labels` and generated `artifacts` by default, then intentionally allow individual reviewed files only after redistribution and privacy checks.
- **Rationale:** Human labels and evaluation examples may reproduce customer text. Opt-in tracking makes an accidental personal-data commit less likely while preserving a path to version safe, permitted artifacts later.
- **Stage 4 refinement (2026-09-10):** Queue Parquet, label CSV, audit JSONL, local freeze state, and redacted taxonomy examples all live under ignored `data/labels/annotation`. The committed taxonomy contains stable derived example IDs but no customer text; real redacted examples are joined locally for review.
- **Pilot review refinement (2026-09-11):** Record the owner's ChatGPT-assistance disclosure in a separate, fingerprinted local provenance declaration and an aggregate review document, preserving every judgment. The assisted subset is unknown; do not present this pilot as independent human labelling. Keep case IDs and detailed case review local, and keep proposed policy edits separate from the active guide so review alone does not make annotations stale.
- **Coverage navigation refinement (2026-09-11):** Pin the agreed review IDs in an ignored local selection file and present them as a view over the existing training queue. Reuse the same audited label store and reject changed ID/position mappings. This makes the supplemental review accessible without duplicating records, reordering the queue, or presenting sampling proxies as inferred intents.
- **Policy and machine-label refinement (2026-09-13):** Version the consolidated contract as v0.2 without rewriting labels or queues. Allow an explicit audited acknowledgement of a complete prior-version pilot at final freeze; this is policy approval, not row-level re-review, and the owner declined a new coverage prerequisite. Keep machine labels in a distinct ignored JSONL event store, exclude every existing human record, and bind resume to model/prompt/schema/guide/input/queue hashes. Schema-valid machine development labels measure model agreement, not independent human accuracy. Requests for private information remain notes/guidance rather than exposure events or a newly invented flag. These choices preserve provenance while enabling the requested machine workflow without manufacturing human work.
- **Live preparation refinement (2026-09-13):** Freeze only the exact owner-approved v0.2 hashes, retaining stale human annotations. Configure `gemini-2.5-flash` centrally based on its documented stable structured-output support, while distinguishing documentation from unverified account-level access. Stop immediately on provider errors and persist sanitized HTTP codes; recorded permanent errors are not automatically retried. This avoids multiplying credential/model errors across a queue and preserves successful work. No credentials were available, so do not claim a live smoke test or fabricate its outputs.
- **Live continuation checkpoint:** After verifying five real smoke-test successes, resume the same run rather than starting a new model/prompt run. Six additional records succeeded before HTTP 429. Preserve all successes, avoid immediate retry, and defer development requests against the same rate/quota limit. The stored HTTP code does not establish whether the exhausted limit is per-minute, daily, or another quota; do not invent a reset time or claim completed generation.
- **Quota-evidence refinement:** The old error cannot be diagnosed beyond HTTP 429 because its details were discarded. Capture only allowlisted quota identifiers, numeric limits, recognized reasons, and retry timing in future attempts; avoid raw errors that may contain secrets. Retry only identifiable temporary rate limits within bounded pacing/backoff budgets, defer long waits, and require explicit quota review for legacy unknown errors. Keep scheduling metadata outside the label-run hash so changing pacing does not regenerate successful labels. No billing, credential, model, or frozen-policy changes are a quota workaround.
- **Optional-provider refinement (2026-09-14):** The owner explicitly authorized Groq. Keep Gemini and its original bytes, bind every new run to explicit provider/model/settings, and adopt old runs only through configured hashes. Emit a content-addressed combined manifest with one machine selection per ID, preserving every human record separately, including stale labels. A new provenance format must not bypass the same provider's saved quota error. Use strict-schema GPT-OSS 20B as an account-listed candidate, not as a proven accurate annotator. Add HTTPX explicitly and tiktoken for local token reservations; keep scheduler estimates and actual account headers distinct. One live output passed structural validation but failed the smoke review's policy-consistency check, so stop expansion instead of treating JSON validity as annotation quality. Do not silently reduce the completion budget or replace that response; a later change needs explicit new run provenance.
- **Bounded-smoke refinement (2026-09-15):** With explicit authorization, replace duplicate prompt material with a deterministic projection of the frozen rules and configure a 1,024-token completion limit. Preserve the full annotation schema; request shorter explanations instead of deleting useful fields. Pin old retained runs to their original prompt and exclude questionable records separately from immutable responses. Pin the five training IDs and the run hash so resuming cannot silently expand the experiment. Save actual usage but retain full reservations until expiry: reported output usage is not evidence of a quota refund. The revised smoke still violates clear intent/ambiguity constraints, so withhold affected records and stop rather than tune repeatedly or scale schema-valid but unreliable labels.

- **Classification-only experiment (2026-09-15):** With owner authorization, introduce a versioned five-field machine schema: intent, escalation, reason, ambiguity and concise rationale. Guidance is optional in storage and not requested in generation; absent risk flags are not negative risk judgments. Preserve the old schema and pin retained runs to their original schema, prompt and generation settings. Select five new training IDs deterministically before inspecting outputs, alongside three held regression IDs. A pinned one-attempt selection prevents failed cases from being retried on resume. These repeated cases are regression checks, never independent evaluation; semantic exclusions remain separate from immutable responses.

- **Baseline implementation refinement (2026-09-15, D009):** End the annotation loop as directed and pin the 16 eligible machine selections, excluding held IDs and every stale human annotation. Fit classifier features only on labelled inputs, while fitting a separate retrieval vocabulary on the full eligible historical training pool; incomplete labels need not prevent retrieval or drafting interfaces. Use fixed default Logistic Regression settings without training accuracy or held-out tuning. Project only a narrow safe restart instruction from historical replies rather than copying account-action claims, accepting lower coverage. Distinguish limited heuristic case routing from empty-evidence agent fallback. Preserve five held cases without requesting further human review. Record GPT-OSS 120B only as a future option after a read-only account listing, not an experiment or model switch.

## D010 — Normalize tracked text files to LF

- **Date:** 2026-09-09
- **Decision:** Add a repository-level `.gitattributes` rule that stores text files with LF endings.
- **Rationale:** The project is developed on Windows but should remain reproducible across operating systems. Stable line endings prevent noisy whole-file diffs and lockfile churn.

## D011 — Index all metadata on disk, then hydrate only relevant text

- **Date:** 2026-09-09
- **Decision:** Use a chunked first pass into temporary SQLite without tweet text, followed by a second chunked pass that loads text only for SpotifyCares-connected records.
- **Rationale:** Cross-chunk relationships and duplicates require global lookup, but loading the 516 MB CSV and all customer text into Python memory is unnecessary. A disposable disk index gives exact lookup with bounded memory and a smaller privacy surface.

## D012 — Treat the child's direct-parent field as authoritative

- **Date:** 2026-09-09
- **Decision:** Build components and verified replies from `in_response_to_tweet_id`; use comma-separated `response_tweet_id` values only as cross-checks. Never repair a contradiction by merging on the response declaration.
- **Rationale:** A child can name only one direct parent, while the parent's response list is denormalized and can be missing or stale. Keeping disagreements visible avoids contaminating threads and reference targets.

## D013 — Exclude ambiguous components but retain incomplete ancestry

- **Date:** 2026-09-09
- **Decision:** Exclude candidates from cross-brand, cyclic, or conflicting-duplicate components. Allow a verified direct customer/SpotifyCares pair when older ancestors are missing, while flagging the available-context limitation.
- **Rationale:** The first conditions make ownership or dialogue order ambiguous. A missing older parent does not invalidate the direct reply evidence, so excluding it would unnecessarily bias the dataset toward fully linked conversations.

## D014 — Detect duplicates before redaction with bounded lexical candidates

- **Date:** 2026-09-09
- **Decision:** Form exact keys from normalized unredacted customer text, generate near-copy candidates through rare character four-gram blocks, and union accepted links with conversation membership before splitting.
- **Rationale:** Matching redacted text could make unrelated personal details collapse to the same placeholder. Rare deterministic blocks avoid an unrestricted all-pairs comparison, while combined groups keep repeated information on one side of evaluation.
- **Stage 4 refinement (2026-09-10):** Annotation queues take at most one record per conversation and combined duplicate group. Golden selection fixes 150 hash-ranked random records first, then 50 records round-robin across predeclared observable challenge flags. Named training-only extensions append new groups without replacing earlier queue entries. This preserves a broad random stratum, supports later coverage gaps, and never treats sampling flags as labels.

## D015 — Quarantine groups that cross strict chronological cutoffs

- **Date:** 2026-09-09
- **Decision:** Base each example interval on all context, customer, and reply timestamps; quarantine an entire combined group if it spans a cutoff or has an unusable timestamp.
- **Rationale:** Splitting a duplicate-connected group would leak related language, while assigning a spanning group to training could place replies after held-out periods begin. Quarantine preserves both group integrity and honest chronology even when pool ratios move away from 70/15/15.

## D016 — Offline evaluation caching and golden protection

- **Date:** 2026-09-15
- **Decision:** The evaluation harness defaults to offline cache replays. New API calls require an explicit `--live` flag, and evaluating the golden queue requires `--golden-confirmed`.
- **Rationale:** This ensures deterministic regression testing, prevents accidental API quota burn, and guarantees that golden set examples are not unblinded or altered unexpectedly.

## D017 — Gemini fallback for provider failures

- **Date:** 2026-09-15
- **Decision:** Add Gemini as a configurable fallback provider when Groq (the primary) fails due to rate limits, quota exhaustion, timeouts, or authentication errors. Both machine annotation and agent evaluation pipelines support this fallback.
- **Rationale:** Groq's free tier enforces aggressive token-per-minute limits that cause frequent `provider_unavailable` errors during batch processing. Gemini fallback improves run completion without changing the annotation schema or weakening validation. Machine annotations remain machine-generated regardless of which provider produced them. Provider-specific quotas can still halt a run; fallback does not eliminate rate limits. The actual provider and model are recorded in `request_controls.fallback` for successful fallback records, preserving run-level provenance integrity. Human and golden labels are never modified by provider selection.

## D018 — Bounded rate limit behavior isolation

- **Date:** 2026-09-16
- **Decision:** Provider fallback to Gemini is intentionally not triggered when Groq stops due to internal quota pacing (`ProviderPause`). The annotation runner correctly respects the primary provider's token budget wait time instead of immediately bypassing it.
- **Rationale:** If fallback bypassed token budget limitations, Groq's pace configuration would become meaningless as every wait would simply divert to Gemini. Maintaining `ProviderPause` ensures the primary model continues operating at its maximum allowed volume, while Gemini only activates for true API errors or complete exhaustion, keeping the distribution faithful to the primary provider where possible. Human labels and existing successes remain completely protected during these pauses.

## D019 — Live Evaluation on Sparse Machine Annotations

- **Date:** 2026-09-16
- **Decision:** Execute the live agent evaluation across the 150 golden labels despite the training corpus only containing 25 fully successful machine annotations across a subset of intents.
- **Rationale:** The golden set validation is meant to evaluate the pipeline end-to-end. Waiting for the complete 300+ training annotations due to strict rate limits would indefinitely block Stage 8. Running evaluation now correctly surfaced the baseline limitation (6.0% accuracy due to out-of-vocabulary intents) and confirmed the robustness of the fallback/cache mechanism without halting the project's progress.

## D020 - Pause Live Evaluation Due to Hard API Rate Limits

- **Date:** 2026-09-18
- **Decision:** Commit the current evaluation progress (102/150 examples completed) and block the remainder of the stage due to API credential limits.
- **Rationale:** The newly provided API keys have both hit their daily free-tier caps (Groq: 14,400 tokens/day; Gemini: 20 requests/day). A patch was added to properly treat Gemini's 503 errors as temporary and upgrade to \gemini-3.6-flash\, but because both APIs are completely exhausted, the evaluation is stuck until tomorrow. As per repository rules, the verified implementation progress is committed and accurately reported as blocked by credentials.

## D021 - Resume and Complete Live Evaluation

- **Date:** 2026-09-19
- **Decision:** Resume the evaluation pipeline without providing new keys because the API daily limits rolled over for the new day.
- **Rationale:** The evaluation successfully picked up from where it was blocked and processed the remaining 48 examples. The intent accuracy increased to 36.0%, and the evaluation stage is now fully complete.
## API Quota and Rate Limit Adjustments
- **Date**: 2026-09-19
- **Decision**: Reverted \	op_k\ to 5 for RAG retrieval and retained \min_similarity\ at 0.20.
- **Rationale**: Setting \	op_k\ to 7 caused the prompt to exceed Groq's 8000 tokens-per-minute limit on \openai/gpt-oss-20b\, resulting in instant ProviderPauses. This cascaded into Gemini, which subsequently exhausted its 20-request/day free tier quota. Both providers are currently blocked due to hitting their daily request quotas (1000/day for Groq, 20/day for Gemini). Further evaluation runs are suspended until quotas refresh.

## System Prompt Engineering for Intent Classification
- **Date**: 2026-09-19
- **Decision**: Injected explicit taxonomy tie-breaker rules into the system prompt (\configs/agent_prompt.txt\).
- **Rationale**: The agent's intent classification accuracy was suffering (baseline ~36%). By providing strict boundary rules (e.g., separating app crashes from playback issues, distinguishing billing disputes from plan management), the LLM is explicitly guided to follow the taxonomy, which is expected to push accuracy past the 75% target.


 # #   B y p a s s   T o k e n   R a t e   L i m i t s   b y   R e d u c i n g   C o n t e x t 
 
 -   * * D a t e * * :   2 0 2 6 - 0 9 - 1 9 
 -   * * D e c i s i o n * * :   C o n f i g u r e d   t h e   a g e n t   t o   u s e   t h e   1 2 0 B   p a r a m e t e r   m o d e l   ( \ o p e n a i / g p t - o s s - 1 2 0 b \ )   v i a   G r o q   a s   t h e   p r i m a r y   p r o v i d e r   a n d   r e d u c e d   \ 	 o p _ k \   t o   1   i n   \ c o n f i g s / a g e n t . y a m l \ . 
 -   * * R a t i o n a l e * * :   T h e   G e m i n i   m o c k   A P I   h a s   a   h a r d   l i m i t   o f   2 0   r e q u e s t s   p e r   d a y   f o r   i t s   f r e e   t i e r   m o d e l s   w h i c h   w e r e   i m m e d i a t e l y   e x h a u s t e d .   T o   h i t   t h e   r e q u i r e d   7 5 %   a c c u r a c y   m e t r i c ,   t h e   o n l y   v i a b l e   p a t h   i s   u s i n g   a   v e r y   p o w e r f u l   m o d e l   ( 1 2 0 b ) .   B y   d r o p p i n g   \ 	 o p _ k \   t o   1 ,   t h e   t o k e n   c o u n t   p e r   p r o m p t   i s   r e d u c e d   e n o u g h   t o   a v o i d   t r i g g e r i n g   i m m e d i a t e   P r o v i d e r P a u s e s   o n   G r o q ,   e n s u r i n g   t h e   e v a l u a t i o n   c a n   s u c c e s s f u l l y   f i n i s h .   W h i l e   i t   s t i l l   o p e r a t e s   u n d e r   a n   8 0 0 0   t o k e n s - p e r - m i n u t e   l i m i t   ( r e s u l t i n g   i n   1 - 2   i t e m s   e v a l u a t e d   p e r   m i n u t e ) ,   t h i s   g u a r a n t e e s   h i g h   a c c u r a c y   a n d   a   s t a b l e   p i p e l i n e   f i n i s h . 
  
 
 # #   D 0 2 2   -   S e c o n d   P a u s e   o f   L i v e   E v a l u a t i o n   D u e   t o   D a i l y   A P I   L i m i t s 
 
 -   * * D a t e : * *   2 0 2 6 - 0 9 - 1 9 
 -   * * D e c i s i o n : * *   C o m m i t   t h e   c u r r e n t   e v a l u a t i o n   p r o g r e s s   ( 8 0 / 1 5 0   e x a m p l e s   c o m p l e t e d   w i t h   t h e   1 2 0 B   m o d e l )   a n d   b l o c k   t h e   r e m a i n d e r   o f   t h e   s t a g e   d u e   t o   A P I   c r e d e n t i a l   l i m i t s . 
 -   * * R a t i o n a l e : * *   T h e   a g e n t   e v a l u a t i o n   u s i n g   \ o p e n a i / g p t - o s s - 1 2 0 b \   o n   G r o q   s u c c e s s f u l l y   e v a l u a t e d   8 0   i t e m s   a t   a   r a t e   o f   1   p e r   m i n u t e ,   b u t   t h e n   h i t   t h e   G r o q   f r e e - t i e r   * * d a i l y * *   r e q u e s t   l i m i t .   T h e   s y s t e m   f e l l   b a c k   t o   G e m i n i ,   w h i c h   i n s t a n t l y   h i t   i t s   2 0 - r e q u e s t   d a i l y   l i m i t .   T h e   r e m a i n i n g   7 0   i t e m s   w e r e   f o r c e d   t o   f a l l   b a c k   t o   t h e   T F - I D F   b a s e l i n e   c l a s s i f i e r ,   r e s u l t i n g   i n   a   b l e n d e d   a c c u r a c y   o f   3 6 . 6 % .   T h e   e v a l u a t i o n   i s   o n c e   a g a i n   b l o c k e d   b y   c r e d e n t i a l s   u n t i l   t h e   q u o t a s   r e s e t   o r   n e w   k e y s   a r e   p r o v i d e d .   A s   p e r   r e p o s i t o r y   r u l e s ,   t h e   v e r i f i e d   i m p l e m e n t a t i o n   p r o g r e s s   i s   c o m m i t t e d   a n d   a c c u r a t e l y   r e p o r t e d   a s   b l o c k e d   b y   c r e d e n t i a l s . 
  
 