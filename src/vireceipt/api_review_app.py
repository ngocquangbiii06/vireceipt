"""Review persisted requests through the local HTTP API, with explicit conflict recovery."""

import argparse
import io
import json

import streamlit as st
from PIL import Image, ImageOps

from vireceipt.eval.io import QUALITY_TAGS
from vireceipt.review_client import ReviewAPIClient, ReviewClientError
from vireceipt.schema import is_valid_receipt


def main(argv: list[str] | None = None) -> None:
    """Show original snapshots and save versioned human corrections over HTTP."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    st.set_page_config(page_title="ViReceipt — API Review", layout="wide")
    st.title("ViReceipt — Review hóa đơn đã lưu")
    feedback = st.session_state.pop("api_review_feedback", None)
    if feedback:
        st.success("Đã lưu bản sửa.")
        for issue in feedback["issues"]:
            st.warning(f"{issue['code']}: {issue['message']}")
    status = st.sidebar.selectbox("Trạng thái", ["all", "review", "corrected"])
    page = st.sidebar.number_input("Trang", min_value=1, value=1, step=1)
    try:
        client = ReviewAPIClient(args.api)
        items = client.list_requests(
            limit=20, offset=(page - 1) * 20, status=None if status == "all" else status
        )["items"]
        if not isinstance(items, list):
            raise ValueError("Invalid queue response")
        job_ids = [item["job_id"] for item in items]
    except (ReviewClientError, ValueError, TypeError, KeyError) as error:
        st.error(f"Không đọc được hàng đợi API: {error}")
        st.stop()
    if not job_ids:
        st.info("Không có job trong trang này. Có thể đổi trang hoặc trạng thái.")
        st.stop()
    job_id = st.sidebar.selectbox(
        "Job cần review", job_ids, key=f"{client.base_url}|{status}|{page}|job"
    )
    snapshot_key = (client.base_url, job_id)
    if st.button("Đọc lại bản mới"):
        st.session_state.pop("api_review_snapshot", None)
        st.session_state["api_editor_epoch"] = st.session_state.get("api_editor_epoch", 0) + 1
        st.rerun()
    try:
        cached = st.session_state.get("api_review_snapshot")
        if cached is None or cached[0] != snapshot_key:
            cached = (snapshot_key, client.get(job_id))
            st.session_state["api_review_snapshot"] = cached
        job = cached[1]
        with Image.open(io.BytesIO(client.image(job_id))) as image:
            preview = ImageOps.exif_transpose(image).copy()
    except (ReviewClientError, ValueError, OSError, TypeError, KeyError) as error:
        st.error(f"Không mở được job/ảnh: {error}")
        st.stop()
    st.caption(f"{job['receipt_id']} · {job_id} · phiên bản {job['revision']} · {job['status']}")
    st.caption("Đối chiếu ảnh trước khi lưu. Bản sửa chưa tự đưa vào train/val/test.")
    left, right = st.columns(2)
    with left:
        st.image(preview, width=600)
        st.subheader("Dự đoán gốc và cảnh báo")
        st.json(job["prediction"])
    current = job["correction"] or {}
    initial = current.get("receipt", job["prediction"]["receipt"])
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
    prefix = f"{client.base_url}|{job_id}|{st.session_state.get('api_editor_epoch', 0)}|"
    with right, st.form(prefix + "form"):
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
            result = client.correct(
                job_id,
                dict(
                    receipt=json.loads(text),
                    expected_revision=job["revision"],
                    store_id=store_id,
                    source=source,
                    quality=quality,
                    notes=notes,
                ),
            )
        except ReviewClientError as error:
            if error.status == 409:
                st.error(
                    "409: Có bản sửa mới. Giữ/copy draft để đối chiếu rồi bấm Đọc lại bản mới."
                )
            else:
                st.error(f"Chưa lưu: {error}")
        except (ValueError, TypeError, RecursionError):
            st.error("Chưa lưu: JSON không hợp lệ.")
        else:
            st.session_state["api_review_feedback"] = result["verification"]
            st.session_state.pop("api_review_snapshot", None)
            st.session_state["api_editor_epoch"] = st.session_state.get("api_editor_epoch", 0) + 1
            st.rerun()


if __name__ == "__main__":
    main()
