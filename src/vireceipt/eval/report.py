"""Turn a metrics summary and run metadata into a Markdown report."""

import subprocess
from typing import Any


def git_state() -> dict[str, Any]:
    """Current commit and whether the working tree has uncommitted changes."""

    def run(*args: str) -> str | None:
        try:
            out = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            return None
        return out.stdout.strip()

    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {"commit": commit or "unknown", "dirty": bool(status) if status is not None else None}


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def _num(x: float | None, fmt: str = "{:.0f}") -> str:
    return "—" if x is None else fmt.format(x)


def to_markdown(meta: dict[str, Any], s: dict[str, Any]) -> str:
    """Render a report. Counts are always shown next to rates: samples are small."""
    n = s["n"]
    dirty = " (uncommitted changes)" if meta["git"]["dirty"] else ""
    lines = [
        f"# Evaluation — {meta['run_name']} on `{meta['split']}`",
        "",
        "| | |",
        "|---|---|",
        f"| Model / extractor | {meta.get('model') or '—'} |",
        f"| Split | `{meta['split']}`{' (final run)' if meta.get('final') else ''} |",
        f"| Receipts | {n} |",
        f"| Commit | `{meta['git']['commit']}`{dirty} |",
        f"| Evaluated at | {meta['evaluated_at']} |",
        f"| Labels | `{meta['gold']}` |",
        f"| Predictions | `{meta['pred']}` |",
    ]
    if meta.get("lock"):
        lines.append(
            f"| Test lock | sha256 `{meta['lock']['sha256'][:12]}…` ({meta['lock']['n']} records) |"
        )
    if meta.get("rerun_reason"):
        lines.append(f"| Re-run reason | {meta['rerun_reason']} |")

    lines += [
        "",
        "## Receipt level",
        "",
        f"- Valid JSON: {s['valid_json']}/{n} ({_pct(s['valid_json_rate'])})",
        f"- All fields and items correct: {s['all_correct']}/{n} ({_pct(s['all_correct_rate'])})",
        f"- Hallucinated field values: {s['hallucinated_total']}",
        "",
        "## Fields",
        "",
        "| Field | Correct | Wrong | Missed | Hallucinated | Accuracy | Strict |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for path, f in s["fields"].items():
        strict = _pct(f["strict_accuracy"]) if "strict_accuracy" in f else ""
        lines.append(
            f"| `{path}` | {f['correct']} | {f['wrong']} | {f['missed']} | {f['hallucinated']} "
            f"| {_pct(f['accuracy'])} | {strict} |"
        )

    it = s["items"]
    lines += [
        "",
        "## Line items",
        "",
        f"Matched {it['matched']} of {it['gold']} gold and {it['predicted']} predicted items — "
        f"precision {_pct(it['precision'])}, recall {_pct(it['recall'])}, F1 {_pct(it['f1'])}.",
        "",
        "## By photo quality",
        "",
        "| Quality | Receipts | All correct | Rate |",
        "|---|---:|---:|---:|",
    ]
    for tag, q in s["by_quality"].items():
        lines.append(f"| {tag} | {q['n']} | {q['all_correct']} | {_pct(q['rate'])} |")

    ab = s["abstention"]
    lines += ["", "## Abstention", ""]
    if not ab:
        lines.append("No confidences or decisions in the predictions file.")
    if "coverage_curve" in ab:
        lines += [
            "Most confident receipts kept → share fully correct:",
            "",
            "| Coverage | Receipts | All correct | Rate |",
            "|---:|---:|---:|---:|",
        ]
        for row in ab["coverage_curve"]:
            cov, rate = _pct(row["coverage"]), _pct(row["rate"])
            lines.append(f"| {cov} | {row['n']} | {row['all_correct']} | {rate} |")
        lines.append("")
    if "decisions" in ab:
        d = ab["decisions"]
        lines += [
            f"- Auto-accepted: {d['accepted']}/{n} ({_pct(d['auto_accept_rate'])})",
            f"- Fully correct among accepted: {d['accepted_all_correct']}/{d['accepted']} "
            f"({_pct(d['accepted_accuracy'])})",
            f"- Wrong receipts sent to review: {d['wrong_sent_to_review']}/{d['wrong_receipts']} "
            f"({_pct(d['error_catch_rate'])})",
        ]

    op = s["operations"]
    lines += [
        "",
        "## Operations",
        "",
        f"- Latency p50 / p95: {_num(op['latency_ms_p50'])} / {_num(op['latency_ms_p95'])} ms "
        f"(n={op['latency_n']})",
        f"- Mean cost per receipt: {_num(op['cost_usd_mean'], '${:.5f}')} (n={op['cost_n']})",
        "",
    ]
    return "\n".join(lines)
