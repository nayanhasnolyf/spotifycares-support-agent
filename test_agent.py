import os, json, yaml
from spotify_cares.config import AppConfig
from spotify_cares.agent import load_agent_settings, load_taxonomy, build_draft_model
from spotify_cares.agent import generate

config = AppConfig(**yaml.safe_load(open("configs/project.yaml")))
settings = load_agent_settings("configs/agent.yaml")
settings.provider = "groq"
settings.model = "openai/gpt-oss-20b"

message = "Spotify isn't working on my Sonos. Is there an issue that you are aware of? Cheers."
context = []
evidence = []

try:
    res, record = generate(config, settings, message, context, evidence)
    print("RES:")
    print(res)
    print("RECORD:")
    print(json.dumps(record, indent=2))
except Exception as e:
    import traceback
    traceback.print_exc()
    print("Exception:", e)
