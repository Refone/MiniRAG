from textwrap import dedent

_HYPO_ANSWER_PROMPT = dedent("""\
    你是一个 RAG 检索增强系统中的“假设性回答生成器”。

    你的任务：根据用户查询，生成一段“假设性回答”文本。
    这段文本不会被当作最终答案，而是会被向量化，用来在知识库中检索更相关的真实文档。

    用户查询：
    {query}

    请生成 hypo_answer。要求：
    1. 只输出假设性回答正文，不要输出“假设性回答：”、标题、解释、Markdown 或任何前后缀。
    2. 采用客观、陈述性、说明性的语气，模拟知识库、技术文档、百科或产品手册中的理想答案段落。
    3. 围绕查询的核心意图展开，自然包含相关关键词、同义表达、关键实体和可能的上位/下位概念。
    4. 如果查询是一个问题，就直接回答它；如果查询是关键词或短语，就写成一段解释性文字。
    5. 可以合理推测和补全语义，但不要编造具体来源、URL、精确统计数字或虚假引用。
    6. 不要反问用户，不要写“我不知道”“无法确定”“需要更多信息”等。
    7. 长度控制在 100～300 字左右；如果查询较复杂，可适当扩展到 500 字以内。
    8. 输出必须是一段连续的 `hypo_answer` 字符串。

    hypo_answer:
    """)
# 第 8 条是一条格式约束的最终强化, 大模型在长指令下容易“遗忘”前面的要求，所以最后补一句，相当于最后通牒
# 末尾单独的 hypo_answer 是一个输出起点的锚点，利用了大模型的“续写惯性”


class PromptHypoAnswer:
    def __init__(self, query: str):
        self.query = query
        self.prompt = _HYPO_ANSWER_PROMPT.format(query=self.query)


if __name__ == "__main__":
    from common.model import LLM

    query = "MLGB-5000 开机自检亮红灯是什么原因？"
    prompt_instance = PromptHypoAnswer(query)
    print("=" * 20, " Prompt Instance ", "=" * 20)
    print(prompt_instance.prompt)
    print("=" * 20, " LLM Response ", "=" * 20)
    llm_response = LLM.invoke(prompt_instance.prompt)
    print(llm_response.content)
