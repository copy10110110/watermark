from watermark_app.models.errors import ErrorCode, AppError


def test_all_error_codes_defined():
    expected = {
        "SUCCESS", "FILE_NOT_FOUND", "FORMAT_UNSUPPORTED",
        "WATERMARK_NOT_FOUND", "WATERMARK_TIMEOUT",
        "WATERMARK_TEXT_TOO_LONG", "WATERMARK_TEXT_EMPTY",
        "IMAGE_TOO_LARGE", "IMAGE_CORRUPTED", "INTERNAL_ERROR",
    }
    assert set(ErrorCode) == expected


def test_error_code_is_string():
    assert isinstance(ErrorCode.SUCCESS, str)
    assert ErrorCode.SUCCESS == "SUCCESS"


def test_app_error_creation():
    err = AppError(ErrorCode.FILE_NOT_FOUND, "image.jpg")
    assert err.code == "FILE_NOT_FOUND"
    assert err.message
    assert err.detail == "image.jpg"


def test_app_error_to_dict():
    err = AppError(ErrorCode.FORMAT_UNSUPPORTED, "test.svg")
    d = err.to_dict()
    assert d["error_code"] == "FORMAT_UNSUPPORTED"
    assert "error" in d
    assert d["detail"] == "test.svg"


def test_app_error_is_success():
    err = AppError(ErrorCode.SUCCESS)
    assert err.is_success() is True
    err2 = AppError(ErrorCode.FILE_NOT_FOUND)
    assert err2.is_success() is False
