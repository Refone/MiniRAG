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

        return super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        )


if __name__ == "__main__":
    import asyncio
    from common.prompt.prompt_conclude_query import ConcludeQueryResult
    from rich import print as rprint

    async def test_ainvoke():
        # 示例调用
        response = await DeepSeekFlash().ainvoke("你好")
        rprint(response.content)

    async def test_with_structured_output():
        response = (
            await DeepSeekFlash()
            .with_structured_output(ConcludeQueryResult)
            .ainvoke("我想咨询一下 Iphone 17 Pro Max 的售价")
        )
        rprint(response)

    asyncio.run(test_ainvoke())
    asyncio.run(test_with_structured_output())
