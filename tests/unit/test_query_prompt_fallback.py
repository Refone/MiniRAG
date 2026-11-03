"""查询兜底 prompt 分支单测（零外部依赖）。

覆盖 library / fallback 两种回答模式的模板组装：资料充足时的引用约束、
资料不足时的声明与通识兜底、以及疑似文档提示。
"""

import pytest

from common.prompt.prompt_final_answer import PromptFinalAnswer

pytestmark = pytest.mark.unit

WEB_REFERENCE = "---\n数据来源: Web, 置信度: 0.83000000,\n内容: 上海今日多云\n\n---\n"
MILVUS_REFERENCE = (
    "---\n数据来源: Milvus, 置信度: 0.95000000,\n内容: 断电量程切换\n\n---\n"
)


def test_library_prompt_grounded_with_insufficiency_fallback():
    prompt = PromptFinalAnswer(
        reference=MILVUS_REFERENCE,
        history="",
        question="如何用 RS-12 测量电阻",
    ).prompt

    assert (
        "当【参考内容】能够回答问题（或部分回答）时，只使用其中可验证的信息作答"
        in prompt
    )
    # 资料不足时不再直接拒答: 先声明, 再按网络 → 通识兜底
    assert "文库中未检索到与该问题相关的内容" in prompt
    assert "并说明这是大模型的通识回答" in prompt
    assert "参考内容中未提供足够信息以回答该问题" not in prompt
    assert "【检索状态】" not in prompt


def test_library_prompt_includes_history():
    prompt = PromptFinalAnswer(
        reference=MILVUS_REFERENCE,
        history="用户此前问过量程",
        question="继续",
    ).prompt

    assert "用户此前问过量程" in prompt
    assert "无历史对话" not in prompt


def test_fallback_prompt_declares_no_match_with_web():
    prompt = PromptFinalAnswer(
        reference=WEB_REFERENCE,
        history="",
        question="今天上海天气如何",
        no_doc_match=True,
        suspect_titles=["万用表RS-12的使用"],
    ).prompt

    assert "未在文库中检索到相关内容；参考内容为网络搜索结果。" in prompt
    assert "第一句" in prompt
    assert "网络搜索结果" in prompt
    assert "《万用表RS-12的使用》" in prompt
    assert "参考内容中未提供足够信息" not in prompt


def test_fallback_prompt_general_answer_without_reference():
    prompt = PromptFinalAnswer(
        reference="",
        history="",
        question="给我讲个笑话",
        no_doc_match=True,
    ).prompt

    assert "未在文库中检索到相关内容，且没有可用的网络搜索结果。" in prompt
    assert "（无参考资料）" in prompt
    assert "（无）" in prompt
    assert "大模型的通识回答" in prompt
