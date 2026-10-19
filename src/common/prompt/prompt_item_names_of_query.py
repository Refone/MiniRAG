from textwrap import dedent

from pydantic import BaseModel, Field


class ItemNamesOfQueryPydantic(BaseModel):

    item_names: list[str] = Field(
        description="识别出的询问主体列表，若无法确定询问主体则为空列表"
    )


_ITEM_NAMES_OF_QUERY_PROMPT_TEMPLATE = dedent("""\
    # Role
    你是一名主体识别助手，负责从查询中提炼出「询问主体」。

    # Task
    阅读【历史记录】与【查询】，抽取用户在本次查询中真正想了解的「询问主体」。
    「询问主体」将用于在文档库中匹配对应的说明书/文档，因此必须是文档级实体。

    # Definition of "询问主体"
    - 指文档级实体: 设备型号（如 "RS-12"）、产品名（如 "万用表"）、手册/文档名、机构、人物、地点等，能在文档库中定位到具体文档的实体。
    - 测量对象或话题不是主体: 如 "直流电压"、"电阻"、"测量方法" 这类词不抽取。
    - 只抽取明确出现或可明确指代的主体，不做过度联想。
    - 不抽取修饰词、动作、时间状语、疑问词等非主体成分。
    - 若无法确定任何询问主体，返回空列表 []。

    # Rules
    1. 每个主体为简洁短语（建议 10 字以内），保留型号与专有名词原貌（如 "RS-12"）。
    2. 保持原文语言，不改写专有名词。
    3. 若当前查询省略了主体（如 "怎么测电压"），但历史记录中已明确主体（如 "RS-12 万用表"），则从历史记录中继承该主体。
    4. 若历史记录为空或不相关，则只依据查询本身抽取。
    5. 去重并保持出现顺序。
    6. 仅输出 JSON，不要添加解释、Markdown 代码块或多余文本。

    # Output Schema
    {{
        "item_names": ["主体1", "主体2", "..."]
    }}

    # Input
    ## 历史记录
    {history_text}

    ## 查询
    {query}

    # Output
    """)


class PromptItemNamesOfQuery:
    def __init__(self, query: str, history_text: str = ""):
        self.query = query
        self.prompt = _ITEM_NAMES_OF_QUERY_PROMPT_TEMPLATE.format(
            history_text=history_text if history_text else "（无历史记录）",
            query=self.query,
        )

    def __str__(self) -> str:
        return self.prompt


if __name__ == "__main__":
    from common.model import LLM

    query_rewrite = "特斯拉 Model Y 和华为尊界比哪个好？"
    prompt_instance = PromptItemNamesOfQuery(query=query_rewrite)
    print("=" * 20, " Prompt Instance ", "=" * 20)
    print(prompt_instance)
    print("=" * 20, " LLM Response ", "=" * 20)
    llm_response = LLM.invoke(prompt_instance.prompt)
    print(llm_response.content)
