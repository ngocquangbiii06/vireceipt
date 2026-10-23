# CLAUDE.md

Luật và bối cảnh chung nằm trong AGENTS.md (dùng chung cho Codex và Claude Code):

@AGENTS.md

## Riêng cho Claude Code

Vai trò của Claude trong repo này: **viết task card và review**. Phần viết code là của Codex.

- **Review đợt:** `/review-batch <nhánh>` — mỗi task một subagent `reviewer` (model rẻ) chạy song
  song, gom vào `.reviews/<tên-đợt>.md`; mục "Cần chủ repo quyết" nằm đầu file.
- **Review task lẻ:** `/review-task <MÃ> <nhánh>` — ghi vào `.reviews/<MÃ>.md`. Task khó (metric, khóa
  tập test, thiết kế) thì nhờ review thẳng trong phiên chính thay vì subagent.
- **Viết task card mới:** chép `docs/tasks/_template.md` thành `docs/tasks/<MÃ>.md`, thêm một dòng vào
  `docs/tasks/README.md`. Task card phải có danh sách "Được phép sửa", tiêu chí xong đo được, và mục
  "Quyết định đã chốt" — hỏi chủ repo các chỗ biên **trước khi** giao, để Codex không dừng giữa đợt.
- **Ghi quyết định:** chủ repo trả lời câu hỏi review thì ghi vào "Quyết định đã chốt" của task card.
- **Không sửa code trên nhánh Codex đang làm.** Chỉ đọc diff, chạy test, sửa task card.
- Mỗi đợt một phiên; xong thì `/clear` để phiên sau không phải đọc lại lịch sử dài.
- Chỉ commit hoặc push khi chủ repo yêu cầu.
