from textwrap import dedent

from pydantic import BaseModel, Field


class ConcludeQueryResult(BaseModel):
    """意图识别输出的结构化结果，与提示词中的 JSON 字段一一对应。"""

    key_words: list[str] = Field(
        description="询问主体列表，若无法确定询问主体则为空列表"
    )
    conclude_query: str = Field(
        description="重写后的、包含询问主体的独立完整问题"
    )


_PROMPT_TEMPLATE = dedent("""\
    请根据历史会话和当前问题,提取用户询问的询问主体(key_words).
    0. 用户提问可能会切换主体,和历史会话不一致,所以,以当前用户问题为主进行识别和问题重写
    1. 如果能明确识别询问主体，请提取出来。可能有一个或多个，但不能重复。
    2. 如果用户使用了代词（如"这个"、"它"），请结合历史会话指代消解，确定询问主体。
    3. 如果无法确定询问主体,key_words 返回空列表。
    4. 请重新改写用户的问题(conclude_query),使其成为包含询问主体的独立完整问题。

    请直接返回JSON格式结果,格式如下:
    {{
        "key_words": ["主体A", "主体B"],
        "conclude_query": "关于主体A和主体B..."
    }}

    历史会话：
    {history_summary}

    当前用户问题：
    {original_query}""")


class PromptConcludeQuery:
    def __init__(self, history_summary: str, original_query: str):
        self.history_summary = history_summary
        self.original_query = original_query
        self.prompt = _PROMPT_TEMPLATE.format(
            history_summary=history_summary,
            original_query=original_query,
        )

    def __str__(self) -> str:
        return self.prompt
