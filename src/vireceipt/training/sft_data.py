"""Export unfrozen training/validation labels into portable image conversations."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from vireceipt.eval.io import GoldRecord, load_gold
from vireceipt.extractors.receipt_json import PROMPT_VERSION, build_prompt


def to_example(record: GoldRecord, image_rel: str) -> dict[str, Any]:
    """Pair the inference prompt and image path with the unchanged canonical gold JSON."""
    return {
        "id": record.id,
        "prompt_version": PROMPT_VERSION,
        "image": image_rel,
        "messages": [
            {"role": "system", "content": build_prompt()},
            {"role": "user", "content": [{"type": "image", "image": image_rel}]},
            {
                "role": "assistant",
                "content": json.dumps(
                    record.receipt,
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
            },
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Validate all paths before exporting atomically; never open a test.jsonl label file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path)
    parser.add_argument("--images-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--skip-missing", action="store_true")
    args = parser.parse_args(argv)
    temporary = None
    try:
        for path in (args.labels, args.out):
            if (
                path.name.casefold() == "test.jsonl"
                or path.resolve().name.casefold() == "test.jsonl"
            ):
                raise ValueError("test.jsonl is reserved for final evaluation")
        source, output, root = args.labels.resolve(), args.out.resolve(), args.images_root.resolve()
        if output == source:
            raise ValueError("Output cannot replace source labels")
        records = load_gold(source)
        examples, image_paths, skipped = [], set(), 0
        for record in records:
            name = record.image
            if name is None or name == "":
                if args.skip_missing:
                    skipped += 1
                    continue
                raise ValueError(f"image_missing: {record.id}")
            if not isinstance(name, str) or Path(name).anchor:
                raise ValueError("Image must be a relative path inside images-root")
            image = (root / name).resolve()
            if not image.is_relative_to(root):
                raise ValueError("Image must stay inside images-root")
            image_paths.add(image)
            if not image.is_file():
                if args.skip_missing:
                    skipped += 1
                    continue
                raise ValueError(f"image_missing: {record.id}")
            examples.append(to_example(record, Path(name).as_posix()))
        if output in image_paths:
            raise ValueError("Output cannot replace a source image")
        payload = "".join(
            json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in examples
        ).encode("utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        os.replace(temporary, output)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(
        f"Wrote {len(examples)} examples; skipped {skipped} missing images; "
        f"prompt {PROMPT_VERSION}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
