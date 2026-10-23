# Task

Trạng thái: `todo` → `doing` → `review` → `done`. Codex đổi trạng thái dòng của mình; chủ repo đổi
sang `done` khi merge.

## Tuần T1 — dữ liệu và tập test (09/11 – 15/11/2026)

| Mã | Việc | Người làm | Phụ thuộc | Trạng thái |
|---|---|---|---|---|
| [T1-01](T1-01.md) | Kiểm tra giấy phép và cấu trúc nguồn dữ liệu, mô hình | Chủ repo (+AI tra cứu) | — | doing |
| [T1-02](T1-02.md) | Hàm kiểm tra nhất quán nhãn + lệnh `vireceipt-check-labels` | Codex | — | review |
| [T1-03](T1-03.md) | Chia tập theo cửa hàng: lệnh `vireceipt-split` | Codex | — | review |
| [T1-04](T1-04.md) | App gán nhãn (Streamlit) | Codex | T1-02 | review |
| [T1-05](T1-05.md) | Chụp, che, gán nhãn ≥100 hóa đơn; chia tập; đóng băng `test` | Chủ repo | T1-02, T1-03, T1-04 | todo |

## Đợt

Mỗi đợt làm trên một nhánh `wave/<tên-đợt>`, review bằng `/review-batch`, merge một lần (AGENTS.md §6).

| Đợt | Nhánh | Task (theo thứ tự) | Trạng thái |
|---|---|---|---|
| T1-1 | `wave/T1-1` | T1-02 (sửa sau review), T1-03, T1-04 | review |
| T2-1 | `wave/T2-1` (nối từ `wave/T1-1`) | T2-01, T2-02 | review |
| T2-2 | `wave/T2-2` (nối từ `wave/T2-1`) | T2-03, T2-04, T2-05 | review |
| T2-3 | `wave/T2-3` (nối từ `wave/T2-2`) | T2-06, T2-07 | review |
| T3-1 | `wave/T3-1` (nối từ `wave/T2-3`) | T3-01, T3-02 | review |
| T3-2 | `wave/T3-2` (nối từ `wave/T3-1`) | T3-03, T3-04 | review |
| T6-1 | `wave/T6-1` (nối từ `wave/T3-2`) | T6-01, T6-02, T6-03 | review |

## Sau T1

Chủ repo cho phép làm trước phần độc lập dữ liệu và tự review ngày 2026-10-23.
Các task chọn dữ liệu/train vẫn chờ kết luận T1-01 và dữ liệu thật của T1-05.

| Mã | Việc | Người làm | Phụ thuộc | Trạng thái |
|---|---|---|---|---|
| [T2-01](T2-01.md) | Hợp đồng extractor, runner và writer prediction | Codex | Eval harness hiện có | review |
| [T2-02](T2-02.md) | CLI manifest ảnh và adapter extractor | Codex | T2-01 (cùng đợt) | review |
| [T2-03](T2-03.md) | Prompt hóa đơn và parse JSON model | Codex | T2-01/T2-02 (nhánh cha) | review |
| [T2-04](T2-04.md) | HTTP client Chat Completions | Codex | — | review |
| [T2-05](T2-05.md) | Backend VLM ảnh qua Chat API | Codex | T2-03, T2-04 | review |
| [T2-06](T2-06.md) | PaddleOCR CPU đọc văn bản | Codex | T2-2 (nhánh cha) | review |
| [T2-07](T2-07.md) | Baseline OCR + LLM | Codex | T2-06 | review |

## Verifier

| Mã | Việc | Người làm | Phụ thuộc | Trạng thái |
|---|---|---|---|---|
| [T3-01](T3-01.md) | Verifier schema/số học/ngày/thiếu dữ kiện | Codex | T1-02, T2-3 (nhánh cha) | review |
| [T3-02](T3-02.md) | Tích hợp verifier vào prediction | Codex | T3-01 | review |
| [T3-03](T3-03.md) | Grounding bằng normalized presence | Codex | T3-1 (nhánh cha) | review |
| [T3-04](T3-04.md) | Truyền OCR evidence tới prediction | Codex | T3-03 | review |

## Vòng review thủ công (phần độc lập dữ liệu làm trước)

| Mã | Việc | Người làm | Phụ thuộc | Trạng thái |
|---|---|---|---|---|
| [T6-01](T6-01.md) | Hàng đợi review ảnh/prediction | Codex | T3-2 (nhánh cha) | review |
| [T6-02](T6-02.md) | Lưu bản sửa riêng | Codex | T6-01 | review |
| [T6-03](T6-03.md) | Giao diện review | Codex | T6-01, T6-02 | review |
