"""网络连通性探测工具。

供后端启动自检 (api/startup_checks.py) 与各数据服务 client 的 check_health 使用:
先用带超时的 TCP 探测确认服务可达, 再发起真实协议请求 (ping / list_buckets 等),
避免服务未启动时被 SDK 默认的长超时 (如 MinIO 5 分钟) 拖住启动流程。
"""

from __future__ import annotations

import socket
from urllib.parse import urlparse

# scheme -> 未显式给出端口时的默认端口
_DEFAULT_PORTS = {
    "mongodb": 27017,
    "mongodb+srv": 27017,
    "http": 80,
    "https": 443,
}


def _parse_endpoint(endpoint: str) -> tuple[str, int]:
    """把 endpoint 解析为 (host, port)。

    支持三种写法: "127.0.0.1:9000" / "http://127.0.0.1:19530" /
    "mongodb://localhost" (无端口时按 scheme 默认端口补)。
    """
    if "://" not in endpoint:
        endpoint = f"//{endpoint}"

    parsed = urlparse(endpoint)
    host = parsed.hostname
    port = parsed.port or _DEFAULT_PORTS.get(parsed.scheme)
    if not host:
        raise ValueError(f"无法解析 endpoint, 缺少 host: {endpoint!r}")
    if not port:
        raise ValueError(f"无法解析 endpoint, 缺少端口: {endpoint!r}")
    return host, port


def probe_tcp(endpoint: str, timeout: float = 5.0) -> str:
    """TCP 探测 endpoint 是否可达, 返回规范化后的 "host:port"。

    endpoint 支持三种写法:
        "127.0.0.1:9000"               host:port
        "http://127.0.0.1:19530"       带 scheme 与端口
        "mongodb://localhost:27017"    带 scheme (无端口时按默认端口补)

    Args:
        endpoint: 服务地址
        timeout: 连接超时 (秒)
    Returns:
        规范化的 "host:port" 字符串
    Raises:
        ValueError: endpoint 无法解析 (缺少 host, 或缺少端口且 scheme 无默认端口)
        ConnectionError: TCP 连接失败 (服务未启动 / 地址错误 / 网络不通)
    """
    host, port = _parse_endpoint(endpoint)

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return f"{host}:{port}"
    except OSError as exc:
        raise ConnectionError(f"无法连接 {host}:{port}: {exc}") from exc
