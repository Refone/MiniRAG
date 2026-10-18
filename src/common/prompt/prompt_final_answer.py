from textwrap import dedent

_FINAL_ANSWER_PROMPT = dedent("""\
    你是一个智能助手，请根据参考内容回答用户的问题。
    要求：
    1. 尽量基于【参考内容】和【用户问题】 作答，不要编造不存在的事实。
    2. 优先使用数据来源为 Milvus 的内容。
    3. 如果用户的问题需要通过图片来辅助说明(例如：外观、结构、接线、示意图等), 图片只能来自于本地切片文本中的图片，请在答案最后追加一个独立的图片区块，格式严格如下：
    【图片】
    <图片URL1>
    <图片URL2>
    （每行一个URL；如果没有合适图片则不要输出【图片】区块）

    【参考内容】
    {reference}

    【历史对话】
    {history}

    【用户问题】
    {question}

    请回答：
    """)
# 第 8 条是一条格式约束的最终强化, 大模型在长指令下容易“遗忘”前面的要求，所以最后补一句，相当于最后通牒
# 末尾单独的 hypo_answer 是一个输出起点的锚点，利用了大模型的“续写惯性”


class PromptFinalAnswer:
    def __init__(self, reference: str, history: str, question: str):
        self.prompt = _FINAL_ANSWER_PROMPT.format(
            reference=reference,
            history=history if history else "无历史对话",
            question=question,
        )


if __name__ == "__main__":
    from common.model import LLM

    question = "HAK 180 一定要放平使用吗?"
    prompt_instance = PromptFinalAnswer(
        reference="这是参考内容", history="这是历史信息", question=question
    )
    print("=" * 20, " Prompt Instance ", "=" * 20)
    print(prompt_instance.prompt)
