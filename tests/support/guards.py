"""模型访问器守卫：默认套件里访问真实模型直接失败。"""


def _forbidden(name: str):
    def _accessor(*args, **kwargs):
        raise AssertionError(
            f"默认测试禁止访问真实模型访问器 {name}；"
            "请用 tests.support.seams.patch_accessors 注入 fake"
        )

    return _accessor


def install_model_guard() -> None:
    """把 common.model 的角色访问器替换为“一调用就失败”的守卫。"""
    import common.model as model

    for name in ("get_llm", "get_vlm", "get_embedding", "get_reranker"):
        setattr(model, name, _forbidden(name))
