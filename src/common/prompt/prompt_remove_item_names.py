from textwrap import dedent

_REMOVE_ITEM_NAMES_PROMPT = dedent("""\
    你是一个 RAG 查询净化器(Query Sanitizer), 不是问答助手。
    你的唯一任务是从用户 query 中剔除 item_names 指定的产品/主体名称,
    避免 rerank 时收到主体名关键字干扰, 出现得分虚高。

    用户问题: {query}

    需要剔除的关键词(item_names):
    {item_names}

    必须遵守的规则：
    1. 只删除 item_names 中列出的主体名及其明显变体, 包括大小写差异、全半角差异、空格差异、连字符差异。按“最长优先”匹配, 避免删除完整主体后残留品牌前缀。
    2. 不要删除 item_names 未列出的实体。不要单独删除 item_names 的公共子片段, 除非该片段本身也是 item_names 中的独立项且完整匹配。
    3. 必须保留 query 中的意图词：动作、功能、操作、属性、条件、数量、时间、场景、比较关系、疑问点。例如“四指操作、触控板手势、怎么设置、有什么区别、价格、续航、接口”等不能删。
    4. 删除主体名后, 可以删除或调整因此变得不通顺的虚词, 如“的、了、在、上、关于、给我说说、请”等；可以轻量改写为自然检索短语或问句, 但不得增加新信息、不得改变原意、不得回答 query。
    5. 如果 query 中同一个主体名出现多次, 全部删除。
    6. 对于比较、并列、指代类 query, 删除具体主体名后可用“该产品、该设备、该功能、前者、后者”等泛化指代保留关系；如果仍无法保持语义完整, 则安全回退。
    7. 如果剔除后为空、只剩客套话、或语义严重不完整且无法安全改写, 则原样返回原始 query。不要编造主体或意图。
    8. 如果 item_names 为空, 或 query 中不包含 item_names 中任何主体名, 则原样返回原始 query。
    9. 输出格式：只输出一个纯文本字符串, 即净化后的 clean_query。不要输出 JSON, 不要输出字段名, 不要输出解释, 不要加引号, 不要加 Markdown 代码块, 不要输出多行。

    净化后的问题:
    """)
# 第 8 条是一条格式约束的最终强化, 大模型在长指令下容易“遗忘”前面的要求, 所以最后补一句, 相当于最后通牒
# 末尾单独的 hypo_answer 是一个输出起点的锚点, 利用了大模型的“续写惯性”


class PromptRerankQuerySanitizer:
    def __init__(self, query: str, item_names: list[str]):
        self.prompt = _REMOVE_ITEM_NAMES_PROMPT.format(
            query=query,
            item_names=item_names,
        )


if __name__ == "__main__":
    from common.model import LLM
    from utils.path_utils import PROJECT_ROOT

    prompt_instance = PromptRerankQuerySanitizer(
        query="HAK 180 一定要放平使用吗",
        item_names=[
            "HAK 180 烫金机",
        ],
    )
    print("=" * 20, " Prompt Instance ", "=" * 20)
    print(prompt_instance.prompt)
    print("=" * 20, " LLM Response ", "=" * 20)
    llm_response = LLM.invoke(prompt_instance.prompt)
    print(llm_response.content)
