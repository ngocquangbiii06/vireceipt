# AGENTS.md — luật cho mọi AI agent (Codex, Claude Code…) làm việc trong ViReceipt

Codex tự đọc file này; Claude Code đọc qua `CLAUDE.md`. Giữ file ngắn và đúng.

## 1. Dự án trong 30 giây

ViReceipt đọc ảnh hóa đơn bán lẻ tiếng Việt thành JSON, **tự kiểm tra số liệu và biết từ chối khi
không chắc**. Đây là project portfolio cá nhân: mọi con số công bố phải chạy ra từ code trong repo.

Chia vai:
- **Codex**: nhận task card, viết code + test, chạy kiểm tra, ghi bàn giao.
- **Claude**: viết task card, review diff (`/review-task`). Claude **không sửa code** trên nhánh của
  Codex.
- **Chủ repo** (người): duyệt kế hoạch, merge vào `main`.

## 2. Đọc gì trước khi làm (theo thứ tự)

1. `docs/tasks/README.md` — bảng task và trạng thái.
2. Task card được giao: `docs/tasks/<MÃ>.md`.
3. Bàn giao gần nhất của task đó (nếu có): `docs/handoffs/*-<MÃ>-*.md`.
4. Kết quả review gần nhất (nếu có): `.reviews/<MÃ>.md`.
5. Khi task cần: `README.md` (spec), `docs/labeling-guide.md`, `docs/adr/`.

## 3. Bản đồ repo

```
src/vireceipt/
  schemas/receipt.schema.json   hợp đồng đầu ra (JSON Schema)
  schema.py  normalize.py       validate schema; chuẩn hóa chữ và số tiền
  eval/                         metric, báo cáo, khóa tập test, CLI vireceipt-eval / vireceipt-freeze
tests/                          pytest + fixtures tổng hợp (không phải dữ liệu thật)
docs/tasks/                     task card + bảng trạng thái
docs/handoffs/                  bàn giao, mỗi lần một file
docs/adr/                       quyết định thiết kế
data/                           ảnh + nhãn — KHÔNG commit
locks/  results/                hash tập test; báo cáo eval — có commit
.reviews/                       kết quả review của Claude — không commit
```

## 4. Lệnh

```bash
uv sync                                   # cài
uv run ruff format . && uv run ruff check .
uv run pytest
uv run vireceipt-eval --help
uv run vireceipt-freeze --help
```

## 5. Luật bắt buộc

1. **Chỉ sửa file nằm trong mục "Được phép sửa" của task card.** Cần sửa file khác: dừng lại, ghi
   vào mục "Câu hỏi" của bàn giao.
2. **Không commit** ảnh, nhãn, dữ liệu, trọng số mô hình, `.env`, khóa API. `data/` đã bị ignore — không
   dùng `git add -f`.
3. **Không đọc, in hay phân tích nhãn tập test** (`data/labels/test.jsonl`), không chọn ngưỡng/prompt/mô
   hình theo nó. Chỉ `vireceipt-eval --split test --final` được chạm vào tập test, và chỉ khi task yêu cầu.
4. **Không sửa** schema, `docs/adr/`, `docs/labeling-guide.md`, `locks/`, `results/` trừ khi task card
   cho phép rõ.
5. **Không bịa số liệu.** README hay tài liệu chỉ được ghi con số có trong một báo cáo ở `results/`.
6. **Giấy phép:** không chép code GPL/AGPL/LGPL hay repo không có giấy phép. Code MIT/Apache chép về
   phải giữ dòng giấy phép và ghi vào `THIRD_PARTY.md`. Thêm thư viện mới thì ghi giấy phép của nó
   trong bàn giao.
7. **Không làm việc trên `main`.** Không merge, không push `--force`, không sửa lịch sử git.
8. **Diff nhỏ.** Một task nên dưới khoảng 300 dòng thay đổi (không tính file khóa `uv.lock`). Lớn hơn
   thì đề xuất tách task.

## 6. Quy trình một task (Codex)

1. Đọc mục 2. Kiểm tra task ở trạng thái `todo` và các task phụ thuộc đã `done`.
2. **Tóm tắt kế hoạch** (các bước, file sẽ sửa, câu hỏi còn mở). **Chưa code cho tới khi chủ repo
   đồng ý.**
3. Tạo nhánh `<loại>/<MÃ>-<mô-tả-ngắn>` từ `main`, ví dụ `feat/T1-03-label-checks`.
4. Làm từng bước nhỏ; commit theo Conventional Commits có mã task:
   `feat(labeling): add arithmetic checks [T1-03]`.
5. Viết test cho logic mới. Chạy `uv run ruff format . && uv run ruff check . && uv run pytest`.
6. Đánh dấu tiêu chí đã xong trong task card; đổi trạng thái task trong `docs/tasks/README.md` thành
   `review`.
7. **Ghi bàn giao** từ `docs/handoffs/_template.md` thành
   `docs/handoffs/<YYYY-MM-DD-HHMM>-<MÃ>-codex.md`, **dán nguyên văn** kết quả lệnh kiểm tra. Commit.
8. Dừng. Báo chủ repo nhờ Claude chạy `/review-task <MÃ> <nhánh>`.

**Sửa sau review:** đọc `.reviews/<MÃ>.md`, sửa hết mục **Phải sửa** (và **Nên sửa** nếu hợp lý),
chạy lại kiểm tra, thêm một mục "Sửa sau review" vào cuối file bàn giao, commit, báo lại.

## 7. Định nghĩa XONG

- [ ] Đạt hết tiêu chí trong task card.
- [ ] Có test cho logic mới; `ruff` sạch; `pytest` xanh.
- [ ] Chỉ sửa file được phép; không có dữ liệu, trọng số, bí mật trong commit.
- [ ] README/tài liệu đã cập nhật nếu hành vi thay đổi.
- [ ] Có file bàn giao với kết quả lệnh thật; trạng thái task đã đổi.

## 8. Khi không chắc

Không đoán. Ghi câu hỏi vào mục "Câu hỏi" của bàn giao và dừng. Ưu tiên giải pháp đơn giản, chạy được.

## 9. Phong cách

Python 3.12, type hints, docstring ngắn cho hàm công khai, `ruff`, `pytest`. Tên biến và code tiếng
Anh; tài liệu cho chủ repo bằng tiếng Việt; README bằng tiếng Anh.
