# Task

Trạng thái: `todo` → `doing` → `review` → `done`. Codex đổi trạng thái dòng của mình; chủ repo đổi
sang `done` khi merge.

## Tuần T1 — dữ liệu và tập test (09/11 – 15/11/2026)

| Mã | Việc | Người làm | Phụ thuộc | Trạng thái |
|---|---|---|---|---|
| [T1-01](T1-01.md) | Kiểm tra giấy phép và cấu trúc nguồn dữ liệu, mô hình | Chủ repo (+AI tra cứu) | — | todo |
| [T1-02](T1-02.md) | Hàm kiểm tra nhất quán nhãn + lệnh `vireceipt-check-labels` | Codex | — | doing |
| [T1-03](T1-03.md) | Chia tập theo cửa hàng: lệnh `vireceipt-split` | Codex | — | todo |
| [T1-04](T1-04.md) | App gán nhãn (Streamlit) | Codex | T1-02 | todo |
| [T1-05](T1-05.md) | Chụp, che, gán nhãn ≥100 hóa đơn; chia tập; đóng băng `test` | Chủ repo | T1-02, T1-03, T1-04 | todo |

T1-02 và T1-03 không đụng file của nhau, làm song song được (hai nhánh riêng).

## Sau T1

Viết task card tuần T2 (baseline OCR + LLM, VLM API) khi T1-01 đã có kết luận về dữ liệu.
