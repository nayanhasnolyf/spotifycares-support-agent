from spotify_cares.config import load_config
from spotify_cares.baselines import load_settings
from spotify_cares.agent import load_agent_settings, run_agent
import json
from pathlib import Path
config = load_config(Path("configs/project.yaml"))
baseline_settings = load_settings(Path("configs/baselines.yaml"))
agent_settings = load_agent_settings(Path("configs/agent.yaml"))

msg = "[CUSTOMER] hi I cant log in via the app"
res = run_agent(config, baseline_settings, agent_settings, msg)
print(json.dumps(res, indent=2))
