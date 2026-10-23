# <MÃ> — <tên ngắn>

| | |
|---|---|
| Người làm | Codex / chủ repo |
| Phụ thuộc | <MÃ khác> hoặc — |
| Ước lượng | <giờ> |
| Đợt / nhánh | `wave/<tên-đợt>` (task lẻ: `<loại>/<MÃ>-<mô-tả>`) |

## Mục tiêu

Một đến ba câu: làm xong thì có gì, dùng để làm gì.

## Bối cảnh cần đọc

- `<file>` — vì sao cần đọc

## Được phép sửa

- `<đường dẫn>` (tạo mới / sửa)

Mọi file khác: không sửa. Cần sửa thì dừng task này và hỏi trong bàn giao.

## Quyết định đã chốt

Chốt trước khi giao để Codex không phải dừng giữa đợt. Rà các chỗ biên task này đụng tới: làm tròn,
giá trị thiếu (`null`), danh sách rỗng, Unicode/hoa thường, ngày và múi giờ, thông báo lỗi tiếng gì,
mức `error` hay `warning`.

- <vấn đề> → <cách làm đã chốt> (<ngày>, <ai chốt>)

Quyết định thêm sau review cũng ghi ở đây.

## Các bước

1. …

## Tiêu chí xong

- [ ] … (đo được: lệnh nào chạy ra gì, test nào phải có)
- [ ] `uv run ruff check .` sạch, `uv run pytest` xanh
- [ ] Bàn giao trong `docs/handoffs/` có kết quả lệnh

## Ngoài phạm vi

- … (những thứ dễ bị làm lan sang nhưng không thuộc task này)
