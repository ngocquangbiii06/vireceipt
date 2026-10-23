# locks/

`test.sha256` is written by `uv run vireceipt-freeze data/labels/test.jsonl` and committed. It
holds a hash of the frozen test labels; `vireceipt-eval --split test --final` refuses to run if
the labels no longer match. See [ADR 0001](../docs/adr/0001-frozen-test-set.md).
