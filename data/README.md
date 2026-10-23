# data/

Everything in this folder except this file is git-ignored: receipt images and labels are never
committed.

```
data/
  raw/            original photos and downloaded datasets, untouched
  images/         images used for labelling (personal data blacked out)
  labels/
    all.jsonl     all labels before store-level splitting
    train.jsonl   one labelled receipt per line, see docs/labeling-guide.md
    val.jsonl
    test.jsonl    own receipts only, frozen (hash in locks/test.sha256)
```

Rules:
- Run `uv run vireceipt-split data/labels/all.jsonl --out-dir data/labels` to split labels by store.
- Split by `store_id`, never by image (docs/adr/0001-frozen-test-set.md).
- Record where every external dataset came from and under which licence before using it.
