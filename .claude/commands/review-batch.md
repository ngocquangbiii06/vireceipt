---
description: Review cả một đợt task trên nhánh wave/… bằng nhiều subagent reviewer chạy song song, gom vào một file cho chủ repo và Codex
argument-hint: <nhánh> [MÃ …]
---

Review đợt với tham số: `$ARGUMENTS` (dạng `<nhánh> [MÃ …]`, ví dụ `wave/T1-1` hoặc
`wave/T1-1 T1-02 T1-03 T1-04`).

1. Thiếu nhánh thì hỏi lại, dừng. Tên đợt là phần sau `wave/` (ví dụ `T1-1`); file kết quả là
   `.reviews/<tên-đợt>.md`.
2. Chạy `git rev-parse --abbrev-ref HEAD`. Nếu khác `<nhánh>`: **không tự chuyển nhánh** (Codex có thể
   đang làm). Bảo chủ repo chạy `git switch <nhánh>` khi Codex đã dừng, rồi gọi lại lệnh này. Dừng.
3. Danh sách task: lấy từ tham số; không có thì lấy các mã `[T…]` trong
   `git log --format=%s main..<nhánh>` và đối chiếu với bảng "Đợt" trong `docs/tasks/README.md`.
   Mỗi mã phải có `docs/tasks/<MÃ>.md`; thiếu thì báo và dừng.
4. Lấy commit đang review: `git log -1 --format=%h <nhánh>`. Nếu `.reviews/<tên-đợt>.md` đã có, chỉ đọc
   **dòng đầu** để lấy commit lần trước: đây là **review lại**, `từ commit` = commit đó.
5. Kiểm tra chung, chạy **một lần** trong phiên chính (chỉ giữ dòng tóm tắt của mỗi lệnh):
   - `uv run ruff format --check .`, `uv run ruff check .`, `uv run pytest -q`
   - `git diff --shortstat main...<nhánh>` — quá ~1.000 dòng (không tính `uv.lock`) thì ghi "đợt quá lớn"
   - `git diff main...<nhánh> | grep -n "test.jsonl"` — phải không có kết quả
   - `git log --no-merges --format='%h %s' main..<nhánh>` — liệt kê commit **không** có mã task của đợt
6. Giao cho subagent `reviewer`, **mỗi task một subagent, gọi tất cả trong cùng một lượt để chạy song
   song**: "Review task `<MÃ>` trên nhánh `<nhánh>`, chế độ `đợt`" — review lại thì thêm
   ", từ commit `<commit lần trước>`, review cũ `.reviews/<tên-đợt>.md`". Không tự đọc diff trong phiên
   chính.
7. Ghi `.reviews/<tên-đợt>.md` (ghi đè) theo mẫu dưới. Mục "Cần chủ repo quyết" gom từ mục cùng tên
   của mọi task, đánh số liên tục, mỗi mục ghi mã task. Phần từng task chép **nguyên văn** kết quả
   subagent.

   ```markdown
   # Review đợt <tên-đợt> — nhánh `<nhánh>` @ `<commit>` — <YYYY-MM-DD HH:MM>

   Task: <MÃ, …> · Review lại từ: `<commit lần trước>` (hoặc "lần đầu")

   ## Cần chủ repo quyết
   1. [<MÃ>] câu hỏi — các lựa chọn — gợi ý

   ## Tổng quan
   | Task | Kết luận | Phải sửa | Nên sửa |
   |---|---|---|---|

   ## Kiểm tra chung
   - `lệnh` → kết quả

   ## <MÃ>
   <nguyên văn subagent>
   ```

8. Trả lời chủ repo, tối đa 8 dòng: kết luận từng task, các câu hỏi trong "Cần chủ repo quyết" (chép
   nguyên số thứ tự để chủ repo trả lời kiểu "1: làm tròn lên"), và câu để dán cho Codex:
   "Đọc `.reviews/<tên-đợt>.md`, sửa theo AGENTS.md §6 'Sửa sau review', chạy lại kiểm tra, cập nhật
   bàn giao, commit." Không còn mục sửa và câu hỏi nào thì báo "Sẵn sàng merge `<nhánh>`".
9. Khi chủ repo trả lời: ghi từng quyết định vào mục "Quyết định đã chốt" của task card tương ứng trên
   nhánh đợt (chỉ khi Codex đã dừng; chỉ sửa task card, không sửa code; không commit — Codex commit
   cùng phần sửa). Rồi đưa lại câu để dán cho Codex ở bước 8.
