import json
import streamlit as st
from pathlib import Path
from spotify_cares.agent import load_agent_settings, run_agent
from spotify_cares.baselines import load_settings
from spotify_cares.config import load_config
from spotify_cares.annotation import AnnotationError

st.set_page_config(page_title="SpotifyCares Agent Demo", page_icon="🎧", layout="wide")

st.title("🎧 SpotifyCares Support Agent Demo")
st.markdown("Interact with the retrieval-augmented generation (RAG) customer support agent.")

@st.cache_resource
def get_system():
    try:
        config = load_config(Path("configs/project.yaml"))
        baseline_settings = load_settings(Path("configs/baselines.yaml"))
        agent_settings = load_agent_settings(Path("configs/agent.yaml"))
        return config, baseline_settings, agent_settings
    except (AnnotationError, ValueError, OSError) as e:
        st.error(f"Failed to load agent configuration: {e}")
        return None, None, None

config, baseline_settings, agent_settings = get_system()

if config:
    message = st.text_area("Customer Message", height=100, placeholder="e.g. My app keeps crashing when I try to play downloaded music.")
    
    with st.expander("Advanced Context (Optional)"):
        context_input = st.text_area("Context Tweets (one per line)", height=100)
    
    if st.button("Generate Response"):
        if not message.strip():
            st.warning("Please enter a customer message.")
        else:
            context = [line.strip() for line in context_input.split('\n') if line.strip()]
            
            with st.spinner("Processing..."):
                try:
                    result = run_agent(config, baseline_settings, agent_settings, message, context)
                    
                    st.subheader("Decision")
                    if result["decision"] == "proposed_auto_handle":
                        st.success(f"**Action:** {result['decision']}")
                    else:
                        st.warning(f"**Action:** {result['decision']}")
                    
                    if result["reason_codes"]:
                        st.write("**Reason Codes:**", ", ".join(result["reason_codes"]))
                    
                    st.subheader("Draft Reply")
                    if result["fallback"]:
                        st.error("Using Fallback Response:")
                    st.info(result["draft"])
                    
                    st.subheader("Retrieved Evidence (Grounded Examples)")
                    if not result["evidence_ids"]:
                        st.write("No direct evidence used.")
                    else:
                        st.write(", ".join(result["evidence_ids"]))
                        
                    with st.expander("Raw Output JSON"):
                        st.json(result)
                        
                except Exception as e:
                    st.error(f"An error occurred: {e}")
else:
    st.warning("Please ensure the configuration files exist and the training baseline is generated.")
