"""Local-only Streamlit interface specifically for genuine human golden annotations."""

from pathlib import Path

import streamlit as st

from spotify_cares.annotation import (
    AnnotationError,
    AnnotationStore,
    current_contract,
    get_annotation_view,
    load_guide_state,
    load_queue,
    load_taxonomy,
    save_initial_judgment,
    save_expected_guidance,
    skip_example,
)
from spotify_cares.config import load_config


CONFIG_PATH = Path("configs/project.yaml")


def _index(options: list[str], value: str | None) -> int | None:
    return options.index(value) if value in options else None


st.set_page_config(page_title="SpotifyCares Golden Annotation", layout="wide")
st.title("SpotifyCares Golden Queue Annotation")
st.caption("Local tool. Fields are minimized for speed. Keyboard-friendly Save & Next (Press Enter inside form). No model predictions or scores are exposed.")

config = load_config(CONFIG_PATH)
taxonomy = load_taxonomy(config.annotation.taxonomy_path)
state = load_guide_state(config)

queue_name = "golden"

with st.sidebar:
    st.subheader("Golden Guidelines")
    st.write(f"Taxonomy: `{taxonomy.taxonomy_version}`")
    st.write(f"Guide: `{taxonomy.guide_version}`")
    
    if state["status"] != "frozen":
        st.warning("The golden queue is locked until the guide is reviewed and frozen.")
        st.stop()
        
    annotator_id = st.text_input("Annotator ID", placeholder="your stable initials or ID")
    if not annotator_id:
        st.warning("Please enter your Annotator ID to begin.")
        st.stop()

try:
    queue = load_queue(config, queue_name)
    store = AnnotationStore(config, queue_name)
    records = store.load()
except AnnotationError as error:
    st.error(str(error))
    st.stop()

state_key = f"position_{queue_name}"
if state_key not in st.session_state:
    st.session_state[state_key] = 0

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
        if record is None or record.status not in ("complete", "judgment_saved"):
            st.session_state[state_key] = int(index)
            break
    st.rerun()

position = min(st.session_state[state_key], len(queue) - 1)
queue_row = queue.iloc[position]
example_id = str(queue_row["example_id"])
existing = records.get(example_id)
view = get_annotation_view(config, queue_name, example_id)

st.subheader(f"Golden {position + 1} / {len(queue)}")
st.code(example_id)

if existing:
    st.caption(f"Status: {existing.status} at {existing.annotation_timestamp.isoformat()}")

left, right = st.columns(2)
with left:
    st.markdown("#### Message Context")
    if view["preceding_context"]:
        for item in view["preceding_context"]:
            role = "Customer" if bool(item["context_inbound"]) else "SpotifyCares"
            st.caption(f"{role} · {item['context_created_at_utc']}")
            st.write(item["context_texts_redacted"])
    st.caption("Incoming customer message")
    st.info(view["customer_text_redacted"])

with right:
    st.markdown("#### Judgment")
    intent_options = [item.label for item in taxonomy.intents]
    reason_options = ["None"] + [item.code for item in taxonomy.escalation_policy.reason_codes]
    
    with st.form(f"judgment_{example_id}"):
        primary_intent = st.selectbox(
            "Primary intent (required)",
            intent_options,
            index=_index(intent_options, existing.primary_intent if existing else None),
        )
        should_escalate = st.radio(
            "Escalate to human? (required)",
            ["yes", "no"],
            index=_index(["yes", "no"], existing.should_escalate if existing else None),
            horizontal=True,
        )
        
        # Determine existing reason for index mapping safely
        default_reason = existing.escalation_reason_code if existing and existing.escalation_reason_code else "None"
        escalation_reason = st.selectbox(
            "Reason (required if Escalate is yes)",
            reason_options,
            index=_index(reason_options, default_reason) or 0,
        )
        
        ambiguity = st.radio(
            "Ambiguity",
            ["clear", "ambiguous"],
            index=_index(["clear", "ambiguous"], existing.ambiguity if existing else None),
            horizontal=True,
        )
        
        notes = st.text_input(
            "Notes (optional unless ambiguous)",
            value=existing.annotation_notes if existing else "",
        )
        
        expected_guidance = st.text_input(
            "Expected Reply Guidance (optional)",
            value=existing.expected_reply_guidance if existing else "",
        )
        
        save_judgment = st.form_submit_button("Save & Next", type="primary")
        
    if save_judgment:
        has_error = False
        
        if should_escalate == "yes" and escalation_reason == "None":
            st.error("Escalation reason is required when should_escalate is 'yes'.")
            has_error = True
            
        if ambiguity == "ambiguous" and not notes.strip():
            st.error("Notes are required when ambiguity is 'ambiguous'.")
            has_error = True
            
        if not has_error:
            try:
                # Clean up escalation reason if 'no' is selected
                final_reason = escalation_reason if should_escalate == "yes" else None
                
                save_initial_judgment(
                    config,
                    queue_name=queue_name,
                    example_id=example_id,
                    primary_intent=primary_intent,
                    should_escalate=should_escalate,
                    escalation_reason_code=final_reason,
                    escalation_explanation="golden set annotation" if final_reason else None,
                    risk_flags=(),
                    ambiguity=ambiguity,
                    annotation_notes=notes if notes else "golden set annotation",
                    annotator_id=annotator_id,
                )
                
                # If expected guidance is provided, mark it completely complete
                if expected_guidance.strip():
                    save_expected_guidance(
                        config, 
                        queue_name=queue_name, 
                        example_id=example_id, 
                        guidance=expected_guidance
                    )
                    
                st.success("Saved.")
                if st.session_state[state_key] < len(queue) - 1:
                    st.session_state[state_key] += 1
                st.rerun()
            except (AnnotationError, ValueError) as error:
                st.error(str(error))

    if st.button("Skip (remains incomplete)"):
        try:
            skip_example(config, queue_name, example_id, annotator_id, "skipped in golden")
            if st.session_state[state_key] < len(queue) - 1:
                st.session_state[state_key] += 1
            st.rerun()
        except (AnnotationError, ValueError) as error:
            st.error(str(error))
