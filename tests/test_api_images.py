import io
import struct
import zlib

import pytest

Image = pytest.importorskip("PIL.Image")


@pytest.mark.parametrize(
    "format,mime,suffix", [("JPEG", "image/jpeg", ".jpg"), ("PNG", "image/png", ".png")]
)
def test_upload_accepts_real_images_without_changing_bytes(format, mime, suffix):
    from vireceipt.api_images import validate_image

    stream = io.BytesIO()
    Image.new("RGB", (2, 3), "red").save(stream, format=format)
    payload = stream.getvalue()
    assert validate_image(payload, mime + "; charset=binary") == suffix
    assert stream.getvalue() == payload


@pytest.mark.parametrize(
    "scenario,status",
    [
        ("empty", 422),
        ("mime", 415),
        ("mismatch", 415),
        ("broken", 422),
        ("large", 413),
        ("frames", 422),
    ],
)
def test_bad_uploads_have_stable_errors(scenario, status):
    from vireceipt.api_images import MAX_BYTES, UploadError, validate_image

    stream = io.BytesIO()
    image = Image.new("RGB", (2, 3), "red")
    image.save(stream, format="PNG")
    payload, mime = stream.getvalue(), "image/png"
    if scenario == "empty":
        payload = b""
    elif scenario == "mime":
        mime = "application/octet-stream"
    elif scenario == "mismatch":
        mime = "image/jpeg"
    elif scenario == "broken":
        payload = payload[:20]
    elif scenario == "large":
        payload = b"x" * (MAX_BYTES + 1)
    else:
        stream = io.BytesIO()
        image.save(
            stream, format="PNG", save_all=True, append_images=[Image.new("RGB", (2, 3), "blue")]
        )
        payload = stream.getvalue()
    with pytest.raises(UploadError) as caught:
        validate_image(payload, mime)
    assert caught.value.status_code == status


def test_huge_dimensions_are_rejected_without_decoding_pixels():
    from vireceipt.api_images import MAX_PIXELS, UploadError, validate_image

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    payload = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", MAX_PIXELS + 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )
    with pytest.raises(UploadError) as caught:
        validate_image(payload, "image/png")
    assert caught.value.status_code == 413


def test_truncated_jpeg_pixels_are_rejected_before_backend_use():
    from vireceipt.api_images import UploadError, validate_image

    stream = io.BytesIO()
    Image.new("RGB", (2, 3), "red").save(stream, format="JPEG")
    with pytest.raises(UploadError) as caught:
        validate_image(stream.getvalue()[:-2], "image/jpeg")
    assert caught.value.status_code == 422
