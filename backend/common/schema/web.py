from typing import TypedDict


class WebSearchResult(TypedDict):
    """联网搜索单条结果（MCP WebSearch 返回的 pages 条目）。

    示例:
    {
        "snippet": "如何使用电阻表测量电阻? 1. 断开...",
        "hostname": "百度教育",
        "hostlogo": "https://...png",
        "title": "如何使用电阻表测量电阻?",
        "url": "https://...",
    }
    """

    snippet: str
    hostname: str
    hostlogo: str
    title: str
    url: str
