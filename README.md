# ViReceipt

Vietnamese receipt extraction that checks its own output and says when it is not sure.

ViReceipt reads a phone photo of a Vietnamese retail receipt and returns structured JSON
(seller, date, line items, subtotal, discount, VAT, total). A verification layer checks the
arithmetic and the evidence behind every value; when a check fails or confidence is low, the
receipt goes to a human reviewer instead of being accepted silently.

> **Status: week 0 — scaffolding.** The output schema, the labeling guide and the evaluation
> harness exist; no extractor has been built and **there are no results yet**. Every number
> that appears in this README later will come from a report in `results/`, with the commit,
> model version and sample count.

## Why this project

Reading receipts is not new (see the MC-OCR 2021 challenge). What this project adds:

1. **Abstention with a measured guarantee.** The goal is a statement a business can use:
   "at the chosen threshold the system accepts X% of receipts on its own, and Y% of those are
   fully correct; the rest go to review." The threshold is chosen on `val`, reported on `test`.
2. **A real-world test set.** 100+ receipts photographed by the author, split by store, frozen
   in week 1 and run **once** at the end.
3. **Cost and latency next to accuracy.** A fine-tuned ~2B vision-language model is compared
   with an OCR + LLM pipeline and a commercial VLM API on accuracy, cost per receipt and latency.
4. **A closed loop.** Corrections made in the review UI are stored as new training data.

## Architecture (planned)

```
photo ──► preprocess (rotate, crop, quality score)
      ──► extractor, one of:
            A. PaddleOCR + LLM
            B. commercial VLM API (reference for accuracy and cost)
            C. ~2B VLM fine-tuned with QLoRA          ← main model
      ──► JSON (schemas/receipt.schema.json)
      ──► verifier: schema, arithmetic, date, grounding in OCR text, confidence
      ──► accept  |  flag fields  |  send to human review
      ──► FastAPI + PostgreSQL + review UI (corrections saved) + n8n workflow template
```

## Output schema

Defined in [`src/vireceipt/schemas/receipt.schema.json`](src/vireceipt/schemas/receipt.schema.json).
Money is an integer number of đồng. `null` means the field is not printed on the receipt or
cannot be read. Example:

```json
{
  "schema_version": "1.0",
  "seller": {"name": "Cửa hàng Minh Anh", "address": "12 Lý Thường Kiệt, Q.10, TP.HCM",
             "phone": null, "tax_code": null},
  "issued_at": {"date": "2026-11-12", "time": "18:42"},
  "items": [
    {"name": "Sữa tươi 1L", "quantity": 2, "unit_price": 32000, "amount": 64000},
    {"name": "Bánh mì sandwich", "quantity": 1, "unit_price": 25000, "amount": 25000}
  ],
  "subtotal": 89000, "discount": 0, "vat": null, "total": 89000,
  "currency": "VND", "payment_method": "cash"
}
```

## Evaluation protocol

- **Splits by store**, never by image, so the model cannot memorise a store's layout
  ([ADR 0001](docs/adr/0001-frozen-test-set.md)).
- **The test set is frozen** with `vireceipt-freeze` (a hash of its canonical content is
  committed in `locks/`). `vireceipt-eval` refuses to score `test` unless the hash matches,
  `--final` is passed, and no earlier test report exists (or a re-run reason is recorded).
- **Metrics** (`src/vireceipt/eval/metrics.py`):
  - per field: accuracy, wrong, missed, hallucinated (value predicted where the receipt has none);
  - line items: precision, recall, F1 (name similarity ≥ 0.8 and the same amount);
  - per receipt: valid JSON rate, all-fields-correct rate, results by photo quality;
  - abstention: all-correct rate among the most confident 100/90/80/70/50% of receipts,
    auto-accept rate, accuracy of accepted receipts, share of wrong receipts sent to review;
  - operations: p50/p95 latency, mean cost per receipt.
- Every report records the git commit, the model, the split, the sample count and the time.

How to label: [docs/labeling-guide.md](docs/labeling-guide.md). Data layout: [data/README.md](data/README.md).

## Quickstart

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .

# score predictions against labels (fixtures shown; real data lives in data/, not in git)
uv run vireceipt-eval --gold tests/fixtures/gold.jsonl --pred tests/fixtures/pred.jsonl \
    --split val --run-name demo --out results/
```

Prediction files are JSON Lines, one object per receipt:

```json
{"id": "r0001", "receipt": {...} , "confidence": 0.93, "decision": "accept",
 "latency_ms": 840, "cost_usd": 0.0004}
```

Only `id` and `receipt` are required; `receipt` may be `null` when extraction failed.

## Repository layout

```
src/vireceipt/
  schemas/receipt.schema.json   output contract
  schema.py                     schema loading and validation
  normalize.py                  text and money normalisation
  eval/                         metrics, report, test-set lock, CLIs
tests/                          unit tests and small synthetic fixtures
docs/labeling-guide.md          how to label a receipt
docs/adr/                       design decisions
docs/tasks/  docs/handoffs/     task cards and handoffs (AI-assisted workflow, see AGENTS.md)
data/                           images and labels (git-ignored)
locks/                          committed hash of the frozen test set
results/                        committed evaluation reports
```

Planned in later weeks: `extractors/`, `verify.py`, `api/`, `review_ui/`, `training/`, `n8n/`.

## Roadmap

- [ ] W1 — check data and model licences, collect and label 100+ own receipts, freeze `test`
- [ ] W2 — baselines A (OCR + LLM) and B (VLM API) on `val`
- [ ] W3 — verifier and abstention; coverage/accuracy curve on `val`
- [ ] W4–5 — QLoRA fine-tune of a ~2B VLM on a Kaggle T4, tracked in MLflow; error analysis
- [ ] W6 — serving, FastAPI, PostgreSQL, review UI, Docker Compose
- [ ] W7 — public demo, n8n template, latency and accept-rate monitoring
- [ ] W8 — single final run on `test`, report, model card, demo video

## Data and licences

Candidate training data: MC-OCR 2021 receipt images and the derived `5CD-AI/Viet-Receipt-VQA`
dataset. **Their licences have not been checked yet** (week 1). No dataset, image or model
weight is committed to this repository. Third-party code, if any is copied, will be listed with
its licence in `THIRD_PARTY.md`.

## License

MIT — see [LICENSE](LICENSE).
