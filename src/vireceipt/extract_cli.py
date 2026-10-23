"""Run a chosen extraction adapter on an image-only JSONL manifest."""

import argparse
import importlib
import json
import re
import sys
from pathlib import Path

from vireceipt.extraction import Extractor, extract_images, write_predictions


def _protect_test_labels(path: Path) -> None:
    if tuple(part.casefold() for part in path.parts[-3:]) == ("data", "labels", "test.jsonl"):
        raise ValueError("Frozen test labels are reserved for final evaluation")


def load_manifest(path: Path, images_root: Path | None = None) -> dict[str, Path]:
    """Validate an image-only manifest without loading any receipt labels."""
    path = path.resolve()
    _protect_test_labels(path)
    root = (images_root or path.parent).resolve()
    images = {}
    with path.open(encoding="utf-8") as stream:
        for lineno, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or set(row) != {"id", "image"}:
                raise ValueError(f"Line {lineno}: only id and image are allowed")
            record_id, name = row["id"], row["image"]
            if not isinstance(record_id, str) or not re.fullmatch(r"r[0-9]{4}", record_id):
                raise ValueError(f"Line {lineno}: id must be r followed by four digits")
            if record_id in images:
                raise ValueError(f"Line {lineno}: duplicate id")
            if not isinstance(name, str) or not name or Path(name).anchor:
                raise ValueError(f"Line {lineno}: image must be a relative path")
            image = (root / name).resolve()
            if (
                not image.is_relative_to(root)
                or image.suffix.lower() not in {".jpg", ".jpeg", ".png"}
                or not image.is_file()
            ):
                raise ValueError(f"Line {lineno}: image must be an existing JPG/PNG inside root")
            images[record_id] = image
    if not images:
        raise ValueError("Manifest is empty")
    return images


def _load_extractor(specification: str) -> Extractor:
    module, separator, function = specification.partition(":")
    if not module or not separator or not function:
        raise ValueError("Extractor must be MODULE:FUNCTION")
    try:
        extractor = getattr(importlib.import_module(module), function)
    except Exception:
        raise ValueError("Could not load extractor MODULE:FUNCTION") from None
    if not callable(extractor):
        raise ValueError("Extractor must be callable")
    return extractor


def main(argv: list[str] | None = None) -> int:
    """Validate paths, run the selected adapter and write eval-compatible predictions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="UTF-8 JSONL with only id and image")
    parser.add_argument("--extractor", required=True, help="Importable MODULE:FUNCTION adapter")
    parser.add_argument("--out", type=Path, required=True, help="Output prediction JSONL")
    parser.add_argument("--images-root", type=Path, help="Image root; default: manifest directory")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing predictions")
    args = parser.parse_args(argv)
    try:
        images = load_manifest(args.manifest, args.images_root)
        output = args.out.resolve()
        _protect_test_labels(output)
        if output == args.manifest.resolve() or output in images.values():
            raise ValueError("Output cannot replace the manifest or a source image")
        if output.is_dir() or (output.exists() and not args.overwrite):
            raise ValueError("Output exists; use --overwrite to replace predictions")
        output.parent.mkdir(parents=True, exist_ok=True)
        extractor = _load_extractor(args.extractor)
        predictions = extract_images(images, extractor)
        write_predictions(predictions, output)
    except (OSError, ValueError, UnicodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    failures = sum("error" in prediction.extra for prediction in predictions)
    print(
        f"Wrote {len(predictions)} predictions; {failures} extraction errors; all require review."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
