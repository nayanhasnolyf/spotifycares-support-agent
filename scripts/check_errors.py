"""Diagnostic utility to compare cached agent predictions against golden labels and print mismatches."""

import json
import sys
from pathlib import Path
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent

golden_path = REPO_ROOT / "data" / "processed" / "splits" / "test_candidate_inputs.parquet"
labels_path = REPO_ROOT / "data" / "labels" / "annotation" / "labels" / "golden.csv"
predictions_path = REPO_ROOT / "artifacts" / "evaluation" / "agent_predictions.jsonl"

if not golden_path.exists() or not labels_path.exists() or not predictions_path.exists():
    print(f"Required inputs not found. Ensure splits, labels, and evaluation artifacts exist.")
    sys.exit(1)

golden = pd.read_parquet(golden_path).set_index("example_id")
labels = pd.read_csv(labels_path).set_index("example_id")

mismatches = 0
with open(predictions_path, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("fallback", False):
            continue
        eid = d["example_id"]
        pred = d["intent"]
        if eid not in labels.index:
            continue
        true = labels.loc[eid, "primary_intent"]
        if pred != true:
            mismatches += 1
            print(f"ID: {eid}")
            text = golden.loc[eid, "customer_text_normalized"] if eid in golden.index else "N/A"
            print(f"Text: {text}")
            print(f"Pred: {pred} | True: {true}")
            print("---")

print(f"Total non-fallback mismatches found: {mismatches}")
