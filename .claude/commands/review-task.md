---
description: Review nhánh của một task bằng subagent reviewer (model rẻ), lưu kết quả cho Codex đọc
argument-hint: <MÃ-TASK> <nhánh>
---

Review task với tham số: `$ARGUMENTS` (dạng `<MÃ> <nhánh>`, ví dụ `T1-02 feat/T1-02-label-checks`).

1. Thiếu mã task hoặc nhánh thì hỏi lại, dừng.
2. Kiểm tra `docs/tasks/<MÃ>.md` tồn tại.
3. Chạy `git rev-parse --abbrev-ref HEAD`. Nếu khác `<nhánh>`: **không tự chuyển nhánh** (Codex có thể
   đang làm). Bảo chủ repo chạy `git switch <nhánh>` khi Codex đã dừng, rồi gọi lại lệnh này. Dừng.
4. Lấy commit đang review: `git log -1 --format=%h <nhánh>`.
5. Giao cho subagent `reviewer`: "Review task `<MÃ>` trên nhánh `<nhánh>` theo hướng dẫn của bạn."
   Không tự đọc diff trong phiên chính — để tiết kiệm, mọi việc đọc nằm trong subagent.
6. Ghi kết quả của subagent **nguyên văn** vào `.reviews/<MÃ>.md` (ghi đè), thêm ở đầu file:

   ```markdown
   # Review <MÃ> — nhánh `<nhánh>` @ `<commit>` — <YYYY-MM-DD HH:MM>
   ```

7. Trả lời chủ repo trong 3–5 dòng: kết luận, số mục phải sửa / nên sửa, và câu để dán cho Codex:
   "Đọc `.reviews/<MÃ>.md`, sửa các mục Phải sửa, chạy lại kiểm tra, cập nhật bàn giao, commit."
