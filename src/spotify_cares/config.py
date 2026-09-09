"""Typed loading for the central project configuration."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


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


class ArtifactSettings(StrictModel):
    directory: Path
    processed_data_format: str
    human_labels_format: str
    predictions_format: str


class AppConfig(StrictModel):
    project: ProjectSettings
    data: DataSettings
    extraction: ExtractionSettings
    artifacts: ArtifactSettings


def load_config(path: Path) -> AppConfig:
    """Read and validate a YAML project configuration file."""

    with path.open(encoding="utf-8") as handle:
        values = yaml.safe_load(handle)
    return AppConfig.model_validate(values)
