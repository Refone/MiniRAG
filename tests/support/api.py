"""API 契约测试的小工具。"""


def override_dependency(app, provider, fake) -> None:
    """用 fake 覆盖 FastAPI 依赖（provider 必须是路由 Depends 的同一函数对象）。"""
    app.dependency_overrides[provider] = lambda: fake
