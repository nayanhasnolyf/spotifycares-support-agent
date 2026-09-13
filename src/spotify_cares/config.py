"""Typed loading for the central project configuration."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, model_validator


class StrictModel(BaseModel):
    """Reject unknown configuration keys so typos fail early."""

    model_config = ConfigDict(extra="forbid")


class ProjectSettings(StrictModel):
    name: str
    brand: str
    random_seed: int


class DataSettings(StrictModel):
    source: str
    support_author_id: str
    raw_dir: Path
    interim_dir: Path
    processed_dir: Path
    labels_dir: Path


class ExtractionSettings(StrictModel):
    input_path: Path
    output_dir: Path
    temp_database: Path
    chunk_size: int
    audit_example_count: int


class PreprocessingSettings(StrictModel):
    examples_path: Path
    relevant_tweets_path: Path
    conversations_path: Path
    output_dir: Path
    version: str
    train_fraction: float
    development_fraction: float
    test_fraction: float
    near_duplicate_threshold: float
    near_duplicate_min_chars: int
    shingle_size: int
    candidate_keys: int
    max_block_size: int
    discovery_sample_size: int
    safe_url_domains: tuple[str, ...]

    @model_validator(mode="after")
    def validate_fractions(self) -> "PreprocessingSettings":
        total = self.train_fraction + self.development_fraction + self.test_fraction
        if abs(total - 1.0) > 1e-9:
            raise ValueError("preprocessing split fractions must sum to 1")
        return self


class AnnotationSettings(StrictModel):
    taxonomy_path: Path
    guide_path: Path
    split_dir: Path
    output_dir: Path
    training_queue_size: int
    development_queue_size: int
    golden_random_size: int
    golden_challenge_size: int
    training_pilot_size: int
    machine_model: str | None = None

    @model_validator(mode="after")
    def validate_sizes(self) -> "AnnotationSettings":
        values = (
            self.training_queue_size,
            self.development_queue_size,
            self.golden_random_size,
            self.golden_challenge_size,
            self.training_pilot_size,
        )
        if any(value <= 0 for value in values):
            raise ValueError("annotation queue and pilot sizes must be positive")
        if self.training_pilot_size > self.training_queue_size:
            raise ValueError("training pilot cannot exceed the training queue")
        return self


class ArtifactSettings(StrictModel):
    directory: Path
    processed_data_format: str
    human_labels_format: str
    predictions_format: str


class AppConfig(StrictModel):
    project: ProjectSettings
    data: DataSettings
    extraction: ExtractionSettings
    preprocessing: PreprocessingSettings
    annotation: AnnotationSettings
    artifacts: ArtifactSettings


def load_config(path: Path) -> AppConfig:
    """Read and validate a YAML project configuration file."""

    with path.open(encoding="utf-8") as handle:
        values = yaml.safe_load(handle)
    return AppConfig.model_validate(values)
