import pandas as pd
from spotify_cares.baselines import load_training, IntentBaselines
from spotify_cares.agent import SemanticRetriever, sha256_file, generate, route_policy, direct_signals, feature_text
class FastAgentSystem:
    def __init__(self, config, baseline_settings, agent_settings):
        self.config = config
        self.baseline_settings = baseline_settings
        self.agent_settings = agent_settings
        self.training, self.corpus, self.allowed, self.report = load_training(config, baseline_settings)
        self.membership = pd.read_parquet(config.annotation.split_dir / "train_inputs.parquet", columns=["example_id","thread_id","combined_group_id"])
        self.retriever = SemanticRetriever(self.corpus, self.membership, agent_settings, self.report["corpus_sha256"], sha256_file(config.annotation.split_dir / "preprocessing_manifest.json"))
        self.classifier = IntentBaselines(self.training, self.allowed, baseline_settings)
        
    def predict(self, message: str, context: list[str]) -> dict:
        evidence = self.retriever.search(message, context)
        draft, generation = generate(self.config, self.agent_settings, message, context, evidence)
        intent = draft.intent if (draft and hasattr(draft, 'intent') and draft.intent) else (self.classifier.predict(feature_text(message,context),"tfidf") if self.classifier.model is not None else None)
        route = route_policy(direct_signals(message,context))
        reasons = [route["reason_code"]] if route["reason_code"] else []
        if generation["fallback"]:
            reasons.append(generation["error"])
        if not evidence or draft.insufficient_evidence or not draft.evidence_ids:
            reasons.append("insufficient_retrieval_or_generation_evidence")
        if self.classifier.model is None:
            reasons.append("intent_classifier_unavailable")
        return {
            "intent": intent,
            "decision": "proposed_escalate" if reasons else "proposed_auto_handle",
            "draft": "",
            "reason_codes": sorted(set(reasons)),
            "fallback": generation["fallback"],
            "generation": generation
        }
