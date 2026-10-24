# ViReceipt

Vietnamese receipt extraction that checks its own output and says when it is not sure.

ViReceipt reads a phone photo of a Vietnamese retail receipt and returns structured JSON
(seller, date, line items, subtotal, discount, VAT, total). A verification layer checks the
arithmetic and the evidence behind every value; when a check fails or confidence is low, the
receipt goes to a human reviewer instead of being accepted silently.

> **Status: extraction pipeline implemented; no benchmark results yet.** The schema, labeling
> tools, evaluation harness and a configurable VLM API adapter exist. Every benchmark number
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
# Optional CPU OCR baseline (downloads dependencies; first use also downloads model weights)
# uv sync --group ocr
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run vireceipt-check-labels tests/fixtures/gold.jsonl
uv run --group label streamlit run src/vireceipt/labeling/app.py -- --data data
uv run vireceipt-extract --help

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

## Running an extraction adapter

The runner and CLI include a configurable VLM Chat Completions adapter. It has been tested
against a local HTTP stub; **live provider compatibility and extraction accuracy are unmeasured**.
Additional backends can provide an importable Python callable with this contract:

```python
from pathlib import Path
from vireceipt.extraction import ExtractionResult


def extract(image: Path) -> ExtractionResult:
    # Call your backend with the image, then return its raw JSON output.
    # Supply confidence/cost_usd only when the backend provides them.
    ...
```

Create an image-only UTF-8 JSONL manifest, such as `data/manifest.jsonl`:

```json
{"id":"r0001","image":"images/r0001.jpg"}
{"id":"r0002","image":"images/r0002.png"}
```

```bash
# my_backend.extract must implement the contract above and be importable
uv run vireceipt-extract data/manifest.jsonl --extractor my_backend:extract \
    --out data/predictions/baseline.jsonl
```

Images must be JPG/PNG files inside the manifest directory, or an explicit `--images-root`.
The manifest accepts only unique IDs (`r` plus four digits) and relative image paths; labels
are rejected. `--overwrite` is required to replace an existing prediction file. The manifest,
source images and frozen `data/labels/test.jsonl` cannot be overwritten.

Every prediction currently has `decision: "review"`. Missing confidence/cost stays `null`;
latency measures the adapter call. Schema-invalid JSON is retained with `schema_valid: false`.
An adapter failure produces a null receipt and an error code; later images still run, the
output is written atomically, and the CLI exits with code 1. A schema-invalid output alone
does not change the exit code. Score the resulting JSONL with `vireceipt-eval` as above.

The runner also writes `verification_issues`, a list of `{code, severity, message}` objects.
It checks schema, arithmetic (including half-up rounding), calendar dates, future/old dates,
and missing seller/date/total/items. Missing numbers skip arithmetic checks; absent discount/VAT
count as zero in the subtotal-to-total check. Numbers are preserved when checks disagree.
Verification issues alone do not change the CLI exit code or trigger automatic acceptance.
The OCR+LLM adapter also checks normalized presence of populated fields in its OCR transcript.
Predictions include `grounding: {checked, unsupported_fields}` and a `not_grounded` warning for
each unsupported path. The transcript itself is not written into predictions. Without OCR (the
VLM adapter's default), or when the schema is invalid, `checked` is false.

Text checks preserve Vietnamese accents and word boundaries; numbers, dates, times and contact
numbers allow common printed formats. Null fields and contract constants need no evidence.
Presence does not prove field alignment or OCR/model correctness: a value can occur elsewhere,
and unsupported printing formats can cause warnings. An empty issue list is not proof of
correctness. A measured acceptance policy is still needed; all current outputs require review.

For the built-in VLM adapter, configure a vision model on a compatible endpoint (PowerShell):

```powershell
$env:VIRECEIPT_VLM_BASE_URL = "http://127.0.0.1:8000/v1"
$env:VIRECEIPT_VLM_MODEL = "your-served-vision-model"
# Set VIRECEIPT_VLM_API_KEY through your environment if the endpoint requires authentication.
uv run vireceipt-extract data/manifest.jsonl --extractor vireceipt.extractors.chat_vlm:extract `
    --out data/predictions/vlm.jsonl
```

The endpoint and model are required; the CLI does not start a model server or choose a provider.
HTTPS is required for remote endpoints; HTTP is allowed for loopback servers. Images must be
JPG/PNG with matching file signatures, at most 10 MiB each. The adapter sends them as base64
data URIs with the versioned `receipt-v1` zero-shot prompt and the current output schema.
It does not repair inconsistent totals or invent unreadable values.

`VIRECEIPT_VLM_TIMEOUT` defaults to 60 seconds and `VIRECEIPT_VLM_MAX_TOKENS` to 4096.
Responses must finish with `stop`; refusals, truncation, HTTP/network errors and responses over
4 MiB fail that image. Requests are never retried or redirected. Confidence and cost remain null.
Provider billing, quotas, model/JSON-mode support and accuracy need verification on `val` before
reporting any baseline. The adapter follows the [Chat Completions protocol](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
also used in [Qwen's serving examples](https://github.com/QwenLM/Qwen3-VL).

CPU OCR is an optional dependency group:

```bash
uv sync --group ocr
uv run --group ocr python -c "from pathlib import Path; from vireceipt.ocr import read_text; print(read_text(Path('data/images/r0001.jpg')))"
```

It uses PaddleOCR 3.3.3, PaddlePaddle 3.3.1, `PP-OCRv5_mobile_det` and
`latin_PP-OCRv5_mobile_rec`. The engine defaults to CPU; `VIRECEIPT_OCR_DEVICE` can select
another supported device explicitly. Orientation/unwarping modules are disabled in this baseline.
oneDNN is also disabled to avoid a Paddle 3.3.1 CPU inference error reproduced on Windows.
Models download to Paddle's cache on first use and are never committed. Package and model-card
licenses are Apache-2.0 ([PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE),
[PaddlePaddle](https://github.com/PaddlePaddle/Paddle/blob/develop/LICENSE),
[detection model](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det),
[recognition model](https://huggingface.co/PaddlePaddle/latin_PP-OCRv5_mobile_rec)).
OCR text keeps line order and empty lines. OCR scores are not receipt-level confidence.

For baseline A, send the local OCR transcript to a text model (PowerShell):

```powershell
$env:VIRECEIPT_LLM_BASE_URL = "http://127.0.0.1:8000/v1"
$env:VIRECEIPT_LLM_MODEL = "your-served-text-model"
# Set VIRECEIPT_LLM_API_KEY through your environment when required.
uv run --group ocr vireceipt-extract data/manifest.jsonl --extractor vireceipt.extractors.ocr_llm:extract `
    --out data/predictions/ocr-llm.jsonl
```

This adapter sends only OCR text to the LLM; images stay in the local OCR stage. Blank OCR
fails the image without an LLM request. Configure `VIRECEIPT_LLM_TIMEOUT` (default 60 seconds)
and `VIRECEIPT_LLM_MAX_TOKENS` (default 4096) as needed. The same JSON parsing, no-retry,
review-only decisions and null confidence/cost rules apply. End-to-end transport tests use
a local HTTP stub; neither adapter has been benchmarked on real receipts.

## Reviewing and correcting predictions

The local review app shows the source image, raw prediction and verification metadata beside
a JSON editor. Schema-invalid or null predictions start with a blank receipt template. Run:

```bash
uv run --group label streamlit run src/vireceipt/review_app.py -- --data data \
    --manifest manifest.jsonl --pred predictions/baseline.jsonl
```

Manifest/prediction paths are relative to `--data` (absolute paths inside it also work); inputs
under `labels/` are refused. Every manifest ID must have exactly one prediction. Choose the image's
source, quality tags and `store_id` explicitly. Existing corrections reload when revisiting an ID.

Saving checks strict JSON, the output schema, arithmetic and dates. Printed inconsistencies are
preserved and reported for inspection. Original OCR warnings remain in the model-output view;
corrections are checked without the original transcript. The app never changes predictions or
accepts a receipt automatically. Corrections are atomically upserted by ID in
`data/review/corrections.jsonl` as candidate labels, separate from all/train/val/test. Dataset
promotion and store-based splitting remain manual. This app supports one local writer at a time.

## Local extraction API

Install the optional API group and select the server's backend (PowerShell):

```powershell
uv sync --group api
$env:VIRECEIPT_API_BACKEND = "vlm" # or "ocr-llm" (also needs --group ocr)
# Configure the corresponding VIRECEIPT_VLM_* or VIRECEIPT_LLM_* variables shown above.
uv run --group api uvicorn vireceipt.api:create_app --factory --host 127.0.0.1 --workers 1
curl.exe "http://127.0.0.1:8000/v1/extract?receipt_id=r0001" `
    -H "Content-Type: image/png" --data-binary "@data/images/r0001.png"
```

`GET /healthz` reports process liveness; model configuration and reachability are checked on
extraction, without paid health probes. `POST /v1/extract` takes a required `receipt_id` (`r` plus
four ASCII digits) and a raw JPEG/PNG body with matching Content-Type. The body is streamed with
a 10 MiB bound; Pillow checks one frame, at most 25 million pixels, and decodes it before inference.
The backend runs in a thread pool, one call at a time per app; temporary images are removed after
each request. The server chooses its backend through environment configuration.

The response is the same flat prediction object used by the eval harness, including verification
issues and grounding metadata. Every decision remains `review`. Invalid schema alone returns 200
with the raw receipt; backend/metadata failures return 502 with a null receipt and a sanitized
error code. Bad IDs/images use 4xx responses; upload limits use 413. No transcript is included.

Without database configuration this is a stateless interface. To keep uploaded images and
prediction snapshots, install the storage group and set a server-owned PostgreSQL URL:

```powershell
uv sync --group api --group storage
# Set VIRECEIPT_DATABASE_URL through your environment, for example:
# postgresql://USER:PASSWORD@HOST:5432/DATABASE (percent-encode credentials as needed).
# Then start the same Uvicorn factory above, with the database already provisioned.
```

Startup initializes the request table/index idempotently; connection/configuration errors stop
startup. Local database connections can be plain; remote hosts require certificate-verified TLS.
Each extraction gets a new UUID `job_id` after the original image and prediction are committed,
including invalid model output and backend failures. Reusing a receipt ID creates another job.
The original snapshot keeps its prediction fields; `job_id` is added only to the HTTP response.
Storage failures return 503 `storage_unavailable`; there is no automatic retry or idempotency key,
so a client retry may invoke and bill the model again. No storage failure is returned as a durable
success. Temporary-image failures use 503 `temporary_storage_unavailable`.

Run this API on loopback: authentication and public deployment are still planned. Tests use
synthetic images, PostgreSQL, local Chat API stubs and a real loopback Uvicorn server;
live provider compatibility and extraction accuracy remain unmeasured. The raw-body route uses
[FastAPI's Request interface](https://fastapi.tiangolo.com/advanced/using-request-directly/).

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
