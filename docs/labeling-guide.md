# Hướng dẫn gán nhãn hóa đơn

Mục tiêu: hai người gán nhãn cùng một hóa đơn phải ra cùng một JSON. Khi gặp trường hợp chưa có
trong file này, quyết định một cách, ghi vào mục **Nhật ký quyết định** ở cuối file, rồi áp dụng
cho mọi hóa đơn sau đó (và sửa lại các hóa đơn trước nếu cần).

Schema: `src/vireceipt/schemas/receipt.schema.json`. File nhãn: `data/labels/<split>.jsonl`.

## 1. Một dòng nhãn

```json
{
  "id": "r0001",
  "image": "images/r0001.jpg",
  "store_id": "bhx-q10-ltk",
  "source": "own",
  "quality": ["good"],
  "receipt": { "...": "theo schema" },
  "notes": ""
}
```

| Trường | Cách điền |
|---|---|
| `id` | `r` + 4 chữ số, không dùng lại |
| `image` | đường dẫn tương đối trong `data/` |
| `store_id` | mã cửa hàng do mình đặt: `<chuỗi>-<quận>-<đường>`. **Hai hóa đơn cùng cửa hàng phải cùng `store_id`** — dùng để chia tập |
| `source` | `own` (tự chụp) hoặc `mcocr` |
| `quality` | một hoặc nhiều nhãn: `good`, `blurry`, `skewed`, `low_light`, `crumpled`, `cropped` |
| `notes` | ghi chú tự do, ví dụ "chữ mờ ở dòng 3" |

## 2. Nguyên tắc chung

1. **Chép đúng những gì in trên hóa đơn.** Không sửa lỗi chính tả, không suy luận thêm.
2. **`null` = không in trên hóa đơn hoặc không đọc được.** Không đoán. Nếu đọc được một phần, để
   `null` và ghi vào `notes`.
3. **Chữ tiếng Việt giữ nguyên dấu như trên hóa đơn.** Hóa đơn in không dấu thì chép không dấu.
4. **Khoảng trắng:** gộp nhiều khoảng trắng thành một, bỏ khoảng trắng đầu/cuối.
5. **Viết hoa:** giữ như trên hóa đơn. (Khi chấm, chữ hoa/thường không bị tính là sai.)

## 3. Từng trường

### `seller`
- `name`: tên cửa hàng như in ở đầu hóa đơn, **không** kèm khẩu hiệu hay tên công ty mẹ ở dòng
  khác. Nếu có cả tên thương hiệu và tên chi nhánh trên cùng một dòng, chép cả dòng.
- `address`: chép một dòng địa chỉ, nối các dòng bị xuống hàng bằng một dấu cách. Không thêm
  "TP.HCM" nếu hóa đơn không in.
- `phone`: chép như in (có thể có dấu chấm, cách). Khi chấm chỉ so phần chữ số.
- `tax_code`: mã số thuế người bán nếu in; không phải mã số thuế người mua.

### `issued_at`
- `date`: `YYYY-MM-DD`. Hóa đơn Việt Nam thường in `dd/mm/yyyy` — đổi lại. Năm 2 chữ số
  `12/11/26` → `2026-11-12`.
- `time`: `HH:MM` dạng 24 giờ, bỏ giây. `06:42 PM` → `18:42`.
- Nếu hóa đơn có nhiều mốc giờ (giờ vào/giờ ra ở quán), lấy **giờ in hóa đơn / giờ thanh toán**.

### `items`
- Mỗi dòng hàng một phần tử, **theo thứ tự in**.
- `name`: tên hàng như in, không kèm mã vạch hay mã SKU.
- `quantity`: số lượng; hàng cân ký thì giữ số thập phân (`0.45`). Không in thì `null`.
- `unit_price`, `amount`: số nguyên đồng (xem mục 4).
- Dòng giảm giá **riêng cho một món** (ví dụ "KM -5.000" ngay dưới món): không tạo item mới;
  ghi `amount` là số **sau giảm** nếu hóa đơn in số sau giảm, ngược lại ghi số trước giảm và
  ghi chú trong `notes`.
- Dòng không phải hàng (phí ship, phụ thu, túi nilon có tính tiền): **là item** nếu có tiền.
- Hóa đơn không liệt kê món (chỉ có tổng): `items: []`.

### Tiền tổng
- `subtotal`: tổng trước giảm giá và thuế ("Tổng tiền hàng", "Cộng tiền hàng"). Không in → `null`.
- `discount`: tổng giảm giá **cho cả hóa đơn**, số dương (giảm 10.000 → `10000`). Không có → `null`;
  in rõ "Giảm giá: 0" → `0`.
- `vat`: tiền thuế GTGT nếu in thành dòng riêng. Hóa đơn ghi "giá đã bao gồm VAT" mà không in
  số → `null`.
- `total`: số khách phải trả ("Tổng thanh toán", "Khách phải trả", "Thành tiền" ở cuối).
  **Không** phải "Tiền khách đưa" hay "Tiền thối lại".

### `payment_method`
`cash` (tiền mặt), `card` (thẻ, POS), `bank_transfer` (chuyển khoản, QR ngân hàng),
`e_wallet` (MoMo, ZaloPay, ShopeePay…), `other`. Không in → `null`.

### `currency`
Luôn `"VND"`.

## 4. Đọc số tiền

| Trên hóa đơn | Ghi |
|---|---|
| `1.234.000`, `1,234,000`, `1 234 000` | `1234000` |
| `32.000đ`, `32,000 VND`, `32.000₫` | `32000` |
| `120k` (viết tay) | `120000` |
| `-5.000` ở dòng giảm giá | `5000` trong `discount` |

Đồng Việt Nam không có phần lẻ; dấu `.` và `,` đều là dấu ngăn nghìn.

## 5. Dữ liệu cá nhân

Trước khi gán nhãn hóa đơn tự chụp:
- **Che** (tô đen trên ảnh) tên, số điện thoại, số thẻ, địa chỉ của **người mua**, mã thành viên.
- Không chụp hóa đơn của người khác nếu chưa được đồng ý.
- Ảnh và nhãn nằm trong `data/`, không đưa lên git.

## 6. Kiểm tra trước khi lưu

- [ ] JSON hợp lệ theo schema (`vireceipt-eval` sẽ báo dòng sai).
- [ ] Nếu có đủ số: tổng `amount` các món = `subtotal`; `subtotal - discount + vat = total`.
      Không khớp mà hóa đơn in đúng như vậy → giữ nguyên số in, ghi vào `notes`.
- [ ] `store_id` đúng cửa hàng.

## 7. Tập test

Tập `test` gồm hóa đơn tự chụp, chia **theo cửa hàng** (mọi hóa đơn của một cửa hàng nằm trọn
trong một tập). Gán nhãn xong thì đóng băng:

```bash
uv run vireceipt-freeze data/labels/test.jsonl
```

Sau đó **không mở tập test để xem lỗi, không chỉnh prompt hay ngưỡng theo nó.** Nếu phát hiện
nhãn test sai, sửa nhãn, đóng băng lại, và ghi lý do vào Nhật ký quyết định.

## Nhật ký quyết định

| Ngày | Trường hợp | Quyết định |
|---|---|---|
| | | |
