"""Synthetic Vietnamese diacritics smoke; not a real-receipt benchmark."""

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import unicodedata
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Any

from vireceipt.normalize import levenshtein, norm_text

LINES = (
    "CỬA HÀNG THỰC PHẨM MINH ANH",
    "Sữa tươi không đường",
    "Bánh mì thịt nướng",
    "Cà phê sữa đá",
    "Trà đào cam sả",
    "Nước ép bưởi",
    "Phở bò tái chín",
    "Bún đậu mắm tôm",
    "Cơm gà xối mỡ",
    "Đậu hũ sốt cà chua",
    "Đường cát trắng",
    "Muối biển hạt nhỏ",
    "Gạo thơm đặc sản",
    "Dầu ăn đậu nành",
    "Thịt lợn nạc vai",
    "Cá hồi phi lê",
    "Tôm sú tươi sống",
    "Rau cải ngọt",
    "Ổi ruột hồng",
    "Dưa hấu không hạt",
    "Mì gói chua cay",
    "Nấm hương khô",
    "Ớt bột Hàn Quốc",
    "Bột ngũ cốc dinh dưỡng",
    "Khăn giấy bỏ túi",
    "Nước rửa chén",
    "HÓA ĐƠN BÁN LẺ",
    "TỔNG TIỀN THANH TOÁN",
    "ĐỊA CHỈ CỬA HÀNG",
    "ĐƯỜNG LÝ THƯỜNG KIỆT",
    "12 Nguyễn Trãi, Phường 5",
    "68 Đặng Thùy Trâm, Quận Bình Thạnh",
    "125 Võ Văn Tần, Thành phố Hồ Chí Minh",
    "Hẹn gặp lại quý khách",
    "Giá đã gồm thuế giá trị gia tăng",
    "Thanh toán chuyển khoản",
    "Số lượng và đơn giá",
    "Mã cửa hàng số một",
    "Chả giò hải sản",
    "Mứt dừa vị lá dứa",
)


def strip_accents(text: str) -> str:
    """Remove Vietnamese marks including the stroked D, preserving case."""
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def cer(reference: str, prediction: str) -> float:
    """Normalized character edit rate; an empty reference uses denominator one."""
    reference, prediction = norm_text(reference), norm_text(prediction)
    return levenshtein(reference, prediction) / max(1, len(reference))


def summarize(references: list[str], predictions: list[str]) -> dict[str, int | float]:
    """Count exact/accentless lines and corpus CER weighted by reference characters."""
    if len(references) != len(predictions):
        raise ValueError("Every reference needs one OCR result")
    pairs = [(norm_text(a), norm_text(b)) for a, b in zip(references, predictions, strict=True)]
    edits = sum(levenshtein(a, b) for a, b in pairs)
    characters = sum(len(a) for a, _ in pairs)
    return dict(
        lines=len(pairs),
        exact=sum(a == b for a, b in pairs),
        accentless=sum(strip_accents(a) == strip_accents(b) for a, b in pairs),
        edits=edits,
        characters=characters,
        cer=edits / max(1, characters),
    )


def render_line(text: str, font: Any) -> Any:
    """Draw a single black line with enough padding to preserve accents."""
    from PIL import Image, ImageDraw

    left, top, right, bottom = font.getbbox(text)
    image = Image.new("RGB", (right - left + 64, bottom - top + 64), "white")
    ImageDraw.Draw(image).text((32 - left, 32 - top), text, fill="black", font=font)
    return image


def write_report(report: str, output: Path) -> None:
    """Save the full Unicode report and print it to the console."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    encoding = sys.stdout.encoding or "utf-8"
    print(report.encode(encoding, errors="backslashreplace").decode(encoding))


def main(argv: list[str] | None = None) -> int:
    """Run the actual OCR engine on temporary synthetic images and record provenance."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/arial.ttf"))
    args = parser.parse_args(argv)
    from PIL import ImageFont

    from vireceipt.ocr import read_text

    font = ImageFont.truetype(str(args.font), 40)
    device = os.environ.get("VIRECEIPT_OCR_DEVICE") or "cpu"
    predictions = []
    with tempfile.TemporaryDirectory(prefix="vireceipt-ocr-smoke-") as directory:
        for index, text in enumerate(LINES):
            image = Path(directory) / f"line-{index:02}.png"
            render_line(text, font).save(image)
            predictions.append(read_text(image))
            print(f"OCR {index + 1}/{len(LINES)}", flush=True)
    metrics = summarize(list(LINES), predictions)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rows = [
        "# OCR diacritics smoke",
        "",
        "**Ảnh tổng hợp, không đại diện hóa đơn thật.**",
        "",
        f"- Commit: {commit}; script SHA256: {script_hash}",
        f"- paddleocr: {version('paddleocr')}; paddlepaddle: {version('paddlepaddle')}",
        "- Detection: PP-OCRv5_mobile_det; recognition: latin_PP-OCRv5_mobile_rec; "
        f"device={device}",
        f"- Font: {args.font.resolve()}, size40; one line/image, black on white",
        f"- Exact after norm_text: {metrics['exact']}/{metrics['lines']}",
        f"- Accentless exact: {metrics['accentless']}/{metrics['lines']}",
        f"- CER có dấu: {metrics['edits']}/{metrics['characters']} = {metrics['cer']:.6f}",
        "",
        "| Reference | OCR |",
        "|---|---|",
    ]
    for reference, prediction in zip(LINES, predictions, strict=True):
        rows.append(f"| {reference} | {norm_text(prediction).replace('|', '&#124;')} |")
    report = "\n".join(rows) + "\n"
    output = Path("results") / f"ocr-diacritics-smoke-{date.today():%Y%m%d}.md"
    write_report(report, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
