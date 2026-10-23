# data/

Everything in this folder except this file is git-ignored: receipt images and labels are never
committed.

```
data/
  raw/            original photos and downloaded datasets, untouched
  images/         images used for labelling (personal data blacked out)
  labels/
    train.jsonl   one labelled receipt per line, see docs/labeling-guide.md
    val.jsonl
    test.jsonl    own receipts only, frozen (hash in locks/test.sha256)
```

Rules:
- Split by `store_id`, never by image (docs/adr/0001-frozen-test-set.md).
- Record where every external dataset came from and under which licence before using it.
