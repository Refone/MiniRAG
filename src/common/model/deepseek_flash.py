from langchain_deepseek import ChatDeepSeek

from common.config.app_config import APP_CONFIG
from common.config.env_config import ENV_CONFIG
from common.model.rate_limiter import SlidingWindowRateLimiter


class DeepSeekFlash(ChatDeepSeek):
    """DeepSeek 模型封装：原生限速 + 关闭思考模式。

    继承自 ChatDeepSeek（即 BaseChatModel），因此 bind_tools / with_structured_output /
    回调 / 批处理 / 流式等全部原生可用；限速由 LangChain 在每条调用路径上自动执行。
    """

    def __init__(
        self,
        model: str = ENV_CONFIG.dashscope.llm_model,
        api_key: str = ENV_CONFIG.dashscope.api_key,
        base_url: str = ENV_CONFIG.dashscope.base_url,
        **kwargs,
    ):
        kwargs.setdefault(
            "rate_limiter", SlidingWindowRateLimiter(ENV_CONFIG.dashscope.llm_rpm)
        )
        kwargs.setdefault(
            "request_timeout",
            (APP_CONFIG.tcp_reachability_timeout, APP_CONFIG.llm_request_timeout),
        )
        kwargs.setdefault("max_retries", APP_CONFIG.llm_request_retry_attempts)

        # 关闭思考模式
        kwargs.setdefault("extra_body", {})
        kwargs["extra_body"]["enable_thinking"] = False

        return super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        )


if __name__ == "__main__":
    import asyncio
    from rich import print as rprint

    async def test_ainvoke():
        # 示例调用
        response = await DeepSeekFlash().ainvoke("你好")
        rprint(response)

    asyncio.run(test_ainvoke())
