from textwrap import dedent

_PROMPT_TEMPLATE = dedent("""\
    这是标题为 {md_title} markdown 文档中的一张图片,
    图片前面一小段文字为“{pre_text}”, 后面一小段文字为“{post_text}”,
    请以图片信息为主,上下文信息为辅,用中文简要总结这张图片的内容, 用于 markdown 图片标题,
    控制在 {summary_length} 字以内。""")

_SUMMARY_LENGTH = 50


class PromptImageSummary:
    def __init__(
        self,
        md_title: str,
        pre_text: str,
        post_text: str,
        summary_length: int = _SUMMARY_LENGTH,
    ):
        self.md_title = md_title
        self.pre_text = pre_text
        self.post_text = post_text
        self.prompt = _PROMPT_TEMPLATE.format(
            md_title=md_title,
            pre_text=pre_text,
            post_text=post_text,
            summary_length=summary_length,
        )

    def __str__(self) -> str:
        return self.prompt


if __name__ == "__main__":
    print(PromptImageSummary("示例标题", "示例前文", "示例后文").prompt)
