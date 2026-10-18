from textwrap import dedent

_RERANK_TEXT_REFINE_PROMPT = dedent("""\
    你现在是文本精简提炼专家。请基于以下的问答，对回答文本进行精炼。
    问题:{question}
    回答:{answer}
    1. 保留核心语义、关键信息、逻辑要点，删除废话、客套话、重复表述、修饰冗余语句；
    2. 不改变原有事实、不新增编造信息、不曲解原意；
    3. 输出精简后的合并文本，语言凝练、短句为主，适合向量化嵌入；
    4. 不要分点、不要解释、不要多余话术，只输出精简结果。
    5. 精炼后的回答不超过{limit}字
    """)
# 第 8 条是一条格式约束的最终强化, 大模型在长指令下容易“遗忘”前面的要求，所以最后补一句，相当于最后通牒
# 末尾单独的 hypo_answer 是一个输出起点的锚点，利用了大模型的“续写惯性”


class PromptRerankRefineText:
    def __init__(self, question: str, answer: str, limit: int):
        self.prompt = _RERANK_TEXT_REFINE_PROMPT.format(
            question=question,
            answer=answer,
            limit=limit,
        )


if __name__ == "__main__":
    from common.model import LLM
    from utils.path_utils import PROJECT_ROOT

    question = "HAK 180 一定要放平使用吗"
    # load 整段 output/markdown-folder/hak180产品安全手册/hak180产品安全手册_fixed.md
    with open(
        PROJECT_ROOT
        / "output/markdown-folder/hak180产品安全手册/hak180产品安全手册_fixed.md",
        "r",
        encoding="utf-8",
    ) as f:
        md = f.read()

    prompt_instance = PromptRerankRefineText(question, md, 500)
    print("=" * 20, " Prompt Instance ", "=" * 20)
    print(prompt_instance.prompt)
    print("=" * 20, " LLM Response ", "=" * 20)
    llm_response = LLM.invoke(prompt_instance.prompt)
    print(llm_response.content)
