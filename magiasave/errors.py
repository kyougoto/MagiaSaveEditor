"""统一错误类型。错误码前缀对齐客户端 save_* 约定，便于排查。"""


class ArchiveError(Exception):
    """存档容器层面的错误（zip / manifest / 校验）。"""

    code = "archive_error"

    def __init__(self, message, code=None):
        super().__init__(message)
        if code:
            self.code = code


class FormatError(ArchiveError):
    """字节格式不合法（zip 结构、head/part 协议）。"""

    code = "format_error"


class ValidationError(ArchiveError):
    """语义校验失败（profile 字段、preferences、路径白名单）。"""

    code = "validation_error"
