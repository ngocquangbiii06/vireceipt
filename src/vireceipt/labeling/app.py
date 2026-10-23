"""Streamlit receipt labeling app; the only labels file accessed is all.jsonl."""

import argparse
import json
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps

from vireceipt.checks import check_receipt
from vireceipt.eval.io import QUALITY_TAGS
from vireceipt.labeling.form import build_record, next_id, unlabeled_images, upsert_record


def main(argv: list[str] | None = None) -> None:
    """Show a receipt image and form, validating before an atomic save."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    data = parser.parse_args(argv).data.resolve()
    labels, images = data / "labels" / "all.jsonl", data / "images"
    st.set_page_config(page_title="ViReceipt — Gán nhãn", layout="wide")
    st.title("ViReceipt — Gán nhãn hóa đơn")
    feedback = st.session_state.pop("saved_feedback", None)
    if feedback:
        st.success(f"Đã lưu {feedback[0]}.")
        for issue in feedback[1]:
            st.warning(f"{issue.code}: {issue.message}")
    try:
        records = (
            [
                json.loads(line)
                for line in labels.read_text(encoding="utf-8").split("\n")
                if line.strip()
            ]
            if labels.exists()
            else []
        )
        pending = unlabeled_images(images, labels)
    except (ValueError, OSError, UnicodeError) as error:
        st.error(f"Không đọc được dữ liệu: {error}")
        st.stop()
    mode = st.sidebar.radio("Chế độ", ["Gán ảnh mới", "Sửa nhãn"])
    current = {}
    if mode == "Gán ảnh mới":
        if not pending:
            st.info("Không còn ảnh chưa gán nhãn. Thêm ảnh vào thư mục images hoặc chọn Sửa nhãn.")
            st.stop()
        relative = st.sidebar.selectbox(
            "Ảnh chưa gán", [p.relative_to(data).as_posix() for p in pending]
        )
        record_id = next_id(row["id"] for row in records)
    else:
        if not records:
            st.info("Chưa có nhãn để sửa.")
            st.stop()
        record_id = st.sidebar.selectbox("ID cần sửa", [row["id"] for row in records])
        current = next(row for row in records if row["id"] == record_id)
        relative = current["image"]
    prefix = f"{mode}:{record_id}:{relative}:"
    image_path = (data / relative).resolve()
    if not image_path.is_relative_to(images.resolve()):
        st.error("Ảnh phải nằm trong thư mục images.")
        st.stop()
    left, right = st.columns([1, 1])
    with left:
        rotation_key = f"rotation:{relative}"
        if st.button("Xoay 90°", key=prefix + "rotate"):
            st.session_state[rotation_key] = (st.session_state.get(rotation_key, 0) + 90) % 360
        try:
            with Image.open(image_path) as image:
                preview = ImageOps.exif_transpose(image).copy()
            st.image(
                preview.rotate(st.session_state.get(rotation_key, 0), expand=True),
                caption=relative,
                width=600,
            )
        except OSError as error:
            st.error(f"Không mở được ảnh: {error}")
            st.stop()
    with right:
        receipt = current.get("receipt", {})
        stores = sorted({row["store_id"] for row in records})
        st.caption("Gợi ý store_id: " + (", ".join(stores) or "chưa có"))
        with st.form(prefix + "form"):
            values = dict(id=record_id, image=relative)
            st.text_input("ID", record_id, disabled=True, key=prefix + "id")
            st.text_input("Ảnh", relative, disabled=True, key=prefix + "image")

            def text(label, key, value=None):
                values[key] = st.text_input(
                    label, "" if value is None else str(value), key=prefix + key
                )

            text("store_id", "store_id", current.get("store_id"))
            values["source"] = st.selectbox(
                "Nguồn",
                ["own", "mcocr"],
                index=["own", "mcocr"].index(current.get("source", "own")),
                key=prefix + "source",
            )
            values["quality"] = st.multiselect(
                "Chất lượng",
                sorted(QUALITY_TAGS),
                default=current.get("quality", ["good"]),
                key=prefix + "quality",
            )
            for key, label in (
                ("name", "Tên cửa hàng"),
                ("address", "Địa chỉ cửa hàng"),
                ("phone", "Điện thoại cửa hàng"),
                ("tax_code", "Mã số thuế"),
            ):
                text(label, f"seller_{key}", receipt.get("seller", {}).get(key))
            text("Ngày", "date", receipt.get("issued_at", {}).get("date"))
            text("Giờ", "time", receipt.get("issued_at", {}).get("time"))
            st.caption(
                "Để trống khi không in hoặc không đọc được; không sửa số in sai trên hóa đơn."
            )
            columns = ("name", "quantity", "unit_price", "amount")
            rows = [
                {key: "" if row[key] is None else str(row[key]) for key in columns}
                for row in receipt.get("items", [])
            ] or [dict.fromkeys(columns, "")]
            values["items"] = st.data_editor(rows, num_rows="dynamic", key=prefix + "items")
            for key, label in (
                ("subtotal", "Tổng tiền hàng"),
                ("discount", "Giảm giá"),
                ("vat", "Thuế GTGT"),
                ("total", "Tổng thanh toán"),
            ):
                text(label, key, receipt.get(key))
            payments = ["", "cash", "card", "bank_transfer", "e_wallet", "other"]
            values["payment_method"] = st.selectbox(
                "Thanh toán",
                payments,
                index=payments.index(receipt.get("payment_method") or ""),
                key=prefix + "payment",
            )
            values["notes"] = st.text_area(
                "Ghi chú", current.get("notes", ""), key=prefix + "notes"
            )
            submitted = st.form_submit_button("Lưu")
        if submitted:
            try:
                record = build_record(values)
                issues = check_receipt(record["receipt"])
                upsert_record(labels, record)
            except (ValueError, OSError, UnicodeError) as error:
                st.error(f"Chưa lưu: {error}")
            else:
                st.session_state["saved_feedback"] = (record["id"], issues)
                st.rerun()


if __name__ == "__main__":
    main()
