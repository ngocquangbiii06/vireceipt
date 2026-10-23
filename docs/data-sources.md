# Nguồn dữ liệu và mô hình — T1-01

Ngày tra cứu: 2026-10-23. Đây là kết quả tra cứu một phần; T1-01 vẫn `doing`.
Các số mẫu bên dưới là số tác giả công bố, không phải kết quả đánh giá của ViReceipt.
Ô chưa xác minh không được hiểu là đã có quyền sử dụng hoặc công bố.

## Dữ liệu

| Nguồn chính thức | Số mẫu công bố / nhãn | Điều khoản đã đọc, trích nguyên văn | Train | Công bố weights train từ nguồn | Đăng lại ảnh |
|---|---|---|---|---|---|
| [MC-OCR 2021 — trang cuộc thi](https://www.aihub.ml/competitions/1), [bài báo tổ chức](https://people.cs.umu.se/sonvx/files/MCOCR_Preprint.pdf) | 2.436 ảnh; chất lượng và 4 trường người bán, địa chỉ, thời điểm, tổng tiền. Không có nhãn dòng hàng có cấu trúc được mô tả trong bài báo. | “You will not distribute the data except for the purpose of non-commercial and academic-research.” | Chưa xác minh quyền dùng ngoài cuộc thi. | Chưa có điều khoản weights được xác nhận. | Có hạn chế phân phối; không đưa ảnh vào repo. |
| [5CD-AI/Viet-Receipt-VQA](https://huggingface.co/datasets/5CD-AI/Viet-Receipt-VQA) | Chưa xác minh số mẫu và trường nhãn vì không mở được card. | Chưa đọc được điều khoản; không có câu trích đã xác minh. | Chưa xác minh. | Chưa xác minh. | Chưa xác minh. |
| [UIT-MLReceipts — bài báo của tác giả](https://www.rev-jec.org/index.php/rev-jec/article/download/330/310) | 2.147 ảnh; 1.000 train, 358 validation, 789 test; bbox và nhóm seller/address/timestamp/total cost, không phải annotation dòng hàng theo schema ViReceipt. | “The dataset is available online for non-commercial research at http://tinyurl.com/uit-ml-receipts.” | Tác giả nêu nghiên cứu phi thương mại. | Chưa thấy quyền công bố weights được nêu riêng. | Chưa có quyền phát lại ảnh được xác nhận. |
| [SROIE — trang cuộc thi](https://rrc.cvc.uab.es/?ch=13), [báo cáo của ban tổ chức](https://arxiv.org/abs/2103.10213) | 1.000 ảnh scan, 600 trainval và 400 test theo bài báo; bbox/OCR transcript và key information extraction. Tiếng Anh, chỉ tham khảo cho dự án. | Trang điều khoản/download không truy cập được trong phiên tra cứu; chưa có câu trích giấy phép dữ liệu. | Chưa xác minh. | Chưa xác minh. | Chưa xác minh. |

MC-OCR còn có điều khoản phân phối rộng hơn và quy tắc annotation riêng cho cuộc thi trên cùng trang.
Không suy từ quyền tham gia cuộc thi thành quyền tạo nhãn mới hoặc phát hành mô hình cho portfolio.
Cần đối chiếu đầy đủ điều khoản gói dữ liệu và làm rõ quyền tương ứng trước khi chọn hướng huấn luyện.

## Mô hình và thư viện

| Thành phần chính thức | Bằng chứng giấy phép | Phạm vi đã xác minh |
|---|---|---|
| [Qwen3-VL-2B-Instruct model card](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct/raw/main/README.md) | Metadata nguyên văn: `license: apache-2.0`. | Card đúng model ghi Apache-2.0; LICENSE riêng trong repo model không tải được qua các URL đã thử. |
| [Qwen2-VL-2B-Instruct model card](https://huggingface.co/Qwen/Qwen2-VL-2B-Instruct/raw/main/README.md) | Metadata nguyên văn: `license: apache-2.0`. | Card đúng model ghi Apache-2.0; chưa tải weights hay chọn checkpoint. |
| [PaddleOCR LICENSE](https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/LICENSE) | Apache-2.0; “See the License for the specific language governing permissions and limitations under the License.” | Mã nguồn trong repo. Giấy phép từng weights tải từ nguồn khác phải kiểm riêng. |
| [VietOCR LICENSE](https://raw.githubusercontent.com/pbcquoc/vietocr/master/LICENSE) | Apache-2.0; “See the License for the specific language governing permissions and limitations under the License.” | Mã nguồn trong repo. Không tự suy quyền weights liên kết ngoài từ giấy phép mã nguồn. |

Đánh giá sơ bộ từ Apache-2.0: có thể sửa và phân phối phần thuộc phạm vi giấy phép nếu giữ các điều kiện
LICENSE/NOTICE và thông báo thay đổi. Đây chưa phải quyết định công bố weights ViReceipt: quyền của
dữ liệu huấn luyện vẫn phải được giải quyết. Bản/checkpoint chỉ cho nghiên cứu không được chọn cho
mục tiêu công bố mô hình khi chưa có quyền phù hợp.

## Truy cập Viet-Receipt-VQA và kiểm 30 mẫu

- API metadata `https://huggingface.co/api/datasets/5CD-AI/Viet-Receipt-VQA`: HTTP 401.
- README qua `resolve/main/README.md`: HTTP 401; web fetch trang dataset: HTTP 401.
- Chrome chưa đăng nhập hiển thị 404 tại URL dataset. Không kết luận repo đã bị xóa hay giấy phép nào
  từ các phản hồi này; cần đúng URL và tài khoản có quyền.
- Chủ repo đã xác nhận chưa có quyền truy cập trong phiên 2026-10-23.
- **Chưa kiểm 30 mẫu, chưa có số đúng/sai.** Không tải dataset, không chấp nhận điều khoản thay chủ repo.
- Thông tin nhãn dòng hàng do Gemini sinh hiện mới là bối cảnh của task card, chưa đối chiếu được card.

Khi có quyền: chỉ lấy mẫu từ nguồn ngoài phục vụ train/val, cố định seed, lưu danh sách ID và tiêu chí
chấm trong ghi chép cục bộ; kiểm tên món, lượng, đơn giá, thành tiền theo ảnh; báo số đúng/tổng từ
kết quả thực. Không lấy mẫu từ tập test riêng của ViReceipt.

## Phần cần chủ repo quyết

1. Cung cấp quyền/URL hợp lệ để kiểm 30 mẫu và đọc điều khoản Viet-Receipt-VQA.
2. Làm rõ quyền train/phát hành weights từ nguồn được chọn; chưa có kết luận tương đương giấy phép
   mở cho MC-OCR, UIT-MLReceipts hoặc SROIE.
3. Sau khi có bằng chứng, chọn (a), (b) hoặc (c) trong ADR 0002. Hiện chưa chọn thay chủ repo.
