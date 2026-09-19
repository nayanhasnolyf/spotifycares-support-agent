import yaml
from pathlib import Path
from spotify_cares.agent import load_agent_settings, SemanticRetriever
from spotify_cares.baselines import load_training
from pydantic import BaseModel

class Config(BaseModel):
    class AnnotationConfig(BaseModel):
        split_dir: Path = Path("data/labels/annotation/splits")
    class ArtifactsConfig(BaseModel):
        directory: Path = Path("artifacts")
    annotation: AnnotationConfig = AnnotationConfig()
    artifacts: ArtifactsConfig = ArtifactsConfig()
    
config = Config()
agent_settings = load_agent_settings("configs/agent.yaml")

class BaselineSettings(BaseModel):
    max_training_examples: int = 1000
    tf_idf_max_features: int = 1000
    top_k_history: int = 5
baseline_settings = BaselineSettings()

training, corpus, allowed, report = load_training(config, baseline_settings)
import pandas as pd
membership = pd.read_parquet(config.annotation.split_dir / "train_inputs.parquet", columns=["example_id","thread_id","combined_group_id"])
print("Ready to initialize SemanticRetriever")
retriever = SemanticRetriever(corpus, membership, agent_settings, report["corpus_sha256"], "dummy_hash")
print("Done!")
