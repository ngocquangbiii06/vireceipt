"""Local Streamlit review UI; corrections remain separate from dataset splits."""

import argparse
import json
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps

from vireceipt.eval.io import QUALITY_TAGS
from vireceipt.review_queue import load_review_queue
from vireceipt.review_store import load_corrections, save_correction
from vireceipt.schema import is_valid_receipt


def main(argv: list[str] | None = None) -> None:
    """Show image, model output and a validated candidate-label editor."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path, default=Path("manifest.jsonl"))
    parser.add_argument("--pred", type=Path, default=Path("predictions/baseline.jsonl"))
    args = parser.parse_args(argv)
    root = args.data.resolve()
    st.set_page_config(page_title="ViReceipt — Review", layout="wide")
    st.title("ViReceipt — Đối chiếu và sửa dự đoán")
    feedback = st.session_state.pop("review_feedback", None)
    if feedback:
        st.success(f"Đã lưu bản sửa {feedback[0]}.")
        for issue in feedback[1]:
            st.warning(f"{issue.code}: {issue.message}")
    try:
        queue = load_review_queue(root, args.manifest, args.pred)
        corrections = load_corrections(root)
    except (ValueError, OSError, UnicodeError) as error:
        st.error(f"Không đọc được hàng đợi review: {error}")
        st.stop()
    record_id = st.sidebar.selectbox("ID cần review", [item.id for item in queue])
    item = next(item for item in queue if item.id == record_id)
    relative = item.image.relative_to(root).as_posix()
    current = corrections.get(item.id, {})
    if current and current["image"] != relative:
        st.error(
            "ID này đã có bản sửa cho ảnh khác. Kiểm tra lại manifest và ID trước khi tiếp tục."
        )
        st.stop()
    st.caption(f"{relative} · " + ("đã lưu bản sửa" if current else "chưa lưu bản sửa"))
    st.caption(
        "Bản sửa được lưu riêng; chưa tự đưa vào train/val/test. Không sửa số in sai trên ảnh."
    )
    left, right = st.columns(2)
    with left:
        try:
            with Image.open(item.image) as image:
                preview = ImageOps.exif_transpose(image).copy()
            st.image(preview, caption=relative, width=600)
        except OSError as error:
            st.error(f"Không mở được ảnh: {error}")
            st.stop()
        st.subheader("Dự đoán gốc và cảnh báo")
        st.json({"receipt": item.prediction.receipt, **item.prediction.extra})
    with right:
        initial = current.get("receipt", item.prediction.receipt)
        if not is_valid_receipt(initial):
            initial = dict(
                schema_version="1.0",
                seller=dict.fromkeys(("name", "address", "phone", "tax_code")),
                issued_at=dict(date=None, time=None),
                items=[],
                subtotal=None,
                discount=None,
                vat=None,
                total=None,
                currency="VND",
                payment_method=None,
            )
            st.info("Dự đoán chưa đúng schema. Điền từ ảnh vào mẫu trống bên dưới.")
        prefix = f"{root}|{args.manifest}|{args.pred}|{item.id}|{relative}|"
        with st.form(prefix + "form"):
            text = st.text_area(
                "JSON hóa đơn đã đối chiếu",
                json.dumps(initial, ensure_ascii=False, indent=2),
                height=420,
                key=prefix + "receipt",
            )
            store_id = st.text_input("store_id", current.get("store_id", ""), key=prefix + "store")
            sources = ["", "own", "mcocr"]
            source = st.selectbox(
                "Nguồn ảnh",
                sources,
                index=sources.index(current.get("source", "")),
                key=prefix + "source",
            )
            quality = st.multiselect(
                "Chất lượng ảnh",
                sorted(QUALITY_TAGS),
                default=current.get("quality", []),
                key=prefix + "quality",
            )
            notes = st.text_area("Ghi chú", current.get("notes", ""), key=prefix + "notes")
            submitted = st.form_submit_button("Lưu bản sửa")
        if submitted:
            try:
                report = save_correction(
                    root, item, text, store_id=store_id, source=source, quality=quality, notes=notes
                )
            except (ValueError, OSError, UnicodeError) as error:
                st.error(f"Chưa lưu: {error}")
            else:
                st.session_state["review_feedback"] = (item.id, report.issues)
                st.rerun()


if __name__ == "__main__":
    main()
