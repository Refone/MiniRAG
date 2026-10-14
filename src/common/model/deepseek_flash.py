from langchain_deepseek import ChatDeepSeek

from common.model.rate_limiter import SlidingWindowRateLimiter
from common.config.env_config import ENV_CONFIG


class DeepSeekFlash(ChatDeepSeek):
    """DeepSeek 模型封装：原生限速 + 关闭思考模式。

    继承自 ChatDeepSeek（即 BaseChatModel），因此 bind_tools / with_structured_output /
    回调 / 批处理 / 流式等全部原生可用；限速由 LangChain 在每条调用路径上自动执行。
    """

    def __init__(self, **kwargs):
        kwargs.setdefault(
            "rate_limiter", SlidingWindowRateLimiter(ENV_CONFIG.llm.rpm)
        )
        kwargs.setdefault("extra_body", {"thinking": {"type": "disabled"}})
        super().__init__(
            model=ENV_CONFIG.llm.model_name,
            api_key=ENV_CONFIG.llm.api_key,
            base_url=ENV_CONFIG.llm.base_url,
            **kwargs,
        )


if __name__ == "__main__":
    import asyncio

    async def main():
        # 示例调用
        response = await DeepSeekFlash().ainvoke("你好")
        print(response.content)

    asyncio.run(main())
