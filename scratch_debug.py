import json
from spotify_cares.agent import load_agent_settings
from spotify_cares.config import load_config
from spotify_cares.baselines import load_settings
from spotify_cares.agent import run_agent

config = load_config("configs/config.yaml")
baselines = load_settings("configs/baselines.yaml")
agent_settings = load_agent_settings("configs/agent.yaml")

# Find an example that failed
failures = []
with open("artifacts/evaluation/agent_predictions.jsonl") as f:
    for line in f:
        failures.append(json.loads(line))

# The script evaluate.py just calls `run_agent(..., message, context)`
# Let's just mock one or use one from the failures if possible
print("Testing direct generation...")
try:
    from spotify_cares.groq_annotation import GroqProvider
    from spotify_cares.agent import GeneratedDraft
    provider = GroqProvider(config.annotation)
    provider(model="openai/gpt-oss-20b", system="You are a bot", schema=GeneratedDraft.model_json_schema(), message="hello")
except Exception as e:
    import traceback
    traceback.print_exc()

try:
    from spotify_cares.machine_annotation import GeminiProvider
    provider = GeminiProvider()
    provider(model="gemini-2.5-flash", system="You are a bot", schema=GeneratedDraft.model_json_schema(), message=[{"role": "user", "content": "hello"}])
except Exception as e:
    import traceback
    traceback.print_exc()
