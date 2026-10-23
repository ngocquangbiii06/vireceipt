"""Resource bounds and structural validation for binary receipt uploads."""

import io
import warnings

from PIL import Image

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 25_000_000
_FORMATS = {"image/jpeg": ("JPEG", ".jpg"), "image/png": ("PNG", ".png")}


class UploadError(ValueError):
    """Stable HTTP status and code without decoder or filesystem details."""

    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code, self.code = status_code, code


def validate_image(payload: bytes, content_type: str) -> str:
    """Validate one bounded JPEG/PNG without altering its bytes; return a safe suffix."""
    media_type = content_type.partition(";")[0].strip().lower()
    if media_type not in _FORMATS:
        raise UploadError(415, "unsupported_media_type")
    if not payload:
        raise UploadError(422, "empty_image")
    if len(payload) > MAX_BYTES:
        raise UploadError(413, "image_too_large")
    expected, suffix = _FORMATS[media_type]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as image:
                if image.format != expected:
                    raise UploadError(415, "image_type_mismatch")
                if image.width * image.height > MAX_PIXELS:
                    raise UploadError(413, "image_too_large")
                if getattr(image, "n_frames", 1) != 1:
                    raise UploadError(422, "multiple_frames")
                image.verify()
            with Image.open(io.BytesIO(payload)) as image:
                image.load()
    except UploadError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise UploadError(413, "image_too_large") from error
    except (OSError, ValueError, SyntaxError) as error:
        raise UploadError(422, "invalid_image") from error
    return suffix
