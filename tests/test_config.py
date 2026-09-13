from pathlib import Path

from spotify_cares.config import load_config


def test_project_config_names_final_brand():
    config = load_config(Path("configs/project.yaml"))
    assert config.project.brand == "SpotifyCares"
    assert config.data.support_author_id == "SpotifyCares"
    assert config.extraction.input_path == Path("data/raw/twcs.csv")
    assert config.preprocessing.output_dir == Path("data/processed/splits")
    assert config.preprocessing.discovery_sample_size == 400
    assert config.annotation.taxonomy_path == Path("configs/taxonomy.yaml")
    assert config.annotation.golden_random_size == 150
    assert config.annotation.golden_challenge_size == 50
    assert config.annotation.machine_model == "gemini-2.5-flash"


def test_required_storage_formats_are_explicit():
    config = load_config(Path("configs/project.yaml"))
    assert config.artifacts.processed_data_format == "parquet"
    assert config.artifacts.human_labels_format == "csv"
    assert config.artifacts.predictions_format == "jsonl"
