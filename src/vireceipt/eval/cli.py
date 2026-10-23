"""`vireceipt-eval`: score a predictions file against labels and write a report."""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from vireceipt.eval.io import DataError, load_gold, load_predictions
from vireceipt.eval.lock import DEFAULT_LOCK, check_lock
from vireceipt.eval.metrics import score_all, summarize
from vireceipt.eval.report import git_state, to_markdown

SPLITS = ("train", "val", "test")


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-") or "run"


def _guard_test_run(args: argparse.Namespace, out_dir: Path) -> dict | None:
    """Enforce the run-once rule for the test split. Returns the lock that was checked."""
    if args.split != "test":
        return None
    if not args.final:
        raise DataError("the test split is scored once, at the end; pass --final to do it")
    lock = check_lock(args.gold, args.lock)
    earlier = sorted(out_dir.glob("*-test.json"))
    if earlier and not args.rerun_reason:
        raise DataError(
            f"a test report already exists ({earlier[-1].name}); pass --rerun-reason to run again"
        )
    return lock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score receipt predictions against labels.")
    parser.add_argument("--gold", required=True, help="labels JSONL")
    parser.add_argument("--pred", required=True, help="predictions JSONL")
    parser.add_argument("--split", required=True, choices=SPLITS)
    parser.add_argument("--run-name", required=True, help="short name, e.g. ocr-llm-v1")
    parser.add_argument("--model", default=None, help="model / extractor version, for the report")
    parser.add_argument("--out", default="results", help="directory for reports")
    parser.add_argument("--final", action="store_true", help="required to score the test split")
    parser.add_argument("--lock", default=str(DEFAULT_LOCK), help="test-set lock file")
    parser.add_argument("--rerun-reason", default=None, help="why the test split is scored again")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    try:
        lock = _guard_test_run(args, out_dir)
        gold = load_gold(args.gold)
        preds = load_predictions(args.pred)
        summary = summarize(score_all(gold, preds)).to_dict()
    except (DataError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    now = datetime.now(UTC)
    meta = {
        "run_name": args.run_name,
        "model": args.model,
        "split": args.split,
        "final": args.final,
        "gold": Path(args.gold).as_posix(),
        "pred": Path(args.pred).as_posix(),
        "evaluated_at": now.isoformat(timespec="seconds"),
        "git": git_state(),
        "lock": lock,
        "rerun_reason": args.rerun_reason,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"{now:%Y%m%d-%H%M%S}-{_slug(args.run_name)}"
    stem, i = f"{base}-{args.split}", 2
    while (out_dir / f"{stem}.json").exists():  # never overwrite an earlier report
        stem, i = f"{base}-{i}-{args.split}", i + 1
    (out_dir / f"{stem}.json").write_text(
        json.dumps({"meta": meta, "summary": summary}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / f"{stem}.md").write_text(to_markdown(meta, summary), encoding="utf-8")

    f1 = summary["items"]["f1"]
    print(
        f"{args.run_name} on {args.split}: {summary['all_correct']}/{summary['n']} receipts fully "
        f"correct, item F1 {'—' if f1 is None else f'{f1:.3f}'}"
    )
    print(f"report: {out_dir / (stem + '.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
