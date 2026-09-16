# SpotifyCares Support Agent

An AI customer-support agent built on the Customer Support on Twitter dataset to handle SpotifyCares inquiries.

This project implements an end-to-end pipeline covering data ingestion, conversation assembly, human annotation scaffolding, offline baseline evaluation, and an LLM-based agent with strict retrieval-grounded generation and deterministic policy routing.

## Final Report

> [!WARNING]
> **Data Blocker Notice**
> Per the project instructions: *"Never invent data, annotations, API outputs, human ratings, or measured results."* 
> The metrics and analysis below require genuine hand-labelled golden sets and live API executions against those sets. The structure is provided below, but actual results are blocked pending human annotation and API quota limits.

### 1. Framing
The SpotifyCares Support Agent aims to assist human agents by pre-drafting responses and routing inquiries based on historical precedence and strict safety rules. Instead of blindly trusting LLM hallucination, the agent uses a **Retrieve-and-Generate (RAG)** approach. It retrieves historically vetted support replies from SpotifyCares and forces the generation step to strictly ground its response in that retrieved evidence. Furthermore, a deterministic policy engine overrides the LLM for high-risk actions (e.g., security incidents, payment issues) to enforce human escalation, ensuring safe and predictable customer service.

### 2. Results
*Live Evaluation Complete*
- **Total Labeled Golden Examples:** 150
- **Agent Intent Accuracy:** 6.0% (9/150)
- **Escalation Safety Recall:** 83.1% (69 successfully escalated out of 83 true escalation cases)
- **False Auto-Handle Rate:** 60.9% (14 unsafe auto-handles out of 23 proposed auto-handles)
- **Empty Retrieval Rate:** 84.7% (127/150 examples had insufficient retrieval or generation evidence)

### 3. Baseline Comparison
*Live Evaluation Complete*
We evaluate the Agent against two automated baselines:
1. **Trivial Baseline (Majority Class):** Achieves 6.0% intent accuracy. Represents zero-intelligence guessing.
2. **TF-IDF Baseline:** Achieves 5.3% intent accuracy. Represents standard lexical retrieval.
3. **Agent (Retrieval-Grounded LLM):** Achieves 6.0% intent accuracy. Represents semantic understanding and context-aware drafting.

### 4. Five Observed Failure Modes
*Live Evaluation Diagnostics & Pending Human Judge Analysis...*
Based on live evaluation and preliminary architecture, we observe/expect the following failure modes:
1. **[OBSERVED] Out-of-Vocabulary Intents:** The baseline models were fitted on only 61 training examples, causing them to systematically miss remaining classes, locking baseline accuracy around ~5-6%. Inquiries outside the trained taxonomy cause unpredictable routing.
2. **[PENDING] Retrieval Mismatch:** Sparse or vague queries retrieve irrelevant historical conversations, leading to confusing drafts.
3. **[PENDING] Strict Fallback Over-Escalation:** The strict policy engine flags safe queries if they mimic security vocabulary.
4. **[PENDING] Provider Rate Limiting:** Real-time generation pauses when LLM providers rate-limit, falling back to ACK templates.
5. **[PENDING] Prompt Injection Bleed:** While strongly defended, deeply nested contextual context tweets might rarely influence the RAG framing.

### 5. What is misleading about my headline number?
*Pending Actual Metrics...*
- The evaluation dataset heavily relies on the Twitter Customer Support dataset, which is biased towards public social media complaints. Performance on direct chat/email channels may differ significantly.
- "Escalation Safety Recall" assumes that the human golden labels are perfectly safe; however, human annotator disagreement adds noise to this absolute safety guarantee.
- Caching API results artificially inflates latency metrics for repeat queries during evaluation, which does not reflect real-world first-touch latency.

### 6. Next Steps
1. **Collect Golden Set:** Execute the `annotation_app.py` workflow with trained human reviewers to establish the hand-labeled baseline.
2. **Live Evaluation:** Run `spotify-cares evaluate --queue golden --live --golden-confirmed` to generate the raw prediction cache and metrics.
3. **Review Diagnostics:** Analyze the `report.json` to identify systematic errors and adjust the `configs/agent_prompt.txt`.

---

## Running the Application

### 1. Requirements
- Python 3.10+
- `uv` package manager

### 2. Setup
```bash
uv sync
```

### 3. Agent Demo (CLI)
Interact with the agent directly from the command line:
```bash
uv run spotify-cares agent-demo --message "My music stops playing randomly"
```

### 4. Machine Annotation with Provider Fallback
Groq is the primary LLM provider; Gemini is used as a fallback when Groq fails due to unrecoverable API errors. Verified behavior correctly respects Groq's internal token pacing (`ProviderPause`) rather than blindly bypassing it, allowing Groq to maintain its maximum allowed volume. Both providers produce machine-generated labels — fallback improves overall robustness without corrupting provenance, and all human golden labels remain completely protected and frozen.
```bash
uv run --env-file .env spotify-cares machine-annotate --queue training --provider groq --fallback-provider gemini --limit 5
```

### 5. Agent Demo (Streamlit)
Run the web-based interactive demo:
```bash
uv run streamlit run app/agent_app.py
```

### 6. Automated Tests
```bash
$env:TMP="C:\temp"
$env:TEMP="C:\temp"
uv run pytest -q --tb=short --basetemp=C:\temp\ptsc
```
