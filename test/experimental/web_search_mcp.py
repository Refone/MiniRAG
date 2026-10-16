# -*- coding: utf-8 -*-
# 使用 OpenAI SDK + MCP SDK 调用阿里云百炼联网搜索（WebSearch）MCP 服务
import os
import asyncio
import json

import httpx2
from openai import OpenAI
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession

from common.config.env_config import ENV_CONFIG


async def main():
    # 优先读取 DASHSCOPE_API_KEY，其次回退到 .env 中的 QWEN_API_KEY
    api_key = os.getenv("DASHSCOPE_API_KEY") or ENV_CONFIG.qwen.api_key
    if not api_key:
        print("错误：请设置环境变量 DASHSCOPE_API_KEY")
        return
    mcp_url = "https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp"
    headers = {"Authorization": f"Bearer {api_key}"}
    # 1. 连接 MCP Server，获取可用工具列表
    # 注意：mcp>=2.0 中 streamable_http_client 不再接收 headers 参数，
    # 需通过 httpx2.AsyncClient 传入自定义请求头（认证信息），并解包为 (read, write) 二元组。
    async with httpx2.AsyncClient(headers=headers) as http_client:
        async with streamable_http_client(mcp_url, http_client=http_client) as (
            read,
            write,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                # 转换为 OpenAI function calling 格式
                openai_tools = []
                for tool in tools_result.tools:
                    openai_tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description or "",
                                "parameters": tool.input_schema
                                or {"type": "object", "properties": {}},
                            },
                        }
                    )
                # 2. 调用 DashScope（OpenAI 兼容接口）
                client = OpenAI(
                    api_key=api_key,
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                )
                messages = [{"role": "user", "content": "搜索一下HAK180烫金机"}]
                print("正在联网搜索...")
                print("=" * 50)
                # 3. 多轮工具调用循环
                while True:
                    response = client.chat.completions.create(
                        model="qwen-max",
                        messages=messages,
                        tools=openai_tools or None,
                    )
                    choice = response.choices[0]
                    msg = choice.message
                    if not msg.tool_calls:
                        print(msg.content)
                        break
                    messages.append(msg)
                    for tc in msg.tool_calls:
                        args = json.loads(tc.function.arguments or "{}")
                        result = await session.call_tool(tc.function.name, args)
                        tool_content = ""
                        for block in result.content:
                            if hasattr(block, "text"):
                                tool_content += block.text
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": tool_content,
                            }
                        )


if __name__ == "__main__":
    asyncio.run(main())
