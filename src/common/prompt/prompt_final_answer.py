from textwrap import dedent

_IMAGE_RULES = dedent("""\
    图片使用规则（与答案直接相关的图片应主动内嵌，避免遗漏）：
    - 参考内容中的图片有两种形式：Markdown 形式 ![说明](图片URL)，或 HTML 形式 <img src="图片URL" alt="说明">。无论哪种形式，图片 URL 一律逐字符原样复制，不得截断、猜测或拼接；图片 URL 可能是完整的 http(s) 链接，也可能是以 /api/files/ 开头的站内路径，两种形态都是完整可用的图片地址，按原样输出即可。
    - 当回答覆盖了某张图对应的内容（例如参考内容中出现“如图 X 所示”“图 X 展示了……”等表述）时，应把该图内嵌在对应文字附近，禁止把图片统一堆放到回答末尾。原文即使是 HTML <img> 标签，也必须转换为 Markdown 语法输出，格式为：![简要说明](图片URL)；禁止原样输出 HTML 标签。
    - 回答正文中不要出现“如图 X 所示”“见图 X”“上图/下图”等图编号引用（最终展示的图片不带图注编号），直接把图片内嵌在相关文字处即可。
    - 多张相关图片适合并列展示时，请将它们连续输出（图片之间不要插入文字或空行），前端会自动并排展示；每张图片或图片组与前后文字之间请留空行，让图片单独成段。
    - 简要说明优先采用图片图注的描述文字（去掉“图 1.3”这类编号，如“智能体决策时间与质量关系图”）或 alt 描述的简短概括；说明文字应简短，不打断阅读。
    - 同一图片 URL 不要重复输出；与答案内容无关的图片不要输出。
    - 正文中不得裸写图片 URL，也不得输出任何 HTML 标签（包括 <img>）；图片一律用 Markdown 语法内嵌。""").strip()

_LIBRARY_HEADER = (
    "你是一个严谨、忠于给定资料的智能助手。"
    "请基于【参考内容】和【历史对话】回答【用户问题】。"
)

_FALLBACK_HEADER = (
    "你是一个严谨、乐于助人的智能助手。"
    "请综合【检索状态】、【参考内容】和【历史对话】回答【用户问题】。"
)

_LIBRARY_RULES: list[str] = [
    "当【参考内容】能够回答问题（或部分回答）时，只使用其中可验证的信息作答，"
    "不要编造、推测或补充参考内容中不存在的事实。",
    "除兜底声明外，回答时不要写“根据参考内容”“参考内容显示”等类似表述，直接给出答案。",
    "在相关内容同等相关的前提下，优先采用数据来源标记为 Milvus 的内容；"
    "若 Milvus 内容与问题无关，则不要强行使用。",
    "【历史对话】仅用于理解用户问题的上下文、指代和追问关系，不作为事实依据；"
    "事实性信息应以【参考内容】为准。",
    "如果【参考内容】不足以回答该问题，必须在回答的第一句说明“文库中未检索到与该问题相关的内容”，"
    "然后按以下顺序兜底：①【参考内容】中有网络搜索结果时，基于网络结果作答，"
    "并说明依据是网络搜索；② 没有可用的网络结果时，使用通识知识简短作答，"
    "并说明这是大模型的通识回答。兜底内容不得伪装成参考内容中的事实，"
    "也不得编造来源或链接。",
    "回答应简洁、准确；如问题较复杂，可使用分点或步骤说明。",
    _IMAGE_RULES,
    "使用与【用户问题】一致的语言作答。",
]

_FALLBACK_RULES: list[str] = [
    "本次未从文库中检索到相关内容。【检索状态】会说明是否有网络搜索结果："
    "必须在回答的第一句明确指出“未在文库中检索到相关内容”，"
    "并按检索状态说明随后依据是“网络搜索结果”还是“大模型的通识回答”，"
    "不得省略或弱化这条声明。",
    "检索状态含网络搜索结果时，以【参考内容】中的网络摘要为主要依据作答，"
    "可用通识知识补充背景，但不得编造参考内容中不存在的来源、链接或事实。",
    "检索状态表明没有网络搜索结果时，直接使用通识知识作答，"
    "并说明这是大模型的通识回答；不得假装引用了任何资料。",
    "回答时不要写“根据参考内容”“参考内容显示”等类似表述，直接给出答案。",
    "【历史对话】仅用于理解用户问题的上下文、指代和追问关系，不作为事实依据。",
    "【疑似文档】列出的是文库中置信度不足的文档标题；若明显与问题相关，"
    "可用一句话提示“你可能想找的是《…》”，否则不要提及。",
    "回答应简洁、准确；如问题较复杂，可使用分点或步骤说明。",
    _IMAGE_RULES,
    "使用与【用户问题】一致的语言作答。",
]


def _format_rules(rules: list[str]) -> str:
    return "\n".join(f"{index}. {rule}" for index, rule in enumerate(rules, start=1))


class PromptFinalAnswer:
    """最终答案提示词。

    两种模式：
    - library：命中文库文档，资料充足时严格依据【参考内容】作答；
      资料不足时先声明未检索到相关内容，再按网络搜索 → 通识兜底；
    - fallback：未命中文库，允许网络摘要与通识作答，并要求首句声明依据。

    示例实例（fallback，未命中文库但拿到网络结果）：
        PromptFinalAnswer(
            reference="---\\n数据来源: Web, 置信度: 0.83000000,\\n内容: 上海今日多云\\n",
            history="",
            question="今天上海天气如何",
            no_doc_match=True,
            suspect_titles=["万用表RS-12的使用"],
        )
    """

    def __init__(
        self,
        reference: str,
        history: str,
        question: str,
        *,
        no_doc_match: bool = False,
        suspect_titles: list[str] | None = None,
    ):
        self.prompt = (
            self._build_fallback(reference, history, question, suspect_titles or [])
            if no_doc_match
            else self._build_library(reference, history, question)
        )

    @staticmethod
    def _build_library(reference: str, history: str, question: str) -> str:
        return (
            f"{_LIBRARY_HEADER}\n\n"
            f"回答要求：\n{_format_rules(_LIBRARY_RULES)}\n\n"
            f"【参考内容】\n{reference}\n\n"
            f"【历史对话】\n{history if history else '无历史对话'}\n\n"
            f"【用户问题】\n{question}\n\n"
            "请回答：\n"
        )

    @staticmethod
    def _build_fallback(
        reference: str,
        history: str,
        question: str,
        suspect_titles: list[str],
    ) -> str:
        has_web_reference = bool(reference.strip())
        retrieval_status = (
            "未在文库中检索到相关内容；参考内容为网络搜索结果。"
            if has_web_reference
            else "未在文库中检索到相关内容，且没有可用的网络搜索结果。"
        )
        reference_text = reference if has_web_reference else "（无参考资料）"
        suspects = "".join(f"《{title}》" for title in suspect_titles) or "（无）"

        return (
            f"{_FALLBACK_HEADER}\n\n"
            f"回答要求：\n{_format_rules(_FALLBACK_RULES)}\n\n"
            f"【检索状态】\n{retrieval_status}\n\n"
            f"【参考内容】\n{reference_text}\n\n"
            f"【疑似文档】\n{suspects}\n\n"
            f"【历史对话】\n{history if history else '无历史对话'}\n\n"
            f"【用户问题】\n{question}\n\n"
            "请回答：\n"
        )


if __name__ == "__main__":
    library_prompt = PromptFinalAnswer(
        reference="---\n数据来源: Milvus, 置信度: 0.95000000,\n内容: 这是参考内容\n",
        history="这是历史信息",
        question="HAK 180 一定要放平使用吗?",
    )
    fallback_prompt = PromptFinalAnswer(
        reference="---\n数据来源: Web, 置信度: 0.83000000,\n内容: 上海今日多云\n",
        history="",
        question="今天上海天气如何",
        no_doc_match=True,
        suspect_titles=["万用表RS-12的使用"],
    )
    for name, prompt in (("library", library_prompt), ("fallback", fallback_prompt)):
        print("=" * 20, f" {name} Prompt ", "=" * 20)
        print(prompt.prompt)
