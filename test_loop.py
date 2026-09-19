import os, json, yaml
from spotify_cares.config import AppConfig
from spotify_cares.agent import load_agent_settings, load_taxonomy, build_draft_model
from spotify_cares.agent import generate
from pathlib import Path

config = AppConfig(**yaml.safe_load(open("configs/project.yaml")))
settings = load_agent_settings("configs/agent.yaml")

Path("artifacts/agent/generation_events.jsonl").unlink(missing_ok=True)
Path("data/labels/annotation/machine/groq_budget.jsonl").unlink(missing_ok=True)
Path("data/labels/annotation/machine/gemini_budget.jsonl").unlink(missing_ok=True)

message = "Spotify isn't working on my Sonos. Is there an issue that you are aware of? Cheers."
context = []
evidence = []

for i in range(35):
    try:
        print(f"Call {i+1}")
        res, record = generate(config, settings, message, context, evidence)
        if record.get("fallback"):
            print(f"Fallback on call {i+1}:", record.get("error"))
            print(json.dumps(record.get("attempts", []), indent=2))
            break
    except Exception as e:
        print("Exception:", e)
        break

print("Done. Ledger contents:")
ledger = Path("artifacts/agent/generation_events.jsonl")
if ledger.exists():
    print(ledger.read_text())
