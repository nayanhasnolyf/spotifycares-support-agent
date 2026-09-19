from pathlib import Path
from spotify_cares.config import load_config
from spotify_cares.baselines import load_settings
from spotify_cares.agent import load_agent_settings
from spotify_cares.evaluation import _load_labels, cached_evaluation, AgentSystem
import json

config = load_config(Path("configs/project.yaml"))
baseline_settings = load_settings(Path("configs/baselines.yaml"))
agent_settings = load_agent_settings(Path("configs/agent.yaml"))

# Load golden records
records = _load_labels(config, "golden", config.annotation.split_dir, must_have_labels=True)
records_5 = records[:5]

system = AgentSystem(config, baseline_settings, agent_settings)
cache_dir = Path("artifacts/evaluation/fresh_cache")
cache_dir.mkdir(parents=True, exist_ok=True)

# Delete the cache file if it exists to ensure a fresh run
cache_file = cache_dir / "agent_predictions.jsonl"
if cache_file.exists():
    cache_file.unlink()

results = cached_evaluation(system, "agent", records_5, cache_dir, live=True)

# Print out some checks
fallback_count = sum(r["prediction"]["fallback"] for r in results)
evidence_count = sum(len(r["prediction"]["evidence"]) > 0 for r in results)
valid_evidence_ids = sum(isinstance(r["prediction"].get("evidence_ids"), list) for r in results)

print("Errors for all cases:")
for i, r in enumerate(results):
    print(f"Case {i}: fallback={r['prediction']['fallback']}, error={r['prediction']['generation'].get('error')}")

print(f"Results Count: {len(results)}")
print(f"Fallback Rate: {fallback_count / len(results)}")
print(f"Retrieval returned evidence for: {evidence_count} cases")
print(f"Predictions contain evidence_ids for: {valid_evidence_ids} cases")
print(f"First result provider: {results[0]['prediction']['generation']['provider']}")
print(f"First result model: {results[0]['prediction']['generation']['model']}")
print(f"First result prompt hash exists: {'prompt_sha256' in results[0]['prediction']['generation']}")
print(f"First result policy hashes exists: {'policy' in results[0]['prediction']}")

# Show token usage for the first one
print("Token usage for case 1:")
print(json.dumps(results[0]["prediction"]["generation"]["attempts"][-1]["controls"]["usage"], indent=2))
print("Observed headers for case 1:")
print(json.dumps(results[0]["prediction"]["generation"]["attempts"][-1]["controls"]["observed_headers"], indent=2))
