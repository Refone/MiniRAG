"""Web 搜索 seam（tier 3）：MCP WebSearch 调用的唯一入口。

图节点只做编排；测试 patch `common.client.search_web` 即可零网络回放结果。
"""

import asyncio
import json

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp_types import CallToolResult

from common.config.app_config import APP_CONFIG
from common.config.env_config import ENV_CONFIG
from common.logging import logger
from common.schema import WebSearchResult


async def _call_mcp_tool(query: str) -> CallToolResult:
    api_key = ENV_CONFIG.dashscope.api_key
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY 未配置")

    url = ENV_CONFIG.dashscope.web_search_mcp_url
    tool_name = ENV_CONFIG.dashscope.web_search_mcp_tool_name
    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx2.AsyncClient(
        headers=headers,
        timeout=APP_CONFIG.mcp_timeout,
    ) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read,
            write,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()

                return await session.call_tool(
                    tool_name,
                    {
                        "query": query,
                        "count": APP_CONFIG.mcp_web_search_count,
                    },
                )


def search_web(query: str) -> list[WebSearchResult]:
    """调用 MCP WebSearch，失败降级为空结果（不阻塞查询主流程）。"""
    try:
        result = asyncio.run(_call_mcp_tool(query))
    except Exception as e:
        logger.warning(f"MCP 调用失败: {e}")
        return []

    if not result:
        return []

    # MCP 返回的是封装为 str 的 json
    result_text: str = result.content[0].text
    data_json: list[WebSearchResult] = json.loads(result_text).get("pages", [])
    return data_json
