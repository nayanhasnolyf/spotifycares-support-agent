"""Local-only Streamlit interface for genuine human annotations."""

from pathlib import Path

import streamlit as st

from spotify_cares.annotation import (
    AnnotationError,
    AnnotationStore,
    get_annotation_view,
    load_guide_state,
    load_queue,
    load_taxonomy,
    reveal_reference,
    save_expected_guidance,
    save_initial_judgment,
    skip_example,
)
from spotify_cares.config import load_config
from spotify_cares.review_navigation import coverage_review_view


CONFIG_PATH = Path("configs/project.yaml")


def _index(options: list[str], value: str | None) -> int | None:
    return options.index(value) if value in options else None


st.set_page_config(page_title="SpotifyCares annotation", layout="wide")
st.title("SpotifyCares human annotation")
st.caption("Local tool. Labels start blank; no model prediction or suggestion is loaded.")

config = load_config(CONFIG_PATH)
taxonomy = load_taxonomy(config.annotation.taxonomy_path)
state = load_guide_state(config)

with st.sidebar:
    st.subheader("Guide checkpoint")
    st.write(f"Taxonomy: `{taxonomy.taxonomy_version}`")
    st.write(f"Guide: `{taxonomy.guide_version}`")
    st.write(f"Local state: **{state['status']}**")
    st.caption("Review `docs/annotation_guide.md` before labelling.")
    queue_name = st.selectbox("Queue", ["training", "development", "golden"])
    annotator_id = st.text_input("Annotator ID", placeholder="your stable initials or ID")
    if queue_name == "training":
        st.info(f"Review and label the first {config.annotation.training_pilot_size} items as the pilot.")
    elif state["status"] != "frozen":
        st.warning("This queue is locked until the proposed guide is reviewed and frozen.")

try:
    queue = load_queue(config, queue_name)
    store = AnnotationStore(config, queue_name)
    records = store.load()
except AnnotationError as error:
    st.error(str(error))
    st.stop()

review_mode = "Full queue"
if queue_name == "training":
    review_mode = st.sidebar.radio(
        "Training view", ["Full queue", "Coverage review"]
    )
    if review_mode == "Coverage review":
        try:
            queue = coverage_review_view(
                queue, config.annotation.output_dir / "coverage_review.json"
            )
        except AnnotationError as error:
            st.error(str(error))
            st.stop()
        st.sidebar.caption(
            "Selected existing training examples. Coverage groups are sampling "
            "proxies, not verified intents. Saves use the original training records."
        )

state_key = f"position_{queue_name}_{review_mode}"
if state_key not in st.session_state:
    st.session_state[state_key] = 0

if review_mode == "Coverage review":
    review_ids = queue["example_id"].astype(str).tolist()
    original_positions = dict(zip(review_ids, queue["queue_position"]))
    choice_key = "coverage_review_example"
    st.session_state[choice_key] = review_ids[
        min(st.session_state[state_key], len(review_ids) - 1)
    ]

    def select_coverage_example():
        st.session_state[state_key] = review_ids.index(st.session_state[choice_key])

    st.sidebar.selectbox(
        "Coverage review example",
        review_ids,
        key=choice_key,
        format_func=lambda value: f"Training #{original_positions[value]} · {value}",
        on_change=select_coverage_example,
    )
    completed = sum(
        value in records and records[value].status == "complete" for value in review_ids
    )
    st.sidebar.caption(f"Coverage review: {completed}/{len(review_ids)} complete")

controls = st.columns([1, 1, 2, 4])
if controls[0].button("Back", disabled=st.session_state[state_key] <= 0):
    st.session_state[state_key] -= 1
    st.rerun()
if controls[1].button("Next", disabled=st.session_state[state_key] >= len(queue) - 1):
    st.session_state[state_key] += 1
    st.rerun()
if controls[2].button("Resume first incomplete"):
    for index, row in queue.iterrows():
        record = records.get(str(row["example_id"]))
        if record is None or record.status != "complete":
            st.session_state[state_key] = int(index)
            break
    st.rerun()

position = min(st.session_state[state_key], len(queue) - 1)
queue_row = queue.iloc[position]
example_id = str(queue_row["example_id"])
existing = records.get(example_id)
view = get_annotation_view(config, queue_name, example_id)

if review_mode == "Coverage review":
    st.subheader(
        f"Coverage review {position + 1} / {len(queue)} "
        f"· Original training position {queue_row['queue_position']}"
    )
else:
    st.subheader(f"{queue_name.title()} {position + 1} / {len(queue)}")
st.code(example_id)
if existing:
    st.caption(
        f"Saved status: {existing.status}; revision {existing.revision}; "
        f"annotated at {existing.annotation_timestamp.isoformat()}"
    )

left, right = st.columns(2)
with left:
    st.markdown("#### Information available to the agent")
    if view["preceding_context"]:
        for item in view["preceding_context"]:
            role = "Customer" if bool(item["context_inbound"]) else "SpotifyCares"
            st.caption(f"{role} · {item['context_created_at_utc']}")
            st.write(item["context_texts_redacted"])
    else:
        st.warning("No preceding context is available.")
    st.caption("Incoming customer message")
    st.info(view["customer_text_redacted"])
    if view["quality_flags"]:
        st.warning("Data-quality flags: " + ", ".join(view["quality_flags"]))
    else:
        st.caption("No recorded data-quality flags.")

with right:
    st.markdown("#### Initial intent and escalation judgment")
    intent_options = [item.label for item in taxonomy.intents]
    reason_options = [item.code for item in taxonomy.escalation_policy.reason_codes]
    with st.form(f"judgment_{example_id}"):
        primary_intent = st.selectbox(
            "Primary intent",
            intent_options,
            index=_index(intent_options, existing.primary_intent if existing else None),
            placeholder="Choose after reading the message and context",
        )
        should_escalate = st.radio(
            "Should a human handle this case under the written policy?",
            ["yes", "no"],
            index=_index(["yes", "no"], existing.should_escalate if existing else None),
            horizontal=True,
        )
        escalation_reason = st.selectbox(
            "Escalation reason code (required for yes)",
            reason_options,
            index=_index(reason_options, existing.escalation_reason_code if existing else None),
            placeholder="Choose only when escalation is yes",
        )
        escalation_explanation = st.text_area(
            "Escalation explanation",
            value=existing.escalation_explanation or "" if existing else "",
        )
        risk_flags = st.multiselect(
            "Risk flags",
            taxonomy.risk_flags,
            default=list(existing.risk_flags) if existing else [],
        )
        ambiguity = st.radio(
            "Ambiguity",
            ["clear", "ambiguous"],
            index=_index(["clear", "ambiguous"], existing.ambiguity if existing else None),
            horizontal=True,
        )
        notes = st.text_area(
            "Annotation notes",
            value=existing.annotation_notes if existing else "",
        )
        save_judgment = st.form_submit_button(
            "Save edits" if existing else "Save judgment"
        )
    if save_judgment:
        try:
            save_initial_judgment(
                config,
                queue_name=queue_name,
                example_id=example_id,
                primary_intent=primary_intent,
                should_escalate=should_escalate,
                escalation_reason_code=escalation_reason,
                escalation_explanation=escalation_explanation,
                risk_flags=tuple(risk_flags),
                ambiguity=ambiguity,
                annotation_notes=notes,
                annotator_id=annotator_id,
            )
            st.success("Initial judgment saved safely.")
            st.rerun()
        except (AnnotationError, ValueError) as error:
            st.error(str(error))

    if st.button("Skip (remains incomplete)"):
        try:
            skip_example(config, queue_name, example_id, annotator_id, notes)
            st.warning("Example recorded as skipped and still incomplete.")
            st.rerun()
        except (AnnotationError, ValueError) as error:
            st.error(str(error))

st.divider()
st.markdown("#### Historical reference (separate and imperfect)")
if not existing or existing.status == "skipped":
    st.info("Save the initial intent and escalation judgment before revealing the historical reply.")
elif not existing.reference_revealed:
    if st.button("Reveal historical reply"):
        try:
            reveal_reference(config, queue_name, example_id)
            st.rerun()
        except AnnotationError as error:
            st.error(str(error))
else:
    for reply in view["historical_reference"]["reply_texts_redacted"]:
        st.write(reply)
    st.warning(view["historical_reference"]["warning"])
    with st.form(f"guidance_{example_id}"):
        guidance = st.text_area(
            "Expected reply guidance",
            value=existing.expected_reply_guidance,
            help="Describe what a good reply should accomplish; do not blindly copy the historical reply.",
        )
        finish = st.form_submit_button("Save guidance and mark complete")
    if finish:
        try:
            save_expected_guidance(config, queue_name, example_id, guidance)
            st.success("Annotation marked complete.")
            st.rerun()
        except (AnnotationError, ValueError) as error:
            st.error(str(error))

with st.expander("Proposed intent definitions"):
    for intent in taxonomy.intents:
        st.markdown(f"**{intent.label} — {intent.name}**")
        st.write(intent.meaning)
