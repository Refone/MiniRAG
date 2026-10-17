import asyncio
import json
from typing import TypedDict

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp_types import CallToolResult

from common.config.app_config import APP_CONFIG
from common.config.env_config import ENV_CONFIG
from utils.node_utils import trace_node
from utils.logging_utils import logger
from processor.query_processor.state import QueryGraphState


class WebSearchResult(TypedDict):
    """
    {
        'snippet': '如何使用电阻表测量电阻? 1. 断开...',
        'hostname': '百度教育',
        'hostlogo': 'https://mbs1.bdstatic.com/searchbox/mappconsole/image/20230906/3096e08a-869d-46a7-8d30-5e32adb66fdc.png',
        'title': '如何使用电阻表测量电阻?',
        'url': 'https://easylearn.baidu.com/edu-page/tiangong/questiondetail?id=1832280139494591726&fr=search'
    }
    """

    snippet: str  # 搜索结果的摘要信息
    hostname: str  # 搜索结果的主机名
    hostlogo: str  # 搜索结果的主机图标 URL
    title: str  # 搜索结果的标题
    url: str  # 搜索结果的链接


def step_1_validate_and_get_data(state: QueryGraphState) -> str:
    rewritten_query = state.get("rewritten_query", "")
    if not rewritten_query:
        raise ValueError("state['rewritten_query'] is empty")
    return rewritten_query


async def _call_mcp_tool(rewritten_query: str):
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

                result: CallToolResult = await session.call_tool(
                    tool_name,
                    {
                        "query": rewritten_query,
                        "count": APP_CONFIG.mcp_web_search_count,
                    },
                )

    return result


def step_2_call_mcp_tool(rewritten_query: str) -> list[WebSearchResult]:
    try:
        result = asyncio.run(_call_mcp_tool(rewritten_query))
    except Exception as e:
        logger.warning(f"MCP 调用失败: {e}")
        result = None

    if not result:
        return []

    # MCP 返回的是封装为 str 的 json
    result_text: str = result.content[0].text
    data_json: list[WebSearchResult] = json.loads(result_text).get("pages", [])

    return data_json


@trace_node(desc="互联网搜索", need_push=True)
def node_search_internet(state: QueryGraphState) -> QueryGraphState:

    rewritten_query = step_1_validate_and_get_data(state)
    logger.info(f"重写后的查询: {rewritten_query}")

    search_results = step_2_call_mcp_tool(rewritten_query)
    logger.info(f"搜索结果: {search_results}")

    return {"internet_matches": search_results}


if __name__ == "__main__":
    from rich import print as rprint
    from processor.query_processor.state import load_state, save_state
    from utils.path_utils import PROJECT_ROOT

    prev_state = load_state(PROJECT_ROOT / "output/tmp/query_01_intent_recognize.json")
    next_state = node_search_internet(prev_state)
    rprint(next_state)

    new_state_json = str(PROJECT_ROOT / "output/tmp/query_04_search_internet.json")

    save_state(next_state, new_state_json)
    logger.info(f"互联网搜索处理完成")
    logger.info(f"状态保存路径: {new_state_json}")
