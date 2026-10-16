from textwrap import dedent

_QUERY_REWRITE_PROMPT_TEMPLATE = dedent("""\
    # Role
    你是一名查询改写助手，负责把用户的最新问题改写成一个「信息完整、可独立理解」的新查询。

    # Task
    结合【历史记录】与【当前查询】，消除指代（如“它/他/这个/那个/上面说的”）、
    补全省略信息，输出一个无需依赖上下文即可被下游任务理解的完整查询。

    # Rules
    1. 只改写，不回答、不解释、不扩展用户未问的内容。
    2. 保留用户原始意图与语气，不要改变问题类型（问什么就还是问什么）。
    3. 若当前查询已信息完整、无需补全，则原样输出。
    4. 若历史记录为空或不相关，则以当前查询为准，做最小必要的补全。
    5. 保持原语言，不要翻译。
    6. 只输出改写后的查询文本本身，不要加引号、前缀、解释或 Markdown。

    # Input
    ## 历史记录
    {history_text}

    ## 当前查询
    {user_query}

    # Output
    改写后的完整查询：
    """)


class PromptQueryRewrite:
    def __init__(self, history_summary: str, original_query: str):
        self.history_summary = history_summary
        self.original_query = original_query
        self.prompt = _QUERY_REWRITE_PROMPT_TEMPLATE.format(
            history_text=history_summary,
            user_query=original_query,
        )

    def __str__(self) -> str:
        return self.prompt


if __name__ == "__main__":
    from common.model import LLM

    history_summary = dedent("""\
    编号 1 | 用户提问 | 你能告诉我 Iphone 17 Pro Max 的硬件配置吗？
    编号 2 | 助手回答 | 当然可以，Iphone 17 Pro Max 的硬件配置如下: CPU、GPU、内存、存储等。
    """)
    original_query = "它的售价是多少？"
    prompt_instance = PromptQueryRewrite(history_summary, original_query)
    print("=" * 20, " Prompt Instance ", "=" * 20)
    print(prompt_instance)
    print("=" * 20, " LLM Response ", "=" * 20)
    llm_response = LLM.invoke(prompt_instance.prompt)
    print(llm_response.content)
