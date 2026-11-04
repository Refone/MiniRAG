from textwrap import dedent

from pydantic import BaseModel, Field


class DocKeywordsAbstractPydantic(BaseModel):
    keywords: str = Field(
        description="文档关键词, 3-5 个, 英文逗号分隔, 均为高区分度词"
    )
    abstract: str = Field(description="文档摘要, 100-200 字")


_PROMPT_TEMPLATE = dedent("""\
    # Role
    你是知识库文档标注助手, 负责为一篇文档生成检索元数据。

    # Task
    阅读【文件名】与【正文开头】, 输出两项:
    1. keywords: 文档关键词, 3-5 个, 英文逗号分隔
    2. abstract: 文档摘要, 100-200 字, 概括文档主题、适用对象与主要内容

    # Definition of "keywords"
    - 关键词参与知识库一级召回的精确匹配, 必须是「文档指纹」级词汇:
      用户搜到这些词时, 这篇文档应当排在前面 —— 每个词都要能把这篇文章与其他文档区分开。
    - 优先级: 型号/品牌/专有名词 (如 "RS-12"、"Brother"、"iPhone 17 Pro Max")
      > 本文档特有的技术点/功能 (如 "触摸板"、"扩展坞"、"快捷键")。
    - 禁止输出以下宽泛词 (它们出现在大多数同类文档中, 没有区分度):
      * 文档类型词: 手册、指南、教程、说明书、用户指南、FAQ 等
        (含 "产品安全手册"、"安装指南" 这类复合形式)
      * 品类大类: 设备、机器、产品、笔记本电脑、打印机、办公设备 等
      * 通用主题词: 安全、操作、规范、警告、维护、使用、方法、注意事项 等
    - 自检规则: 每个关键词都要能通过「换一篇同类文档, 这个词大概率不会出现」的检验;
      不通过就删掉, 不要输出。

    # Rules
    1. 关键词保留型号与专有名词原貌 (大小写、连字符、空格), 如 "RS-12"、"iPhone 17 Pro Max", 不改写、不翻译。
    2. 关键词之间用英文逗号分隔, 不要使用中文逗号或顿号。
    3. 宁缺毋滥: 凑不出 3 个高区分度词时输出 2-3 个即可, 不要用大类词凑数。
    4. 摘要用中文, 客观陈述, 不添加主观评价, 不引用原文大段内容。
    5. 仅输出 JSON, 不要解释、Markdown 代码块或多余文本。

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
