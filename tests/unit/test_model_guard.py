import pytest

from common import model

pytestmark = pytest.mark.unit


def test_model_guard__direct_accessor__raises():
    """Given unit 层的模型守卫
    When 直接调用真实模型访问器
    Then 立即 AssertionError，避免默认套件误连真实模型
    """
    with pytest.raises(AssertionError, match="禁止访问真实模型访问器 get_llm"):
        model.get_llm()
