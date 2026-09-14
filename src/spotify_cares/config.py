"""Typed loading for the central project configuration."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class MachineRateSettings(StrictModel):
    request_interval_seconds: float = Field(default=0, ge=0, le=60)
    max_retries: int = Field(default=2, ge=0, le=5)
    initial_backoff_seconds: float = Field(default=5, gt=0, le=60)
    max_backoff_seconds: float = Field(default=30, gt=0, le=60)
    jitter_seconds: float = Field(default=1, ge=0, le=10)
    max_single_wait_seconds: float = Field(default=30, ge=0, le=60)
    max_total_retry_wait_seconds: float = Field(default=60, ge=0, le=120)

    @model_validator(mode="after")
    def ordered_backoff(self):
        if self.initial_backoff_seconds > self.max_backoff_seconds:
            raise ValueError("initial backoff cannot exceed maximum backoff")
        return self


class RetainedMachineRun(StrictModel):
    queue: Literal["training", "development"]
    provider: Literal["gemini", "groq"]
    model: str = Field(min_length=1)
    run_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    legacy_gemini: bool = False
    prompt_path: Path = Path("configs/machine_annotation_prompt.txt")


class GroqRateSettings(StrictModel):
    # Operator ceilings, NOT claims about the authenticated organization's limits.
    requests_per_minute: int = Field(default=5, gt=0)
    tokens_per_minute: int = Field(default=30000, gt=0)
    input_tokens_per_minute: int | None = Field(default=None, gt=0)
    output_tokens_per_minute: int | None = Field(default=None, gt=0)
    requests_per_day: int | None = Field(default=None, gt=0)
    tokens_per_day: int | None = Field(default=None, gt=0)


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
    machine_provider: Literal["gemini", "groq"] = "gemini"
    groq_model: str = "openai/gpt-oss-20b"
    groq_prompt_path: Path = Path("configs/machine_annotation_prompt.txt")
    groq_prompt_profile: Literal["full", "compact-v1"] = "full"
    groq_max_completion_tokens: int = Field(default=2048, ge=512, le=4096)
    excluded_machine_runs: dict[str, str] = Field(default_factory=dict)
    machine_record_exclusions_path: Path | None = None
    groq_rate: GroqRateSettings = Field(default_factory=GroqRateSettings)
    retained_machine_runs: list[RetainedMachineRun] = Field(default_factory=list)
    machine_rate: MachineRateSettings = Field(default_factory=MachineRateSettings)

    @model_validator(mode="after")
    def validate_sizes(self) -> "AnnotationSettings":
        import re
        if any(not re.fullmatch(r"[0-9a-f]{64}", key) or not reason.strip()
               for key, reason in self.excluded_machine_runs.items()):
            raise ValueError("excluded runs require SHA-256 keys and reasons")
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
