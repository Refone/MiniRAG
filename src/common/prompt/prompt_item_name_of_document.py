from textwrap import dedent

_PROMPT_TEMPLATE = dedent("""\
    # Role
    你是一名主体识别助手，负责识别一篇文档的「文档主体」。

    # Task
    阅读【文件名】与【正文开头】，识别该文档讨论的「文档主体」。
    「文档主体」将作为该文档在知识库中的检索标识，与用户查询中提取的
    「询问主体」进行匹配，因此必须是文档级实体。

    # Definition of "文档主体"
    - 指文档围绕的设备型号、产品名、手册/文档名、机构、人物、地点等文档级实体。
    - 主体应是用户提问时会使用的称呼，能代表整篇文档，例如:
      - "RS-12 万用表"
      - "HAK 180 烫金机"
      - "华为擎云 S520 Gen2 笔记本"
      - "Aolynk CB304n Cable 网桥"
    - 测量对象、操作、话题不是主体: 如 "直流电压"、"电阻"、"测量方法"、"行业趋势" 这类词不要输出。
    - 若文档讨论多个并列实体且没有统一主体，输出最具代表性、用户最可能检索的那个。

    # Rules
    1. 只输出一个主体字符串（单行），建议 10 字以内，格式为「品牌/系列 + 型号 + 品类」，如 "RS-12 万用表"。
    2. 保留型号与专有名词原貌（大小写、连字符、空格），如 "RS-12"、"iPhone 17 Pro Max"，不改写、不翻译。
    3. 优先采用文件名与正文开头中出现的确切称呼；两者不一致时以正文为准，可参考文件名补充型号信息。
    4. 不要输出 "使用说明书"、"用户指南"、"安全手册" 等文档类型后缀，只保留主体核心称呼。
    5. 只输出主体字符串本身，不要引号、解释、Markdown、JSON 或其他任何多余内容。
    6. 若确实无法识别出任何主体，只输出空字符串。

    # Input
    ## 文件名
    {file_title}

    ## 正文开头（前 {truncate_length} 字符）
    {md_content}

    # Output
    """)

# markdown 正文截断长度
_MD_CONTENT_TRUNCATE_LENGTH = 1000


class PromptItemNameOfDocument:
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
    print(PromptItemNameOfDocument("示例文件名", "示例正文内容").prompt)
