# CLAUDE.md

Luật và bối cảnh chung nằm trong AGENTS.md (dùng chung cho Codex và Claude Code):

@AGENTS.md

## Riêng cho Claude Code

Vai trò của Claude trong repo này: **viết task card và review**. Phần viết code là của Codex.

- **Review:** `/review-task <MÃ> <nhánh>` — chạy subagent `reviewer` (model rẻ), ghi kết quả vào
  `.reviews/<MÃ>.md` để Codex đọc và sửa. Task khó (metric, khóa tập test, thiết kế) thì nhờ review
  thẳng trong phiên chính thay vì subagent.
- **Viết task card mới:** chép `docs/tasks/_template.md` thành `docs/tasks/<MÃ>.md`, thêm một dòng vào
  `docs/tasks/README.md`. Task card phải có danh sách "Được phép sửa" và tiêu chí xong đo được.
- **Không sửa code trên nhánh Codex đang làm.** Chỉ đọc diff và chạy test.
- Mỗi task một phiên; xong thì `/clear` để phiên sau không phải đọc lại lịch sử dài.
- Chỉ commit hoặc push khi chủ repo yêu cầu.
