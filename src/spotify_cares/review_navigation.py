"""Read-only views of locally pinned training review IDs."""

from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from spotify_cares.annotation import AnnotationError


class ReviewExample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_position: int = Field(ge=1)
    example_id: str = Field(min_length=1)


class ReviewSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    queue_name: Literal["training"]
    name: str
    source_queue_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    purpose: str
    examples: list[ReviewExample] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_examples(self) -> "ReviewSelection":
        if len({item.example_id for item in self.examples}) != len(self.examples):
            raise ValueError("review selection contains duplicate IDs")
        if len({item.original_position for item in self.examples}) != len(self.examples):
            raise ValueError("review selection contains duplicate positions")
        return self


def coverage_review_view(queue: pd.DataFrame, selection_path: Path) -> pd.DataFrame:
    """Select by stable ID, retaining original positions and original queue order.

    The source fingerprint records when IDs were pinned. A later queue extension
    is allowed, but an ID must still occupy its original position. No positions
    are re-resolved to replacement IDs and no source or label file is written.
    """

    if not selection_path.is_file():
        raise AnnotationError(
            "Coverage review selection is missing: " + str(selection_path)
        )
    try:
        selection = ReviewSelection.model_validate_json(
            selection_path.read_text(encoding="utf-8")
        )
    except ValueError as error:
        raise AnnotationError(f"Invalid coverage review selection: {error}") from error
    if set(queue["queue_name"]) != {"training"}:
        raise AnnotationError("Coverage review is available only for the training queue")
    if queue["example_id"].duplicated().any() or queue["queue_position"].duplicated().any():
        raise AnnotationError("Training queue contains duplicate IDs or positions")
    positions = queue.set_index("example_id")["queue_position"].to_dict()
    for item in selection.examples:
        if positions.get(item.example_id) != item.original_position:
            raise AnnotationError(
                "Pinned review ID is missing or its original position changed: "
                + item.example_id
            )
    ids = {item.example_id for item in selection.examples}
    return queue.loc[queue["example_id"].isin(ids)].copy().reset_index(drop=True)
