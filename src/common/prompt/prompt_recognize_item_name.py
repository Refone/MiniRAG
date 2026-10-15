from textwrap import dedent

_PROMPT_TEMPLATE = dedent("""\
    请从以下信息中总结文章主体：

    文件名：{file_title}

    正文(前{truncate_length}字符):
    {md_content}

    要求：
    1. 1. 返回内容为字符串形式，提炼文章讨论的核心主体/主题,可以是短语而非完整句子。
    例如：
    - 苏伯尓5000W大功率电磁炉
    - 2025年AI芯片行业趋势
    - 深度学习
    2. 返回结果应该只包含总结内容，不要添加任何解释、前缀、引号或其他内容。
    3. 语言精简，尽量使用单一名词，避免修饰词。
    4. 如果无法识别文章主体，请返回空字符串。""")

# markdown 正文截断长度
_MD_CONTENT_TRUNCATE_LENGTH = 1000


class PromptRecognizeItemName:
    def __init__(self, file_title: str, md_content: str):
        self.file_title = file_title
        self.md_content = md_content
        self.prompt = _PROMPT_TEMPLATE.format(
            file_title=file_title,
            truncate_length=_MD_CONTENT_TRUNCATE_LENGTH,
            md_content=md_content[:_MD_CONTENT_TRUNCATE_LENGTH],
        )

    def __str__(self) -> str:
        return self.prompt


if __name__ == "__main__":
    print(PromptRecognizeItemName("示例文件名", "示例正文内容").prompt)
