from langchain_deepseek import ChatDeepSeek

from common.model.rate_limiter import SlidingWindowRateLimiter
from common.config.env_config import ENV_CONFIG


class DeepSeekFlash(ChatDeepSeek):
    """DeepSeek 模型封装：原生限速 + 关闭思考模式。

    继承自 ChatDeepSeek（即 BaseChatModel），因此 bind_tools / with_structured_output /
    回调 / 批处理 / 流式等全部原生可用；限速由 LangChain 在每条调用路径上自动执行。
    """

    def __init__(
        self,
        model: str = ENV_CONFIG.llm.model_name,
        api_key: str = ENV_CONFIG.llm.api_key,
        base_url: str = ENV_CONFIG.llm.base_url,
        **kwargs,
    ):
        kwargs.setdefault("rate_limiter", SlidingWindowRateLimiter(ENV_CONFIG.llm.rpm))
        kwargs.setdefault("extra_body", {"thinking": {"type": "disabled"}})
        # 防 API 挂起: 连接超时 10s + 读超时 LLM_TIMEOUT, 失败最多重试 LLM_MAX_RETRIES 次。
        # 不配置时 openai SDK 默认 600s/次 × 3 次, 一个卡死的请求会拖约 30 分钟。
        kwargs.setdefault("request_timeout", (10.0, ENV_CONFIG.llm.timeout))
        kwargs.setdefault("max_retries", ENV_CONFIG.llm.max_retries)

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
        rprint(response.content)

    asyncio.run(test_ainvoke())
