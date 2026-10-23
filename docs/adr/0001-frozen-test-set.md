# ADR 0001 — Store-level splits and a frozen, run-once test set

- Status: accepted
- Date: 2026-10-23

## Context

Receipts from the same store share a layout, a font and often the same items. If receipts from
one store appear in both training and test data, the test score measures memorised layouts, not
extraction. Small personal projects also tend to tune prompts and thresholds on the set they
report, which inflates results.

## Decision

1. Every labelled receipt carries a `store_id`. Splits are made by store: all receipts of a
   store belong to exactly one of `train`, `val`, `test`.
2. `test` contains only receipts photographed by the author (`source: own`), labelled in week 1
   and frozen with `vireceipt-freeze`, which commits a SHA-256 of the canonical label content to
   `locks/test.sha256`.
3. Prompts, thresholds and model choices are selected on `val` only.
4. `vireceipt-eval` scores `test` only with `--final`, only when the lock matches, and only once;
   a second run requires `--rerun-reason`, which is written into the report.

## Consequences

- The reported test numbers are lower but honest, and the protocol is visible in the code.
- With ~100 test receipts, results are reported as counts (e.g. 87/104) with the sample size,
  not as precise percentages.
- Fixing a wrong test label means re-freezing and recording the reason in the labeling guide.
