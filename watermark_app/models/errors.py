from enum import StrEnum


class ErrorCode(StrEnum):
    SUCCESS = "SUCCESS"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FORMAT_UNSUPPORTED = "FORMAT_UNSUPPORTED"
    WATERMARK_NOT_FOUND = "WATERMARK_NOT_FOUND"
    WATERMARK_TIMEOUT = "WATERMARK_TIMEOUT"
    WATERMARK_TEXT_TOO_LONG = "WATERMARK_TEXT_TOO_LONG"
    WATERMARK_TEXT_EMPTY = "WATERMARK_TEXT_EMPTY"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
    IMAGE_CORRUPTED = "IMAGE_CORRUPTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    def __init__(self, code: ErrorCode, detail: str = ""):
        self.code = code
        self.detail = detail
        self._messages = {
            ErrorCode.SUCCESS: "成功",
            ErrorCode.FILE_NOT_FOUND: "文件不存在或无法读取",
            ErrorCode.FORMAT_UNSUPPORTED: "不支持的图片格式",
            ErrorCode.WATERMARK_NOT_FOUND: "图片中未检测到水印",
            ErrorCode.WATERMARK_TIMEOUT: "处理超时",
            ErrorCode.WATERMARK_TEXT_TOO_LONG: "水印文本过长（最大1024字符）",
            ErrorCode.WATERMARK_TEXT_EMPTY: "水印文本为空",
            ErrorCode.IMAGE_TOO_LARGE: "图片尺寸超限",
            ErrorCode.IMAGE_CORRUPTED: "图片文件损坏",
            ErrorCode.INTERNAL_ERROR: "未知内部错误",
        }

    @property
    def message(self) -> str:
        return self._messages.get(self.code, str(self.code))

    def is_success(self) -> bool:
        return self.code == ErrorCode.SUCCESS

    def to_dict(self) -> dict:
        return {
            "error_code": str(self.code),
            "error": self.message,
            "detail": self.detail,
        }
