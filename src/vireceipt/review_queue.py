"""Join image-only manifests with predictions without opening receipt labels."""

import json
from dataclasses import dataclass
from pathlib import Path

from vireceipt.eval.io import Prediction, load_predictions
from vireceipt.extract_cli import load_manifest


@dataclass(frozen=True)
class ReviewItem:
    """One source image and its unmodified model prediction."""

    id: str
    image: Path
    prediction: Prediction


def _input_path(root: Path, path: Path) -> Path:
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Review input must be inside the data directory")
    relative = resolved.relative_to(root)
    if not relative.parts or relative.parts[0].casefold() == "labels":
        raise ValueError("Review inputs must be image manifests and predictions, not labels")
    if tuple(part.casefold() for part in relative.parts) == ("review", "corrections.jsonl"):
        raise ValueError("Review inputs cannot be the corrections output")
    return resolved


def load_review_queue(data_dir: Path, manifest: Path, predictions: Path) -> list[ReviewItem]:
    """Require a complete ID match, preserving manifest order and raw invalid receipts."""
    root = data_dir.resolve()
    manifest, predictions = _input_path(root, manifest), _input_path(root, predictions)
    images = load_manifest(manifest, root)
    try:
        rows = load_predictions(predictions)
        # Also reject non-JSON values and unpaired surrogates in external files.
        for row in rows:
            json.dumps(vars(row), ensure_ascii=False, allow_nan=False).encode("utf-8")
        by_id = {row.id: row for row in rows}
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise ValueError("Invalid predictions file") from error
    if set(by_id) != set(images):
        raise ValueError("Prediction IDs must match manifest IDs exactly")
    return [ReviewItem(record_id, image, by_id[record_id]) for record_id, image in images.items()]
