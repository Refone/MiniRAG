"""单元测试: src/utils/net_utils.py

被测对象:
    _parse_endpoint  解析 host:port / scheme://host:port / mongodb URI 三种写法
    probe_tcp        TCP 探测: 成功返回 "host:port", 拒绝连接抛 ConnectionError

不依赖任何真实外部服务:
    成功用例在本机 127.0.0.1 起一个临时监听 socket,
    失败用例用「绑定后立即关闭」的临时端口触发 Connection refused。
"""

from __future__ import annotations

import socket
import threading

import pytest

from utils.net_utils import _parse_endpoint, probe_tcp


# --------------------------------------------------------------------------- #
# _parse_endpoint: 三种 endpoint 写法与非法输入
# --------------------------------------------------------------------------- #
def test_parse_host_port():
    assert _parse_endpoint("127.0.0.1:9000") == ("127.0.0.1", 9000)


def test_parse_scheme_with_port():
    assert _parse_endpoint("http://127.0.0.1:19530") == ("127.0.0.1", 19530)


def test_parse_mongodb_uri_with_port():
    assert _parse_endpoint("mongodb://localhost:27017") == ("localhost", 27017)


def test_parse_mongodb_uri_uses_default_port():
    # mongodb URI 不带端口时, 按 scheme 默认端口 27017 补
    assert _parse_endpoint("mongodb://localhost") == ("localhost", 27017)


def test_parse_raises_on_missing_host():
    with pytest.raises(ValueError, match="缺少 host"):
        _parse_endpoint("https:///only-path")


def test_parse_raises_on_missing_port():
    with pytest.raises(ValueError, match="缺少端口"):
        _parse_endpoint("127.0.0.1")


# --------------------------------------------------------------------------- #
# probe_tcp: 真实 TCP 探测
# --------------------------------------------------------------------------- #
def _start_accepting_listener() -> tuple[int, threading.Thread]:
    """在 127.0.0.1 上起一个临时监听 socket, 接受一次连接后关闭。"""
    server = socket.create_server(("127.0.0.1", 0))
    port = server.getsockname()[1]

    def _accept_once():
        conn, _ = server.accept()
        conn.close()
        server.close()

    thread = threading.Thread(target=_accept_once, daemon=True)
    thread.start()
    return port, thread


def test_probe_tcp_succeeds_on_open_port():
    port, accept_thread = _start_accepting_listener()

    result = probe_tcp(f"127.0.0.1:{port}", timeout=2)

    assert result == f"127.0.0.1:{port}"
    accept_thread.join(timeout=2)
    assert not accept_thread.is_alive()


def test_probe_tcp_raises_when_connection_refused():
    # 绑定后立即关闭的端口大概率不会被其它进程占用, 连接会遭拒绝
    server = socket.create_server(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.close()

    with pytest.raises(ConnectionError, match=f"无法连接 127.0.0.1:{port}"):
        probe_tcp(f"127.0.0.1:{port}", timeout=2)


def test_probe_tcp_raises_value_error_before_connecting():
    with pytest.raises(ValueError, match="缺少端口"):
        probe_tcp("127.0.0.1", timeout=2)
