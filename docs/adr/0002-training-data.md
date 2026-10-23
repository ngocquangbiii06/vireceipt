# ADR 0002 — Nguồn dữ liệu huấn luyện và nhãn dòng hàng

- Status: proposed — chờ bằng chứng truy cập, kiểm mẫu và quyết định của chủ repo
- Date: 2026-10-23

## Context

ViReceipt cần nhãn dòng hàng theo schema, trong khi các tài liệu gốc MC-OCR và UIT-MLReceipts
được tra cứu mô tả nhãn các trường tổng quát của hóa đơn. Quyền train và phát hành weights từ
các nguồn này chưa được xác minh đầy đủ. Bằng chứng và liên kết ở [docs/data-sources.md](../data-sources.md).

Viet-Receipt-VQA chưa truy cập được; chủ repo xác nhận chưa có quyền. Chưa kiểm 30 mẫu,
chưa có đo lường chất lượng nhãn dòng hàng để làm căn cứ chọn phương án.

## Decision

**Chưa chốt phương án huấn luyện.** Chủ repo chọn sau khi đọc điều khoản và kết quả kiểm mẫu.

| Phương án cần quyết | Điều kiện trước khi áp dụng | Hệ quả dự kiến |
|---|---|---|
| (a) Lọc nhãn Viet-Receipt-VQA | Có quyền truy cập, điều khoản phù hợp và kết quả kiểm 30 mẫu | Có thể tận dụng nhãn sẵn; phải xác định cách lọc từ chất lượng được kiểm thực tế. |
| (b) Tự gán dòng hàng cho một phần MC-OCR | Có quyền dùng/sửa nhãn phù hợp và kế hoạch gán nhãn được duyệt | Tăng công gán nhãn; kiểm soát được quy ước dòng hàng. |
| (c) Fine-tune các trường tổng quát MC-OCR; dùng model gốc cho dòng hàng | Có quyền train/phát hành phù hợp; xác nhận nhãn không bao gồm dòng hàng | Giảm phần nhãn phải tự tạo; chất lượng dòng hàng của model gốc cần đánh giá riêng trên val. |

Không thực hiện train hoặc công bố weights dựa vào ADR đang đề xuất này.
Giấy phép base model không giải quyết thay giấy phép dữ liệu.

## Consequences

- T1-01 giữ `doing`, bị chặn ở quyền truy cập, kiểm 30 mẫu và quyết định của chủ repo.
- Chưa đạt điều kiện viết task train phụ thuộc lựa chọn nguồn dữ liệu cho T2–T5.
- Tập test riêng vẫn theo ADR 0001; không mở hoặc phân tích nhãn test để quyết định hướng train.
