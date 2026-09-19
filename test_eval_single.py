import os, json
from spotify_cares.main import _get_config
from spotify_cares.evaluate import load_baselines, load_agent_settings
from spotify_cares.agent import run_agent

config = _get_config()
baseline_settings = load_baselines("configs/baselines.yaml")
agent_settings = load_agent_settings("configs/agent.yaml")

# Load a golden example
golden = [json.loads(line) for line in open("data/labels/annotation/machine/generation.jsonl")]
ex = golden[10] # Pick an arbitrary example
print(ex["customer_message"])
res = run_agent(config, baseline_settings, agent_settings, ex["customer_message"], ex["preceding_context"])
print("Intent:", res["intent"])
