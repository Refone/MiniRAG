from textwrap import dedent

from pydantic import BaseModel, Field


class DocKeywordsAbstractPydantic(BaseModel):
    keywords: str = Field(description="文档关键词, 3-8 个, 英文逗号分隔")
    abstract: str = Field(description="文档摘要, 100-200 字")


_PROMPT_TEMPLATE = dedent("""\
    # Role
    你是知识库文档标注助手, 负责为一篇文档生成检索元数据。

    # Task
    阅读【文件名】与【正文开头】, 输出两项:
    1. keywords: 文档关键词, 3-8 个, 英文逗号分隔
    2. abstract: 文档摘要, 100-200 字, 概括文档主题、适用对象与主要内容

    # Definition
    - 关键词将参与知识库一级召回的精确匹配, 应覆盖:
      文档主体实体 (设备型号/产品名, 如 "RS-12"、"万用表")、品类、核心功能/场景,
      以及用户检索时可能使用的称呼。
    - 摘要将参与知识库一级召回的语义匹配并展示给用户, 需让用户快速判断
      该文档是否是自己要找的内容。

    # Rules
    1. 关键词保留型号与专有名词原貌 (大小写、连字符、空格), 如 "RS-12"、"iPhone 17 Pro Max", 不改写、不翻译。
    2. 关键词之间用英文逗号分隔, 不要使用中文逗号或顿号。
    3. 摘要用中文, 客观陈述, 不添加主观评价, 不引用原文大段内容。
    4. 仅输出 JSON, 不要解释、Markdown 代码块或多余文本。

    # Output Schema
    {{
        "keywords": "关键词1,关键词2,...",
        "abstract": "文档摘要"
    }}

    # Input
    ## 文件名
    {file_title}

    ## 正文开头（前 {truncate_length} 字符）
    {md_content}

    # Output
    """)

# markdown 正文截断长度 (摘要生成需要比主体识别更长的上下文)
_MD_CONTENT_TRUNCATE_LENGTH = 4000


class PromptDocKeywordsAbstract:
    def __init__(self, file_title: str, md_content: str):
        self.file_title = file_title
        self.prompt = _PROMPT_TEMPLATE.format(
            file_title=file_title,
            truncate_length=_MD_CONTENT_TRUNCATE_LENGTH,
            md_content=md_content[:_MD_CONTENT_TRUNCATE_LENGTH],
        )

    def __str__(self) -> str:
        return self.prompt


if __name__ == "__main__":
    print(PromptDocKeywordsAbstract("示例文件名", "示例正文内容").prompt)
