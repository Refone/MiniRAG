"""模型访问器守卫：默认套件里访问真实模型直接失败。"""

import pytest


def _forbidden(name: str):
    def _accessor(*args, **kwargs):
        raise AssertionError(
            f"默认测试禁止访问真实模型访问器 {name}；"
            "请用 tests.support.seams.patch_accessors 注入 fake"
        )

    return _accessor


def install_model_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 common.model 的角色访问器替换为“一调用就失败”的守卫。

    必须用 autouse fixture 安装并随 monkeypatch 还原：若在 conftest import 时
    全局替换，pytest 收集所有目录时也会污染 live 层，导致真模型测试被拦截。
    """
    import common.model as model

    for name in ("get_llm", "get_vlm", "get_embedding", "get_reranker"):
        monkeypatch.setattr(model, name, _forbidden(name))
