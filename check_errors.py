import json
import pandas as pd

golden = pd.read_parquet('data/processed/splits/test_candidate_inputs.parquet').set_index('example_id')
labels = pd.read_csv('data/labels/annotation/labels/golden.csv').set_index('example_id')

with open('artifacts/evaluation/agent_predictions.jsonl', 'r') as f:
    for line in f:
        d = json.loads(line)
        if d.get('fallback', False): continue
        eid = d['example_id']
        pred = d['intent']
        true = labels.loc[eid, 'primary_intent']
        if pred != true:
            print(f'ID: {eid}')
            print(f'Text: {golden.loc[eid, "customer_text_normalized"]}')
            print(f'Pred: {pred} | True: {true}')
            print('---')
