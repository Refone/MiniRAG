from textwrap import dedent

from pydantic import BaseModel, Field


class ConcludeKeywordsPydantic(BaseModel):

    key_words: list[str] = Field(
        description="询问主体列表，若无法确定询问主体则为空列表"
    )


_CONCLUDE_KEYWORDS_PROMPT_TEMPLATE = dedent("""\
    # Role
    你是一名信息抽取助手，负责从查询中提炼出「询问主体」。

    # Task
    阅读【查询】，抽取用户在本次查询中真正想了解的「询问主体」。

    # Definition of "询问主体"
    - 指查询中关注的实体，如人物、机构、产品、概念、事件、地点等。
    - 只抽取明确出现或可明确指代的主体，不做过度联想。
    - 不抽取修饰词、动作、时间状语、疑问词等非主体成分。
    - 若无法确定任何询问主体，返回空列表 []。

    # Rules
    1. 每个主体为简洁短语（建议 10 字以内）。
    2. 保持原文语言，不改写专有名词。
    3. 去重并保持出现顺序。
    4. 仅输出 JSON，不要添加解释、Markdown 代码块或多余文本。

    # Output Schema
    {{
        "key_words": ["主体1", "主体2", "..."]
    }}

    # Input
    ## 查询
    {query_rewrite}

    # Output
    """)


class PromptConcludeKeywords:
    def __init__(self, query_rewrite: str):
        self.query_rewrite = query_rewrite
        self.prompt = _CONCLUDE_KEYWORDS_PROMPT_TEMPLATE.format(
            query_rewrite=self.query_rewrite,
        )

    def __str__(self) -> str:
        return self.prompt


if __name__ == "__main__":
    from common.model import LLM

    query_rewrite = "特斯拉 Model Y 和华为尊界比哪个好？"
    prompt_instance = PromptConcludeKeywords(query_rewrite=query_rewrite)
    print("=" * 20, " Prompt Instance ", "=" * 20)
    print(prompt_instance)
    print("=" * 20, " LLM Response ", "=" * 20)
    llm_response = LLM.invoke(prompt_instance.prompt)
    print(llm_response.content)
