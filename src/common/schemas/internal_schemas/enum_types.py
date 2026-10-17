from enum import StrEnum
from pathlib import Path


class DocTypeEnum(StrEnum):
    UNKNOWN = "<unk>"
    PDF = "pdf"
    MARKDOWN = "markdown"

    @classmethod
    def from_filename(cls, filename: str) -> "DocTypeEnum":
        """
        根据文件名后缀判断文档类型, 无法识别时返回 UNKNOWN。
        """
        ext = Path(filename).suffix.lower().lstrip(".")
        return {
            "pdf": DocTypeEnum.PDF,
            "md": DocTypeEnum.MARKDOWN,
            "markdown": DocTypeEnum.MARKDOWN,
        }.get(ext, DocTypeEnum.UNKNOWN)

    @staticmethod
    def to_str(doc_type: "DocTypeEnum") -> str:
        """
        将 DocType 转换为字符串表示。
        """
        return doc_type.value


if __name__ == "__main__":
    from rich import print as rprint

    for name in ("a.pdf", "b.MD", "c.markdown", "d.unknown"):
        rprint(f"{name!r:>14} -> {DocTypeEnum.from_filename(name)!r}")
