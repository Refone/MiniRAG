#!/usr/bin/env python3
"""MiniRAG 一键部署脚本。

命令:
    python minirag.py env_check     # 检查部署环境
    python minirag.py env_prepare   # 安装三方包并拉取 Docker 镜像
    python minirag.py deploy        # 构建前后端镜像并按顺序拉起容器
    python minirag.py reset         # 清空持久化存储并重置数据库

支持 Linux / macOS / Windows, 仅依赖 Python 标准库与 Docker Compose v2。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import ctypes
import errno
import json
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parent
DOCKER_DIR = ROOT / "docker"
COMPOSE_INFRA = DOCKER_DIR / "compose.infra.yaml"
COMPOSE_BACKEND = DOCKER_DIR / "compose.backend.yaml"
COMPOSE_FRONTEND = DOCKER_DIR / "compose.frontend.yaml"
COMPOSE_FILES = (COMPOSE_INFRA, COMPOSE_BACKEND, COMPOSE_FRONTEND)
BACKEND_DOCKERFILE = DOCKER_DIR / "backend.Dockerfile"
FRONTEND_DOCKERFILE = DOCKER_DIR / "frontend.Dockerfile"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
WEB_DIR = ROOT / "frontend"
WEB_ENV_FILE = WEB_DIR / ".env"
WEB_ENV_EXAMPLE = WEB_DIR / ".env.example"
VAR_DIR = ROOT / "var"
VAR_UPLOADS = VAR_DIR / "uploads"
VAR_IMPORT = VAR_DIR / "import"
VAR_TMP = VAR_DIR / "tmp"

MIN_PYTHON = (3, 12)
DEFAULT_WAIT_TIMEOUT = 600
DEFAULT_HTTP_TIMEOUT = 60
UV_LOCK = ROOT / "uv.lock"

DEFAULT_PYPI_INDEX = "https://pypi.org/simple"
# 国内 PyPI 镜像按顺序尝试; 单一镜像对个别包可能 403 或暂时缺包
CN_PYPI_MIRRORS = (
    "https://mirrors.aliyun.com/pypi/simple",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.cloud.tencent.com/pypi/simple",
    "https://repo.huaweicloud.com/repository/pypi/simple",
)
CN_PYPI_INDEX = CN_PYPI_MIRRORS[0]
DEFAULT_NPM_REGISTRY = "https://registry.npmjs.org"
CN_NPM_REGISTRY = "https://registry.npmmirror.com"

# (key, 展示名, 官方地址, 国内镜像地址); 只用于连通性探测与建议
NETWORK_TARGETS = (
    ("pypi", "PyPI", "https://pypi.org/simple/", f"{CN_PYPI_INDEX}/"),
    ("npm", "npm", "https://registry.npmjs.org/", f"{CN_NPM_REGISTRY}/"),
    (
        "dockerhub",
        "Docker Hub",
        "https://registry-1.docker.io/v2/",
        "https://docker.m.daocloud.io/v2/",
    ),
    ("ghcr", "GHCR", "https://ghcr.io/v2/", "https://ghcr.nju.edu.cn/v2/"),
    ("quay", "Quay", "https://quay.io/v2/", None),
)

# reset 只清理这些容器数据目录, 避免误删未来新增的配置类 bind mount
DATA_MOUNT_TARGETS = {"/etcd", "/var/lib/milvus", "/minio_data"}

REQUIRED_PATHS = (
    ROOT / "pyproject.toml",
    ROOT / "uv.lock",
    ROOT / "README.md",
    ENV_EXAMPLE,
    *COMPOSE_FILES,
    BACKEND_DOCKERFILE,
    FRONTEND_DOCKERFILE,
    WEB_DIR / "package.json",
    WEB_DIR / "nginx.conf",
    ROOT / "backend" / "api" / "main.py",
)

# (宿主机端口, 用途, 占用它的 compose 容器名)
HOST_PORTS = (
    (8080, "前端 Web", "mini-rag-frontend"),
    (8000, "后端 API", "mini-rag-backend"),
    (19530, "Milvus", "milvus"),
    (9091, "Milvus 健康检查", "milvus"),
    (9000, "MinIO API", "milvus-minio"),
    (9001, "MinIO 控制台", "milvus-minio"),
    (7001, "Attu", "attu"),
    (27017, "MongoDB", "mongodb"),
)

_DRY_RUN = False
_COLOR = False
_COMPOSE_CONFIG_CACHE: dict[Path, dict] = {}
_COMPOSE_WAIT_CAPABILITY: Optional[tuple[bool, bool]] = None
# 本机健康检查不走 HTTP(S)_PROXY, 避免代理环境下 localhost 探测被转发
_LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class _Color:
    RESET = "\033[0m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _configure_console() -> None:
    global _COLOR
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    _COLOR = _supports_color()


def _paint(text: str, color: str) -> str:
    return f"{color}{text}{_Color.RESET}" if _COLOR else text


def _print(message: str = "") -> None:
    print(message, flush=True)


def info(message: str) -> None:
    _print(f"{_paint('[info]', _Color.CYAN)} {message}")


def ok(message: str) -> None:
    _print(f"{_paint('[ ok ]', _Color.GREEN)} {message}")


def warn(message: str, hint: str = "") -> None:
    _print(f"{_paint('[warn]', _Color.YELLOW)} {message}")
    if hint:
        _print(f"       {_paint('->', _Color.DIM)} {hint}")


def fail(message: str, hint: str = "") -> None:
    _print(f"{_paint('[fail]', _Color.RED)} {message}")
    if hint:
        _print(f"       {_paint('->', _Color.DIM)} {hint}")


def detail(message: str) -> None:
    _print(f"    {message}")


def step(title: str) -> None:
    _print(f"\n==> {title}")


# --------------------------------------------------------------------------- #
# 系统识别
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SystemInfo:
    key: str
    name: str
    arch: str
    version: str = ""
    wsl: bool = False


def _normalize_arch(machine: str) -> str:
    arch = (machine or "").lower()
    if arch in ("x86_64", "amd64", "x64"):
        return "x86_64"
    if arch in ("arm64", "aarch64"):
        return "arm64"
    return arch or "unknown"


def _read_linux_distro() -> str:
    path = Path("/etc/os-release")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def _is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        version = Path("/proc/version").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "microsoft" in version.lower() or "wsl" in version.lower()


def _windows_name() -> str:
    version = platform.version()
    parts = version.split(".")
    try:
        build = int(parts[2])
    except (IndexError, ValueError):
        build = 0
    if build >= 22000:
        return "Windows 11"
    if build >= 10240:
        return "Windows 10"
    return "Windows"


def detect_system() -> SystemInfo:
    system = platform.system()
    arch = _normalize_arch(platform.machine())

    if system == "Darwin":
        version = platform.mac_ver()[0] or platform.release()
        return SystemInfo("macos", f"macOS {version}".strip(), arch, version)

    if system == "Windows":
        return SystemInfo("windows", _windows_name(), arch, platform.version())

    if system == "Linux":
        distro = _read_linux_distro()
        name = f"Linux ({distro})" if distro else "Linux"
        wsl = _is_wsl()
        if wsl:
            name = f"{name} [WSL]"
        return SystemInfo("linux", name, arch, platform.release(), wsl=wsl)

    return SystemInfo("unknown", system or "Unknown", arch, platform.release())


def _print_header(title: str, system: SystemInfo) -> None:
    _print("=" * 68)
    _print(f"MiniRAG {title}")
    _print(f"系统: {system.name} / {system.arch}")
    _print(f"项目: {ROOT}")
    _print("=" * 68)


# --------------------------------------------------------------------------- #
# 命令执行
# --------------------------------------------------------------------------- #
class CommandError(RuntimeError):
    def __init__(
        self, cmd: Iterable[str], returncode: int = 1, message: str = ""
    ) -> None:
        self.cmd = list(cmd)
        self.returncode = returncode
        self.message = message
        super().__init__(self.__str__())

    def __str__(self) -> str:
        if self.cmd:
            text = f"命令失败 (exit={self.returncode}): {_display_cmd(self.cmd)}"
        else:
            text = f"操作失败 (exit={self.returncode})"
        if self.message:
            text = f"{text}\n  {self.message}"
        return text


def _display_cmd(cmd: Iterable[str]) -> str:
    parts = [str(part) for part in cmd]
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return " ".join(shlex.quote(part) for part in parts)


def _docker_bin() -> str:
    return shutil.which("docker") or "docker"


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def run_capture(
    cmd: Iterable[str],
    cwd: Path = ROOT,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    parts = [str(part) for part in cmd]
    try:
        return subprocess.run(
            parts,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise CommandError(parts, 127, f"找不到命令: {parts[0]} ({exc})") from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandError(parts, 124, f"命令超时 ({timeout}s)") from exc


def run_stream(
    cmd: Iterable[str],
    cwd: Path = ROOT,
    check: bool = True,
    env: Optional[dict[str, str]] = None,
) -> int:
    parts = [str(part) for part in cmd]
    _print(f"{_paint('$', _Color.DIM)} {_display_cmd(parts)}")
    if _DRY_RUN:
        return 0
    try:
        completed = subprocess.run(parts, cwd=str(cwd), env=env)
    except FileNotFoundError as exc:
        raise CommandError(parts, 127, f"找不到命令: {parts[0]} ({exc})") from exc
    if check and completed.returncode != 0:
        raise CommandError(parts, completed.returncode)
    return completed.returncode


def run_with_retry(
    cmd: Iterable[str],
    cwd: Path = ROOT,
    attempts: int = 2,
) -> int:
    last: Optional[CommandError] = None
    for attempt in range(1, attempts + 1):
        try:
            return run_stream(cmd, cwd=cwd)
        except CommandError as exc:
            last = exc
            if attempt < attempts:
                warn(f"命令失败，3 秒后重试 ({attempt}/{attempts})")
                time.sleep(3)
    assert last is not None
    raise last


# --------------------------------------------------------------------------- #
# 网络探测与镜像源
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    seconds: float
    note: str = ""


_NETWORK_CACHE: Optional[dict[str, ProbeResult]] = None


def _probe_url(url: str, timeout: float = 3.0) -> ProbeResult:
    """探测 URL 是否可达; 401/403/405 也算可达 (仅关心连通性与耗时)。"""
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "minirag-deploy/1.0"},
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(1)
            return ProbeResult(
                True, time.monotonic() - start, f"HTTP {response.status}"
            )
    except urllib.error.HTTPError as exc:
        # 401/403/405 说明服务可达; 5xx 视为镜像/服务异常
        return ProbeResult(exc.code < 500, time.monotonic() - start, f"HTTP {exc.code}")
    except Exception as exc:
        return ProbeResult(False, time.monotonic() - start, type(exc).__name__)


def _probe_network() -> dict[str, ProbeResult]:
    global _NETWORK_CACHE
    if _NETWORK_CACHE is not None:
        return _NETWORK_CACHE

    urls: dict[str, str] = {}
    for key, _label, direct, mirror in NETWORK_TARGETS:
        urls[f"{key}:direct"] = direct
        if mirror:
            urls[f"{key}:mirror"] = mirror

    results: dict[str, ProbeResult] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(urls))) as pool:
        futures = {name: pool.submit(_probe_url, url) for name, url in urls.items()}
        for name, future in futures.items():
            try:
                results[name] = future.result()
            except Exception:
                results[name] = ProbeResult(False, 0.0, "probe failed")
    _NETWORK_CACHE = results
    return results


def _probe_of(results: dict[str, ProbeResult], key: str) -> ProbeResult:
    return results.get(key, ProbeResult(False, 0.0, "not probed"))


def _latency(probe: ProbeResult) -> str:
    return f"{probe.seconds:.1f}s" if probe.ok else "不可达"


def _prefer_mirror(direct: ProbeResult, mirror: ProbeResult) -> bool:
    if not mirror.ok:
        return False
    if not direct.ok:
        return True
    return direct.seconds >= 2.0 and mirror.seconds <= direct.seconds * 0.6


@dataclass(frozen=True)
class MirrorConfig:
    pypi_index: Optional[str] = None
    npm_registry: Optional[str] = None
    reason: str = ""


def resolve_mirror_config(args: argparse.Namespace) -> MirrorConfig:
    """根据 --mirror / --pypi-index / --npm-registry 决定软件包索引。"""
    override_pypi = getattr(args, "pypi_index", None)
    override_npm = getattr(args, "npm_registry", None)

    mode = getattr(args, "mirror", "auto")
    if mode == "cn":
        pypi_index: Optional[str] = CN_PYPI_INDEX
        npm_registry: Optional[str] = CN_NPM_REGISTRY
        reason = "国内镜像预设 (--mirror cn)"
    elif mode == "global":
        pypi_index = None
        npm_registry = None
        reason = "官方源预设 (--mirror global)"
    elif override_pypi is not None and override_npm is not None:
        pypi_index = override_pypi
        npm_registry = override_npm
        reason = "命令行手动指定 PyPI / npm"
    else:
        results = _probe_network()
        pypi_direct = _probe_of(results, "pypi:direct")
        pypi_mirror = _probe_of(results, "pypi:mirror")
        npm_direct = _probe_of(results, "npm:direct")
        npm_mirror = _probe_of(results, "npm:mirror")

        use_pypi = _prefer_mirror(pypi_direct, pypi_mirror)
        # 主镜像探测失败时也切到国内预设: 构建阶段还会按镜像列表继续回退
        if not use_pypi and (not pypi_direct.ok or pypi_direct.seconds >= 2.0):
            use_pypi = True
        use_npm = _prefer_mirror(npm_direct, npm_mirror)
        reason = (
            "自动探测: "
            f"PyPI 直连 {_latency(pypi_direct)} / 阿里云 {_latency(pypi_mirror)}; "
            f"npm 直连 {_latency(npm_direct)} / npmmirror {_latency(npm_mirror)}"
        )
        if use_pypi and not pypi_mirror.ok:
            reason += "（阿里云不可达，构建时继续尝试其他国内镜像）"
        pypi_index = CN_PYPI_INDEX if use_pypi else None
        npm_registry = CN_NPM_REGISTRY if use_npm else None

    if override_pypi is not None:
        pypi_index = override_pypi
        reason += "；PyPI 手动指定"
    if override_npm is not None:
        npm_registry = override_npm
        reason += "；npm 手动指定"
    return MirrorConfig(pypi_index, npm_registry, reason)


def announce_mirrors(config: MirrorConfig) -> None:
    if config.pypi_index:
        info(f"PyPI 索引: {config.pypi_index}")
    if config.npm_registry:
        info(f"npm registry: {config.npm_registry}")
    if not config.pypi_index and not config.npm_registry:
        info("软件包索引: 使用官方源直连")
    if config.reason:
        detail(f"策略: {config.reason}")


# --------------------------------------------------------------------------- #
# 检查项
# --------------------------------------------------------------------------- #
@dataclass
class CheckItem:
    name: str
    status: str
    detail: str = ""
    hint: str = ""


class Checker:
    def __init__(self) -> None:
        self.items: list[CheckItem] = []

    def _add(self, name: str, status: str, detail: str, hint: str) -> None:
        self.items.append(CheckItem(name, status, detail, hint))
        marker = {
            "ok": _paint("[ ok ]", _Color.GREEN),
            "warn": _paint("[warn]", _Color.YELLOW),
            "fail": _paint("[fail]", _Color.RED),
            "skip": _paint("[skip]", _Color.DIM),
        }[status]
        line = f"{marker} {name}"
        if detail:
            line = f"{line}: {detail}"
        _print(line)
        if hint and status in ("warn", "fail", "skip"):
            _print(f"       {_paint('->', _Color.DIM)} {hint}")

    def ok(self, name: str, detail: str = "") -> None:
        self._add(name, "ok", detail, "")

    def warn(self, name: str, detail: str = "", hint: str = "") -> None:
        self._add(name, "warn", detail, hint)

    def fail(self, name: str, detail: str = "", hint: str = "") -> None:
        self._add(name, "fail", detail, hint)

    def skip(self, name: str, detail: str = "", hint: str = "") -> None:
        self._add(name, "skip", detail, hint)

    @property
    def failures(self) -> list[CheckItem]:
        return [item for item in self.items if item.status == "fail"]

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.items if item.status == "warn")

    def summary(self) -> int:
        counts = {
            status: sum(1 for item in self.items if item.status == status)
            for status in ("ok", "warn", "fail", "skip")
        }
        _print("-" * 68)
        _print(
            "检查结果: "
            f"{counts['ok']} 通过, {counts['warn']} 警告, "
            f"{counts['fail']} 失败, {counts['skip']} 跳过"
        )
        if counts["fail"]:
            _print("存在失败项，已停止。")
            return 1
        if counts["warn"]:
            _print("存在警告，请按提示处理后再部署。")
        else:
            _print("全部通过。")
        return 0


def check_system(checker: Checker, system: SystemInfo) -> None:
    if system.key in ("linux", "macos", "windows"):
        checker.ok("操作系统", f"{system.name} / {system.arch}")
    else:
        checker.fail("操作系统", system.name, "仅支持 Linux / macOS / Windows")


def check_python(checker: Checker) -> None:
    current = ".".join(str(part) for part in sys.version_info[:3])
    required = f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
    if sys.version_info >= MIN_PYTHON:
        checker.ok("Python", f"{current} (>= {required})")
    else:
        checker.warn(
            "Python",
            f"{current} < {required}",
            "Docker 部署与 uv 自动下载的 3.12 环境不受影响；"
            "本地直接运行后端需升级到 3.12+",
        )


def check_project_files(checker: Checker) -> None:
    missing = [
        str(path.relative_to(ROOT)) for path in REQUIRED_PATHS if not path.exists()
    ]
    if missing:
        checker.fail(
            "项目文件",
            "缺少: " + ", ".join(missing),
            "确认在仓库根目录执行本脚本",
        )
    else:
        checker.ok("项目文件", f"{len(REQUIRED_PATHS)} 个关键文件齐全")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            hash_pos = value.find(" #")
            if hash_pos >= 0:
                value = value[:hash_pos].rstrip()
        values[key] = value
    return values


def is_placeholder(value: str) -> bool:
    if not value:
        return True
    lowered = value.lower()
    if set(value) <= {"*"}:
        return True
    return (
        "****" in value
        or "your_" in lowered
        or lowered in ("changeme", "change-me", "your-key", "your_key")
    )


def check_env_file(
    checker: Checker,
    required: bool = True,
    check_keys: bool = True,
) -> None:
    if not ENV_FILE.is_file():
        message = "文件不存在"
        hint = "运行 python minirag.py env_prepare 生成 .env"
        if required:
            checker.fail("环境配置 .env", message, hint)
        else:
            checker.warn("环境配置 .env", message, hint)
        return

    checker.ok("环境配置 .env", ".env 已存在")
    if not check_keys:
        return

    values = parse_env_file(ENV_FILE)
    for key, feature in (
        ("DASHSCOPE_API_KEY", "LLM / VLM / Embedding / Rerank"),
        ("MINERU_API_KEY", "PDF 解析"),
    ):
        value = values.get(key, "")
        if is_placeholder(value):
            checker.warn(
                f"配置项 {key}",
                "未配置或仍是占位值",
                f"{feature} 将不可用，请在 .env 中填写",
            )
        else:
            checker.ok(f"配置项 {key}", f"已配置 ({len(value)} 字符)")

    if is_placeholder(values.get("MINIO_ACCESS_KEY", "")) or is_placeholder(
        values.get("MINIO_SECRET_KEY", "")
    ):
        checker.warn(
            "MinIO 凭据",
            ".env 中仍是占位值",
            "Docker 部署已由 compose 覆盖为 minioadmin；本地开发需改为 minioadmin",
        )


def _docker_install_hint(system: SystemInfo) -> str:
    if system.key == "macos":
        return "安装 Docker Desktop: https://docs.docker.com/desktop/setup/install/mac-install/"
    if system.key == "windows":
        return (
            "安装 Docker Desktop (WSL2 后端): "
            "https://docs.docker.com/desktop/setup/install/windows-install/"
        )
    return "安装 Docker Engine + Compose 插件: https://docs.docker.com/engine/install/"


def _daemon_hint(system: SystemInfo) -> str:
    if system.key == "macos":
        return "启动 Docker Desktop，等待引擎就绪后重试"
    if system.key == "windows":
        return "启动 Docker Desktop（WSL2 后端），并确认使用 Linux containers"
    if system.wsl:
        return (
            "启动 Docker Desktop 并开启 WSL integration，或启动 WSL 内的 Docker Engine"
        )
    return "启动 Docker: sudo systemctl start docker；权限不足时把用户加入 docker 组"


def check_docker_cli(checker: Checker, system: SystemInfo) -> bool:
    docker = shutil.which("docker")
    if not docker:
        checker.fail("Docker CLI", "未找到 docker 命令", _docker_install_hint(system))
        return False
    result = run_capture([docker, "--version"], timeout=15)
    if result.returncode != 0:
        checker.fail(
            "Docker CLI",
            _first_line(result.stderr) or "执行 docker --version 失败",
            _docker_install_hint(system),
        )
        return False
    checker.ok("Docker CLI", result.stdout.strip() or docker)
    return True


def check_docker_daemon(checker: Checker, system: SystemInfo) -> bool:
    result = run_capture(
        [
            _docker_bin(),
            "info",
            "--format",
            "{{.ServerVersion}}|{{.OSType}}|{{.Architecture}}",
        ],
        timeout=30,
    )
    if result.returncode != 0:
        checker.fail(
            "Docker 守护进程",
            _first_line(result.stderr) or "无法连接 Docker 守护进程",
            _daemon_hint(system),
        )
        return False
    parts = result.stdout.strip().split("|")
    version = parts[0] if parts else "?"
    os_type = parts[1] if len(parts) > 1 else "?"
    arch = parts[2] if len(parts) > 2 else "?"
    if os_type.lower() != "linux":
        checker.fail(
            "Docker 容器模式",
            f"当前为 {os_type} 容器",
            "切换 Docker Desktop 到 Linux containers 后重试",
        )
        return False
    checker.ok("Docker 守护进程", f"{version} ({os_type}/{arch})")
    return True


def check_compose(checker: Checker) -> bool:
    result = run_capture([_docker_bin(), "compose", "version", "--short"], timeout=20)
    if result.returncode != 0:
        result = run_capture([_docker_bin(), "compose", "version"], timeout=20)
    if result.returncode != 0:
        checker.fail(
            "Docker Compose",
            _first_line(result.stderr) or "无法执行 docker compose",
            "安装 Docker Compose v2 插件",
        )
        return False
    version = _first_line(result.stdout) or "v2"
    checker.ok("Docker Compose", version)
    return True


def check_compose_config(checker: Checker) -> None:
    failures = []
    for compose_file in COMPOSE_FILES:
        result = run_capture(compose(compose_file, "config", "--quiet"), timeout=30)
        if result.returncode != 0:
            message = _first_line(result.stderr or result.stdout) or "配置无效"
            failures.append(f"{compose_file.name}: {message}")
    if failures:
        checker.fail(
            "Compose 配置",
            "; ".join(failures),
            "修正 YAML 或 .env 后重试",
        )
    else:
        checker.ok("Compose 配置", f"{len(COMPOSE_FILES)} 个文件有效")


def _docker_registry_mirrors() -> list[str]:
    try:
        result = run_capture(
            [
                _docker_bin(),
                "info",
                "--format",
                "{{json .RegistryConfig.Mirrors}}",
            ],
            timeout=20,
        )
    except CommandError:
        return []
    if result.returncode != 0:
        return []
    try:
        mirrors = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(mirrors, list):
        return []
    return [str(mirror) for mirror in mirrors if mirror]


def check_network(checker: Checker) -> None:
    results = _probe_network()
    pypi_direct = _probe_of(results, "pypi:direct")
    pypi_mirror = _probe_of(results, "pypi:mirror")
    npm_direct = _probe_of(results, "npm:direct")
    npm_mirror = _probe_of(results, "npm:mirror")
    docker_direct = _probe_of(results, "dockerhub:direct")
    docker_mirror = _probe_of(results, "dockerhub:mirror")
    quay_direct = _probe_of(results, "quay:direct")
    ghcr_direct = _probe_of(results, "ghcr:direct")

    summary = " / ".join(
        (
            f"PyPI {_latency(pypi_direct)}",
            f"npm {_latency(npm_direct)}",
            f"Docker Hub {_latency(docker_direct)}",
            f"Quay {_latency(quay_direct)}",
            f"GHCR {_latency(ghcr_direct)}",
        )
    )
    if (
        pypi_direct.ok
        and npm_direct.ok
        and pypi_direct.seconds < 3.0
        and npm_direct.seconds < 3.0
    ):
        checker.ok("网络直连", summary)
    else:
        checker.warn(
            "网络直连",
            summary,
            "国内网络建议使用 --mirror cn，或为 Docker / shell 配置代理",
        )

    if _prefer_mirror(pypi_direct, pypi_mirror) or _prefer_mirror(
        npm_direct, npm_mirror
    ):
        checker.warn(
            "国内镜像",
            f"PyPI 阿里云 {_latency(pypi_mirror)} / npm npmmirror {_latency(npm_mirror)}",
            "使用 --mirror cn 可加速 uv / npm 依赖下载",
        )

    mirror_list = _docker_registry_mirrors()
    if not docker_direct.ok:
        if mirror_list:
            checker.ok(
                "Docker Hub",
                "直连不可达，但 daemon 已配置 mirror: " + ", ".join(mirror_list),
            )
        elif docker_mirror.ok:
            checker.warn(
                "Docker Hub",
                f"直连不可达；DaoCloud 镜像 {_latency(docker_mirror)}",
                "配置 /etc/docker/daemon.json 的 registry-mirrors 后重启 Docker"
                "（仅对 Docker Hub 生效）",
            )
        else:
            checker.warn(
                "Docker Hub",
                "直连不可达，且未探测到可用镜像",
                "配置 registry-mirrors，或提前导入离线镜像",
            )
    elif docker_direct.seconds >= 4.0 and not mirror_list:
        checker.warn(
            "Docker Hub",
            f"直连较慢 ({_latency(docker_direct)})",
            "可配置 registry-mirrors 加速基础镜像拉取",
        )

    if not quay_direct.ok:
        checker.warn(
            "Quay",
            "直连不可达（etcd / MinIO 镜像）",
            "配置可达的 quay 代理，或提前导入离线镜像",
        )
    if not ghcr_direct.ok:
        checker.warn(
            "GHCR",
            "直连不可达（uv 构建镜像）",
            "可通过 UV_IMAGE 换成镜像站地址，或提前导入离线镜像",
        )


def _tool_version(cmd: Iterable[str], timeout: int = 10) -> str:
    try:
        result = run_capture(cmd, timeout=timeout)
    except CommandError:
        return ""
    return _first_line(result.stdout)


def _uv_install_hint(system: SystemInfo) -> str:
    if system.key == "windows":
        return (
            '安装: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"'
            "，或运行 env_prepare --install-tools"
        )
    return (
        "安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
        "，或运行 env_prepare --install-tools"
    )


def check_toolchains(checker: Checker, system: SystemInfo) -> None:
    uv = shutil.which("uv")
    if uv:
        checker.ok("uv", _tool_version([uv, "--version"]) or uv)
    else:
        checker.warn("uv", "未安装", _uv_install_hint(system))

    node = shutil.which("node")
    npm = shutil.which("npm")
    if node and npm:
        node_version = _tool_version([node, "--version"]) or "?"
        npm_version = _tool_version([npm, "--version"]) or "?"
        checker.ok("Node.js / npm", f"{node_version} / {npm_version}")
    elif node or npm:
        checker.warn(
            "Node.js / npm",
            "只检测到其中一个",
            "安装 Node.js 20+（含 npm）",
        )
    else:
        checker.warn(
            "Node.js / npm",
            "未安装",
            "仅本地前端开发需要；Docker 构建不需要",
        )


def _venv_python() -> Path:
    if os.name == "nt":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def check_local_deps(checker: Checker) -> None:
    venv_python = _venv_python()
    if venv_python.exists():
        checker.ok("Python 依赖", f"{venv_python.relative_to(ROOT)} 已存在")
    else:
        checker.warn(
            "Python 依赖",
            ".venv 不存在",
            "运行 env_prepare 安装（Docker 部署不需要）",
        )

    node_modules = WEB_DIR / "node_modules"
    if node_modules.is_dir():
        checker.ok("前端依赖", "frontend/node_modules 已存在")
    else:
        checker.warn(
            "前端依赖",
            "frontend/node_modules 不存在",
            "运行 env_prepare 安装（Docker 构建不需要）",
        )


def check_disk(checker: Checker) -> None:
    try:
        usage = shutil.disk_usage(str(ROOT))
    except OSError as exc:
        checker.warn("磁盘空间", f"无法读取: {exc}")
        return
    free_gib = usage.free / (1024**3)
    if free_gib < 3:
        checker.fail(
            "磁盘空间",
            f"仅剩 {free_gib:.1f} GiB",
            "Docker 镜像与数据卷至少需要约 10 GiB",
        )
    elif free_gib < 10:
        checker.warn(
            "磁盘空间",
            f"仅剩 {free_gib:.1f} GiB",
            "建议预留 10 GiB 以上给镜像与数据卷",
        )
    else:
        checker.ok("磁盘空间", f"{free_gib:.1f} GiB 可用")


# --------------------------------------------------------------------------- #
# 端口检查
# --------------------------------------------------------------------------- #
def _port_in_use(port: int) -> bool:
    probes = (
        (socket.AF_INET, "0.0.0.0"),
        (socket.AF_INET, "127.0.0.1"),
        (socket.AF_INET6, "::"),
        (socket.AF_INET6, "::1"),
    )
    for family, address in probes:
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
        except OSError:
            continue
        try:
            sock.settimeout(0.2)
            sock.bind((address, port))
        except OSError as exc:
            code = getattr(exc, "winerror", None) or exc.errno
            if code == errno.EADDRINUSE or code == 10048:
                return True
        finally:
            sock.close()
    return False


def _docker_port_owners() -> dict[int, set[str]]:
    owners: dict[int, set[str]] = {}
    try:
        result = run_capture(
            [_docker_bin(), "ps", "--format", "{{.Names}}\t{{.Ports}}"],
            timeout=20,
        )
    except CommandError:
        return owners
    if result.returncode != 0:
        return owners
    pattern = re.compile(r"(?:^|[,\s])(?:\[[^\]]+\]|[\d.]+):(\d+)(?:-(\d+))?->")
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        name, ports = line.split("\t", 1)
        for match in pattern.finditer(ports):
            start = int(match.group(1))
            end = int(match.group(2) or start)
            for port in range(start, end + 1):
                owners.setdefault(port, set()).add(name)
    return owners


def _minirag_health_on(port: int) -> bool:
    """判断本机端口是否已有 MiniRAG 服务 (便于给出更精确的端口冲突提示)。"""
    try:
        with _LOCAL_HTTP.open(
            f"http://127.0.0.1:{port}/api/health", timeout=2
        ) as response:
            payload = json.loads(response.read(4096).decode("utf-8", "replace"))
        return payload.get("status") == "ok" and "version" in payload
    except Exception:
        return False


def check_ports(checker: Checker) -> None:
    owners = _docker_port_owners()
    free: list[int] = []
    own: list[int] = []
    foreign: list[str] = []

    for port, label, _container in HOST_PORTS:
        if not _port_in_use(port):
            free.append(port)
            continue
        port_owners = owners.get(port, set())
        if _container in port_owners:
            own.append(port)
        else:
            foreign.append(f"{port}({label})")

    if foreign:
        hint = "停止占用进程，或修改 compose 端口映射后重试"
        if any(entry.startswith("8000(") for entry in foreign) and (
            _minirag_health_on(8000)
        ):
            hint = (
                "检测到 8000 已有 MiniRAG 服务（可能是本地 uvicorn）；"
                "容器部署前请先停止它"
            )
        checker.fail(
            "端口占用",
            "被其他进程占用: " + ", ".join(foreign),
            hint,
        )
    elif own:
        text = "已被本栈容器占用: " + ", ".join(str(port) for port in own)
        if free:
            text += "; 空闲: " + ", ".join(str(port) for port in free)
        checker.ok("端口", text)
    else:
        checker.ok("端口", "全部可用: " + ", ".join(str(port) for port in free))


# --------------------------------------------------------------------------- #
# Compose / 镜像
# --------------------------------------------------------------------------- #
def compose(compose_file: Path, *args: str) -> list[str]:
    return [
        _docker_bin(),
        "compose",
        "-f",
        str(compose_file.resolve()),
        *args,
    ]


def compose_config(compose_file: Path) -> dict:
    resolved = compose_file.resolve()
    if resolved in _COMPOSE_CONFIG_CACHE:
        return _COMPOSE_CONFIG_CACHE[resolved]
    result = run_capture(
        compose(compose_file, "config", "--format", "json"), timeout=30
    )
    if result.returncode != 0:
        raise CommandError(
            compose(compose_file, "config", "--format", "json"),
            result.returncode,
            _first_line(result.stderr or result.stdout),
        )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CommandError(
            compose(compose_file, "config", "--format", "json"),
            1,
            f"无法解析 compose 配置: {exc}",
        ) from exc
    _COMPOSE_CONFIG_CACHE[resolved] = data
    return data


def compose_images(compose_file: Path) -> list[str]:
    result = run_capture(compose(compose_file, "config", "--images"), timeout=30)
    if result.returncode != 0:
        return []
    return _dedupe(line.strip() for line in result.stdout.splitlines() if line.strip())


def _first(items: Iterable[str]) -> str:
    for item in items:
        return item
    return ""


def image_exists(image: str) -> bool:
    if not image:
        return False
    result = run_capture([_docker_bin(), "image", "inspect", image], timeout=30)
    return result.returncode == 0


def _expand_docker_arg(
    value: str,
    defaults: dict[str, str],
) -> str:
    match = re.fullmatch(
        r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}",
        value,
    )
    if not match:
        return value
    name = match.group(1)
    fallback = match.group(2)
    return defaults.get(name) or fallback or ""


def _images_from_dockerfile(
    path: Path,
    overrides: Optional[dict[str, str]] = None,
) -> list[str]:
    images: list[str] = []
    stages: set[str] = set()
    arg_defaults: dict[str, str] = {}
    overrides = overrides or {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return images

    from_pattern = re.compile(
        r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?",
        re.IGNORECASE,
    )
    copy_pattern = re.compile(r"^\s*COPY\s+.*--from=(\S+)", re.IGNORECASE)
    arg_pattern = re.compile(
        r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)(?:=(.*))?$",
        re.IGNORECASE,
    )

    for line in lines:
        arg_match = arg_pattern.match(line)
        if arg_match:
            name = arg_match.group(1)
            default = arg_match.group(2)
            if default is not None:
                arg_defaults[name] = overrides.get(name, default.strip().strip('"'))
            continue

        match = from_pattern.match(line)
        if match:
            reference = _expand_docker_arg(match.group(1), arg_defaults)
            stage = match.group(2)
            if (
                reference
                and reference.lower() not in stages
                and reference.lower() != "scratch"
            ):
                images.append(reference)
            if stage:
                stages.add(stage.lower())
            continue
        match = copy_pattern.match(line)
        if match:
            reference = _expand_docker_arg(match.group(1).strip('"'), arg_defaults)
            if not reference:
                continue
            if reference.lower() in stages or reference.isdigit():
                continue
            if "/" in reference or ":" in reference:
                images.append(reference)
    return images


def collect_images() -> list[str]:
    images: list[str] = []
    try:
        result = run_capture(compose(COMPOSE_INFRA, "config", "--images"), timeout=30)
    except CommandError:
        result = None
    if result is not None and result.returncode == 0:
        images.extend(
            line.strip() for line in result.stdout.splitlines() if line.strip()
        )
    overrides = {
        name: value
        for name in ("PYTHON_IMAGE", "UV_IMAGE", "NODE_IMAGE", "NGINX_IMAGE")
        if (value := os.environ.get(name))
    }
    for dockerfile in (BACKEND_DOCKERFILE, FRONTEND_DOCKERFILE):
        images.extend(_images_from_dockerfile(dockerfile, overrides))
    return _dedupe(images)


def check_docker_images(checker: Checker) -> None:
    images = collect_images()
    if not images:
        checker.skip("Docker 镜像", "未能解析镜像清单")
        return
    missing = [image for image in images if not image_exists(image)]
    if missing:
        shown = ", ".join(missing[:6])
        if len(missing) > 6:
            shown += " ..."
        checker.warn(
            "Docker 镜像",
            f"缺少 {len(missing)}/{len(images)} 个: {shown}",
            "运行 env_prepare 拉取（deploy 构建时也会自动拉取）",
        )
    else:
        checker.ok("Docker 镜像", f"{len(images)} 个已就绪")


def _compose_wait_capability() -> tuple[bool, bool]:
    global _COMPOSE_WAIT_CAPABILITY
    if _COMPOSE_WAIT_CAPABILITY is not None:
        return _COMPOSE_WAIT_CAPABILITY
    try:
        result = run_capture(compose(COMPOSE_INFRA, "up", "--help"), timeout=20)
    except CommandError:
        _COMPOSE_WAIT_CAPABILITY = (False, False)
        return _COMPOSE_WAIT_CAPABILITY
    text = f"{result.stdout}\n{result.stderr}"
    _COMPOSE_WAIT_CAPABILITY = ("--wait" in text, "--wait-timeout" in text)
    return _COMPOSE_WAIT_CAPABILITY


def _container_state(name: str) -> Optional[tuple[str, str]]:
    result = run_capture(
        [
            _docker_bin(),
            "inspect",
            name,
            "--format",
            "{{.State.Status}}|"
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
        ],
        timeout=15,
    )
    if result.returncode != 0:
        return None
    status, _, health = result.stdout.strip().partition("|")
    return status, health or "none"


def _compose_container_names(compose_file: Path) -> list[str]:
    try:
        data = compose_config(compose_file)
    except CommandError:
        return []
    names = []
    for service in data.get("services", {}).values():
        name = service.get("container_name")
        if name:
            names.append(name)
    return names


def wait_for_containers(
    compose_file: Path,
    label: str,
    timeout: int,
) -> None:
    names = _compose_container_names(compose_file)
    if not names:
        return
    deadline = time.monotonic() + timeout
    last_report = 0.0
    while time.monotonic() < deadline:
        states = {name: _container_state(name) for name in names}
        ready = True
        for name, state in states.items():
            if state is None:
                ready = False
                continue
            status, health = state
            if status in ("exited", "dead"):
                raise CommandError(
                    [],
                    1,
                    f"容器 {name} 状态异常: {status}",
                )
            if health == "unhealthy":
                raise CommandError(
                    [],
                    1,
                    f"容器 {name} 健康检查失败: unhealthy",
                )
            if status != "running" or health not in ("healthy", "none"):
                ready = False
        if ready:
            return
        now = time.monotonic()
        if now - last_report >= 10:
            parts = []
            for name, state in states.items():
                if state is None:
                    parts.append(f"{name}=未创建")
                else:
                    parts.append(f"{name}={state[0]}/{state[1]}")
            detail("等待中: " + ", ".join(parts))
            last_report = now
        time.sleep(3)
    raise CommandError(
        [],
        124,
        f"等待{label}超时 ({timeout}s)，请查看 compose 日志",
    )


def start_compose(
    compose_file: Path,
    label: str,
    timeout: int,
) -> None:
    step(f"启动{label}")
    cmd = compose(compose_file, "up", "-d", "--no-build")
    supports_wait, supports_timeout = _compose_wait_capability()
    if supports_wait:
        cmd.append("--wait")
        if supports_timeout:
            cmd.extend(["--wait-timeout", str(timeout)])
    run_stream(cmd)
    if _DRY_RUN:
        info(f"[dry-run] 跳过启动{label}")
        return
    if not supports_wait:
        wait_for_containers(compose_file, label, timeout)
    ok(f"{label}已启动")


def compose_down(compose_file: Path, volumes: bool = False) -> None:
    cmd = compose(compose_file, "down")
    if volumes:
        cmd.append("--volumes")
    run_stream(cmd)
    if _DRY_RUN:
        info(f"[dry-run] 跳过停止 {compose_file.name}")


def wait_http(
    url: str,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
    expect_status: Optional[str] = None,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with _LOCAL_HTTP.open(url, timeout=5) as response:
                body = response.read(4096)
                if 200 <= response.status < 300:
                    if expect_status is None:
                        return True
                    try:
                        payload = json.loads(body.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        payload = {}
                    if payload.get("status") == expect_status:
                        return True
        except Exception:
            pass
        time.sleep(2)
    return False


# --------------------------------------------------------------------------- #
# env_check
# --------------------------------------------------------------------------- #
def cmd_env_check(args: argparse.Namespace) -> int:
    system = detect_system()
    _print_header("环境检查", system)
    checker = Checker()

    check_system(checker, system)
    check_python(checker)
    check_project_files(checker)
    check_env_file(checker)
    docker_ok = check_docker_cli(checker, system)
    daemon_ok = check_docker_daemon(checker, system) if docker_ok else False
    compose_ok = check_compose(checker) if docker_ok else False
    if compose_ok:
        check_compose_config(checker)
    if not args.skip_network:
        check_network(checker)
    check_toolchains(checker, system)
    check_local_deps(checker)
    if daemon_ok:
        check_docker_images(checker)
    check_ports(checker)
    check_disk(checker)

    result = checker.summary()
    if result == 0 and args.strict and checker.warning_count:
        warn("严格模式: 存在警告，按失败处理")
        return 1
    return result


def run_preflight(
    require_env: bool,
    include_ports: bool,
    include_toolchains: bool,
    include_disk: bool = True,
) -> Checker:
    system = detect_system()
    checker = Checker()

    check_system(checker, system)
    check_python(checker)
    check_project_files(checker)
    check_env_file(checker, required=require_env)
    docker_ok = check_docker_cli(checker, system)
    if docker_ok:
        check_docker_daemon(checker, system)
        if check_compose(checker):
            check_compose_config(checker)
    if include_toolchains:
        check_toolchains(checker, system)
    if include_ports:
        check_ports(checker)
    if include_disk:
        check_disk(checker)
    checker.summary()
    return checker


# --------------------------------------------------------------------------- #
# env_prepare
# --------------------------------------------------------------------------- #
def ensure_env_files(dry_run: bool) -> bool:
    if not ENV_EXAMPLE.is_file():
        fail("缺少 .env.example", "无法生成 .env")
        return False

    if ENV_FILE.is_file():
        ok(".env 已存在")
    elif dry_run:
        info(f"[dry-run] 将从 .env.example 创建 {ENV_FILE}")
    else:
        shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
        if os.name != "nt":
            try:
                ENV_FILE.chmod(0o600)
            except OSError:
                pass
        warn(
            "已从 .env.example 创建 .env",
            "请填写 DASHSCOPE_API_KEY / MINERU_API_KEY 后再使用完整功能",
        )

    if WEB_ENV_EXAMPLE.is_file() and not WEB_ENV_FILE.exists():
        if dry_run:
            info(f"[dry-run] 将从 frontend/.env.example 创建 {WEB_ENV_FILE}")
        else:
            shutil.copyfile(WEB_ENV_EXAMPLE, WEB_ENV_FILE)
            ok("已创建 frontend/.env")
    return True


def _find_uv() -> Optional[str]:
    found = shutil.which("uv")
    if found:
        return found
    names = ["uv.exe"] if os.name == "nt" else ["uv"]
    for base in (Path.home() / ".local" / "bin", Path.home() / ".cargo" / "bin"):
        for name in names:
            candidate = base / name
            if candidate.is_file():
                os.environ["PATH"] = f"{base}{os.pathsep}{os.environ.get('PATH', '')}"
                return str(candidate)
    return None


def install_uv(system: SystemInfo) -> None:
    step("安装 uv")
    if system.key == "windows":
        shell = shutil.which("powershell") or shutil.which("pwsh")
        if not shell:
            raise CommandError([], 1, "未找到 PowerShell，无法自动安装 uv")
        cmd = [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "irm https://astral.sh/uv/install.ps1 | iex",
        ]
    else:
        if not shutil.which("sh"):
            raise CommandError([], 1, "未找到 sh，无法自动安装 uv")
        if shutil.which("curl"):
            cmd = [
                "sh",
                "-c",
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
            ]
        elif shutil.which("wget"):
            cmd = [
                "sh",
                "-c",
                "wget -qO- https://astral.sh/uv/install.sh | sh",
            ]
        else:
            raise CommandError([], 1, "需要 curl 或 wget 才能自动安装 uv")
    run_stream(cmd)


def ensure_uv(args: argparse.Namespace, system: SystemInfo) -> Optional[str]:
    uv = shutil.which("uv")
    if uv:
        return uv
    if _DRY_RUN:
        warn("uv 未安装", "dry-run 只打印命令，不执行安装")
        return "uv"

    warn("uv 未安装")
    if not args.install_tools:
        if not sys.stdin.isatty():
            fail(
                "缺少 uv",
                "使用 --install-tools 自动安装，或手动安装后重试",
            )
            return None
        try:
            answer = input("是否自动安装 uv? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            fail("缺少 uv", "已取消自动安装")
            return None

    install_uv(system)
    uv = _find_uv()
    if not uv:
        fail("uv 安装后仍未找到", "重新打开终端，或手动把 uv 加入 PATH")
        return None
    ok(f"uv 已安装: {uv}")
    return uv


def _pypi_candidates(primary: str) -> list[str]:
    candidates = [primary]
    if primary == DEFAULT_PYPI_INDEX:
        return candidates
    known = any(
        primary == mirror or primary.startswith(f"{mirror.rstrip('/')}/")
        for mirror in CN_PYPI_MIRRORS
    )
    if known:
        candidates = [primary, *CN_PYPI_MIRRORS, DEFAULT_PYPI_INDEX]
    seen: set[str] = set()
    result: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


def sync_python_deps(
    uv: str,
    args: argparse.Namespace,
    mirrors: MirrorConfig,
) -> None:
    cmd = [uv, "sync", "--frozen"]
    if args.no_dev:
        cmd.append("--no-dev")

    if not mirrors.pypi_index or mirrors.pypi_index == DEFAULT_PYPI_INDEX:
        run_stream(cmd)
        return

    candidates = _pypi_candidates(mirrors.pypi_index)
    if _DRY_RUN:
        run_stream([uv, "lock", "--default-index", mirrors.pypi_index])
        run_stream(cmd)
        return

    # uv.lock 记录的是 pypi.org / files.pythonhosted.org 地址，--frozen 不会改用镜像；
    # 临时按镜像重新锁定（保持锁内版本，只重写 source/URL），安装后恢复原文件。
    # 已知国内镜像会按顺序回退，避免单个镜像对个别包 403 / 缺包导致整体失败。
    original_lock = UV_LOCK.read_bytes()
    try:
        for index in candidates:
            info(f"PyPI 索引: {index}")
            lock_rc = run_stream([uv, "lock", "--default-index", index], check=False)
            if lock_rc != 0:
                warn(f"重新锁定失败，尝试下一个镜像: {index}")
                UV_LOCK.write_bytes(original_lock)
                continue
            sync_rc = run_stream(cmd, check=False)
            if sync_rc == 0:
                return
            warn(f"依赖安装失败，尝试下一个镜像: {index}")
            UV_LOCK.write_bytes(original_lock)
    finally:
        UV_LOCK.write_bytes(original_lock)
    raise CommandError(
        [],
        1,
        "所有 PyPI 镜像均失败；请检查网络，或用 --pypi-index 指定可用镜像",
    )


def install_node_deps(
    args: argparse.Namespace,
    mirrors: MirrorConfig,
) -> None:
    npm = shutil.which("npm")
    if not npm:
        warn(
            "跳过前端依赖",
            "未找到 npm；Docker 前端构建不依赖宿主机 Node.js",
        )
        return
    version = _tool_version([npm, "--version"], timeout=15)
    if not version:
        warn("跳过前端依赖", "npm 无法执行")
        return

    step("安装前端依赖")
    if (WEB_DIR / "package-lock.json").is_file():
        cmd = [npm, "ci", "--no-audit", "--no-fund"]
    else:
        warn("缺少 frontend/package-lock.json", "回退到 npm install")
        cmd = [npm, "install", "--no-audit", "--no-fund"]
    if mirrors.npm_registry:
        info(f"npm registry: {mirrors.npm_registry}")
        cmd.append(f"--registry={mirrors.npm_registry}")
    run_stream(cmd, cwd=WEB_DIR)
    ok("前端依赖已就绪 (frontend/node_modules)")


def pull_images() -> None:
    images = collect_images()
    if not images:
        warn("未发现需要拉取的镜像", "跳过 Docker 镜像拉取")
        return

    step(f"拉取 Docker 镜像 ({len(images)} 个)")
    failed: list[str] = []
    for image in images:
        info(f"拉取 {image}")
        try:
            run_with_retry([_docker_bin(), "pull", image], attempts=2)
        except CommandError:
            if image_exists(image):
                # 镜像已存在时允许离线 / 仓库鉴权失败: 本次部署仍可用
                warn(f"拉取失败，但本地已有该镜像，继续: {image}")
            else:
                failed.append(image)
                fail(f"镜像拉取失败: {image}")
    if failed:
        raise CommandError([], 1, "以下镜像拉取失败: " + ", ".join(failed))
    if _DRY_RUN:
        info("[dry-run] 跳过实际拉取")
        return
    ok("Docker 镜像拉取完成")


def cmd_env_prepare(args: argparse.Namespace) -> int:
    system = detect_system()
    _print_header("环境准备", system)

    if not ensure_env_files(args.dry_run):
        return 1

    step("安装前检查")
    checker = run_preflight(
        require_env=ENV_FILE.is_file(),
        include_ports=False,
        include_toolchains=True,
    )
    if checker.failures:
        return 1

    mirrors = MirrorConfig()
    if not args.skip_python or not args.skip_node:
        step("镜像源选择")
        mirrors = resolve_mirror_config(args)
        announce_mirrors(mirrors)

    if args.skip_python:
        info("跳过 Python 依赖 (--skip-python)")
    else:
        uv = ensure_uv(args, system)
        if not uv:
            return 1
        step("安装 Python 依赖")
        sync_python_deps(uv, args, mirrors)
        ok("Python 依赖已就绪 (.venv)")

    if args.skip_node:
        info("跳过前端依赖 (--skip-node)")
    else:
        install_node_deps(args, mirrors)

    if args.skip_pull:
        info("跳过 Docker 镜像拉取 (--skip-pull)")
    else:
        pull_images()

    values = parse_env_file(ENV_FILE)
    if is_placeholder(values.get("DASHSCOPE_API_KEY", "")) or is_placeholder(
        values.get("MINERU_API_KEY", "")
    ):
        warn(
            ".env 中仍有未配置的 API Key",
            "编辑 .env 填写后，再使用上传 / 查询功能",
        )

    step("环境准备完成")
    _print("下一步: python minirag.py deploy")
    return 0


# --------------------------------------------------------------------------- #
# deploy
# --------------------------------------------------------------------------- #
def build_images(
    args: argparse.Namespace,
    mirrors: MirrorConfig,
) -> None:
    build_env = os.environ.copy()
    build_env["UV_INDEX_URL"] = mirrors.pypi_index or DEFAULT_PYPI_INDEX
    build_env["NPM_REGISTRY"] = mirrors.npm_registry or DEFAULT_NPM_REGISTRY
    for compose_file, label in (
        (COMPOSE_BACKEND, "后端"),
        (COMPOSE_FRONTEND, "前端"),
    ):
        step(f"构建{label}镜像")
        cmd = compose(compose_file, "build")
        if args.pull:
            cmd.append("--pull")
        if args.no_cache:
            cmd.append("--no-cache")
        run_stream(cmd, env=build_env)
        image = _first(compose_images(compose_file))
        if not image:
            raise CommandError(cmd, 1, f"无法解析{label}镜像名")
        if _DRY_RUN:
            info(f"[dry-run] 将构建{label}镜像: {image}")
            continue
        if not image_exists(image):
            raise CommandError(cmd, 1, f"构建后镜像不存在: {image}")
        ok(f"{label}镜像: {image}")


def ensure_built_images() -> None:
    for compose_file, label in (
        (COMPOSE_BACKEND, "后端"),
        (COMPOSE_FRONTEND, "前端"),
    ):
        image = _first(compose_images(compose_file))
        if not image:
            raise CommandError([], 1, f"无法解析{label}镜像名")
        if not image_exists(image):
            raise CommandError(
                [],
                1,
                f"{label}镜像不存在: {image}；去掉 --no-build 重新构建",
            )
        ok(f"{label}镜像已存在: {image}")


def _start_with_log_hint(compose_file: Path, label: str, timeout: int) -> None:
    try:
        start_compose(compose_file, label, timeout)
    except CommandError:
        fail(f"{label}启动失败")
        detail("查看日志: " + _display_cmd(compose(compose_file, "logs", "--tail=100")))
        raise


def cmd_deploy(args: argparse.Namespace) -> int:
    system = detect_system()
    _print_header("一键部署", system)

    step("部署前检查")
    checker = run_preflight(
        require_env=True,
        include_ports=True,
        include_toolchains=False,
    )
    if checker.failures:
        return 1

    if args.no_build:
        info("跳过镜像构建 (--no-build)")
        ensure_built_images()
    else:
        step("镜像源选择")
        mirrors = resolve_mirror_config(args)
        announce_mirrors(mirrors)
        build_images(args, mirrors)

    _start_with_log_hint(COMPOSE_INFRA, "基础设施", args.timeout)
    _start_with_log_hint(COMPOSE_BACKEND, "后端", args.timeout)
    _start_with_log_hint(COMPOSE_FRONTEND, "前端", args.timeout)

    if _DRY_RUN:
        info("dry-run: 跳过服务验证")
        return 0

    step("验证服务")
    if not wait_http(
        "http://127.0.0.1:8000/api/health",
        timeout=DEFAULT_HTTP_TIMEOUT,
        expect_status="ok",
    ):
        fail("后端健康检查失败")
        detail(
            "查看日志: " + _display_cmd(compose(COMPOSE_BACKEND, "logs", "--tail=100"))
        )
        return 1
    ok("后端 API 可访问")

    if not wait_http(
        "http://127.0.0.1:8080/",
        timeout=DEFAULT_HTTP_TIMEOUT,
    ):
        fail("前端页面不可访问")
        detail(
            "查看日志: " + _display_cmd(compose(COMPOSE_FRONTEND, "logs", "--tail=100"))
        )
        return 1
    ok("前端页面可访问")

    if not wait_http(
        "http://127.0.0.1:8080/api/health",
        timeout=DEFAULT_HTTP_TIMEOUT,
        expect_status="ok",
    ):
        fail("前端 /api 反代后端失败")
        detail("检查 frontend/nginx.conf 与后端容器状态")
        return 1
    ok("前端 /api 反代正常")

    print_endpoints()
    return 0


def print_endpoints() -> None:
    step("部署完成")
    _print("  前端页面      http://127.0.0.1:8080")
    _print("  后端 API 文档  http://127.0.0.1:8000/docs")
    _print("  Attu          http://127.0.0.1:7001")
    _print("  MinIO 控制台  http://127.0.0.1:9001")
    _print("")
    _print("清空数据并重置: python minirag.py reset")


# --------------------------------------------------------------------------- #
# reset
# --------------------------------------------------------------------------- #
def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def persistence_targets() -> tuple[list[Path], list[str], list[str]]:
    data = compose_config(COMPOSE_INFRA)
    bind_dirs: list[Path] = []
    for service in data.get("services", {}).values():
        for volume in service.get("volumes", []):
            if (
                volume.get("type") == "bind"
                and volume.get("target") in DATA_MOUNT_TARGETS
            ):
                source = volume.get("source")
                if source:
                    bind_dirs.append(Path(source))

    volume_names = [
        config.get("name", key) for key, config in data.get("volumes", {}).items()
    ]
    network_names = [
        config.get("name", key) for key, config in data.get("networks", {}).items()
    ]

    if not bind_dirs:
        bind_dirs = [
            DOCKER_DIR / "volumes" / name for name in ("etcd", "milvus", "minio")
        ]
    if not volume_names:
        volume_names = ["mini-rag_mongodb_data", "mini-rag_mongodb_config"]
    if not network_names:
        network_names = ["milvus"]
    return _dedupe_paths(bind_dirs), _dedupe(volume_names), _dedupe(network_names)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def ensure_wipe_safe(path: Path) -> None:
    resolved = path.resolve()
    root = ROOT.resolve()
    home = Path.home().resolve()

    if resolved == Path(resolved.anchor) or resolved == home:
        raise CommandError([], 1, f"拒绝清空敏感目录: {resolved}")
    if resolved == root or _is_within(root, resolved):
        raise CommandError([], 1, f"拒绝清空项目根目录或其父目录: {resolved}")
    for marker in (
        ROOT / "pyproject.toml",
        ROOT / "README.md",
        *COMPOSE_FILES,
    ):
        marker_path = marker.resolve()
        if resolved == marker_path or _is_within(marker_path, resolved):
            raise CommandError([], 1, f"拒绝清空包含项目文件的目录: {resolved}")


def docker_wipe_dir(path: Path) -> None:
    cmd = [
        _docker_bin(),
        "run",
        "--rm",
        "--user",
        "0:0",
        "--mount",
        f"type=bind,source={path},target=/wipe",
        "python:3.12-slim",
        "sh",
        "-c",
        "find /wipe -mindepth 1 -delete",
    ]
    run_stream(cmd)


def wipe_dir_contents(path: Path) -> None:
    if _DRY_RUN:
        info(f"[dry-run] 清空目录内容: {path}")
        return
    ensure_wipe_safe(path)
    if not path.exists():
        detail(f"目录不存在，跳过: {path}")
        return
    if not path.is_dir():
        raise CommandError([], 1, f"不是目录: {path}")
    info(f"清空目录内容: {path}")
    try:
        for child in list(path.iterdir()):
            if child.is_symlink() or child.is_file():
                child.unlink()
            else:
                shutil.rmtree(child)
    except OSError as exc:
        warn(f"宿主机清理失败: {exc}", "改用 Docker root 容器清理")
        docker_wipe_dir(path)


def remove_volume(name: str) -> None:
    result = run_capture([_docker_bin(), "volume", "inspect", name], timeout=20)
    if result.returncode != 0:
        detail(f"数据卷不存在，跳过: {name}")
        return
    if _DRY_RUN:
        info(f"[dry-run] 删除数据卷: {name}")
        return
    result = run_capture([_docker_bin(), "volume", "rm", name], timeout=30)
    if result.returncode != 0:
        warn(
            f"删除数据卷失败: {name}",
            _first_line(result.stderr) or "可能仍被其他容器占用",
        )
    else:
        ok(f"已删除数据卷: {name}")


def remove_network(name: str) -> None:
    result = run_capture([_docker_bin(), "network", "inspect", name], timeout=20)
    if result.returncode != 0:
        return
    if _DRY_RUN:
        info(f"[dry-run] 删除网络: {name}")
        return
    result = run_capture([_docker_bin(), "network", "rm", name], timeout=30)
    if result.returncode == 0:
        ok(f"已删除网络: {name}")
    else:
        warn(f"删除网络失败: {name}", _first_line(result.stderr))


def print_reset_plan(
    bind_dirs: list[Path],
    volume_names: list[str],
    runtime_dirs: list[Path],
    keep_down: bool,
) -> None:
    step("将删除以下持久化数据")
    for path in bind_dirs:
        _print(f"  - 数据目录: {_display_path(path)}")
    for name in volume_names:
        _print(f"  - 数据卷:   {name}")
    for path in runtime_dirs:
        _print(f"  - 运行数据: {_display_path(path)}")
    if not runtime_dirs:
        _print("  - 运行数据: 保留 (--keep-runtime)")
    _print("")
    _print("此操作不可恢复。")
    if keep_down:
        _print("完成后保持容器停止 (--keep-down)。")
    else:
        _print("完成后重启基础设施与已构建的应用容器，数据库由后端自检重建。")


def confirm_reset() -> bool:
    if not sys.stdin.isatty():
        fail("非交互终端", "确认清空请加 --yes")
        return False
    try:
        answer = input("确认清空？输入 yes 继续: ").strip().lower()
    except EOFError:
        return False
    if answer not in ("yes", "y"):
        info("已取消")
        return False
    return True


def cmd_reset(args: argparse.Namespace) -> int:
    system = detect_system()
    _print_header("重置持久化数据", system)

    step("重置前检查")
    checker = run_preflight(
        require_env=False,
        include_ports=False,
        include_toolchains=False,
        include_disk=False,
    )
    if checker.failures:
        return 1

    try:
        bind_dirs, volume_names, network_names = persistence_targets()
    except CommandError as exc:
        warn("解析 compose 数据路径失败，使用默认路径", str(exc))
        bind_dirs = [
            DOCKER_DIR / "volumes" / name for name in ("etcd", "milvus", "minio")
        ]
        volume_names = ["mini-rag_mongodb_data", "mini-rag_mongodb_config"]
        network_names = ["milvus"]

    runtime_dirs = [] if args.keep_runtime else [VAR_UPLOADS, VAR_IMPORT, VAR_TMP]
    print_reset_plan(bind_dirs, volume_names, runtime_dirs, args.keep_down)

    if not _DRY_RUN and not args.yes and not confirm_reset():
        return 1

    step("停止容器")
    compose_down(COMPOSE_FRONTEND)
    compose_down(COMPOSE_BACKEND)
    compose_down(COMPOSE_INFRA, volumes=True)
    ok("容器已停止")

    step("清空持久化数据")
    for path in bind_dirs:
        wipe_dir_contents(path)
    for path in runtime_dirs:
        wipe_dir_contents(path)
    for name in volume_names:
        remove_volume(name)
    for name in network_names:
        remove_network(name)
    ok("持久化数据已清空")

    if args.keep_down:
        step("重置完成")
        _print("容器保持停止；下次部署: python minirag.py deploy")
        return 0

    step("重新初始化")
    _start_with_log_hint(COMPOSE_INFRA, "基础设施", args.timeout)

    backend_image = _first(compose_images(COMPOSE_BACKEND))
    frontend_image = _first(compose_images(COMPOSE_FRONTEND))
    started_backend = False

    if not ENV_FILE.is_file():
        warn("缺少 .env", "跳过应用启动；数据库将在下次 deploy 时初始化")
    elif backend_image and image_exists(backend_image):
        _start_with_log_hint(COMPOSE_BACKEND, "后端", args.timeout)
        started_backend = True
        if frontend_image and image_exists(frontend_image):
            _start_with_log_hint(COMPOSE_FRONTEND, "前端", args.timeout)
        else:
            warn("前端镜像不存在", "跳过前端启动；运行 deploy 构建")
    else:
        warn(
            "后端镜像不存在",
            "跳过应用启动；运行 deploy 自动构建并初始化数据库",
        )

    if started_backend and not _DRY_RUN:
        step("验证数据库初始化")
        if not wait_http(
            "http://127.0.0.1:8000/api/health",
            timeout=DEFAULT_HTTP_TIMEOUT,
            expect_status="ok",
        ):
            fail("后端健康检查失败")
            detail(
                "查看日志: "
                + _display_cmd(compose(COMPOSE_BACKEND, "logs", "--tail=100"))
            )
            return 1
        ok("后端启动自检通过，数据库已重建")

    step("重置完成")
    _print("持久化数据已清空；可重新上传文档。")
    return 0


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def _add_mirror_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mirror",
        choices=("auto", "global", "cn"),
        default="auto",
        help="软件包镜像策略: auto=自动探测, global=官方源, cn=国内镜像",
    )
    parser.add_argument(
        "--pypi-index",
        metavar="URL",
        default=None,
        help="覆盖 PyPI 索引（例如阿里云 / 清华镜像）",
    )
    parser.add_argument(
        "--npm-registry",
        metavar="URL",
        default=None,
        help="覆盖 npm registry（例如 https://registry.npmmirror.com）",
    )


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--dry-run",
        action="store_true",
        default=argparse.SUPPRESS,
        help="只打印将要执行的命令，不修改任何状态",
    )

    parser = argparse.ArgumentParser(
        prog="minirag.py",
        description="MiniRAG 一键部署工具（Linux / macOS / Windows）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python minirag.py env_check\n"
            "  python minirag.py env_prepare\n"
            "  python minirag.py deploy\n"
            "  python minirag.py reset\n"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要执行的命令，不修改任何状态",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="命令")

    check = subparsers.add_parser("env_check", parents=[common], help="检查部署环境")
    check.add_argument("--strict", action="store_true", help="把警告也视为失败")
    check.add_argument(
        "--skip-network",
        action="store_true",
        help="跳过 PyPI / npm / Docker 镜像源连通性探测",
    )
    check.set_defaults(func=cmd_env_check)

    prepare = subparsers.add_parser(
        "env_prepare", parents=[common], help="安装依赖并拉取 Docker 镜像"
    )
    prepare.add_argument("--skip-python", action="store_true", help="跳过 uv sync")
    prepare.add_argument("--skip-node", action="store_true", help="跳过 npm ci")
    prepare.add_argument(
        "--skip-pull", action="store_true", help="跳过 Docker 镜像拉取"
    )
    prepare.add_argument(
        "--no-dev", action="store_true", help="uv sync 不安装 dev 依赖"
    )
    prepare.add_argument(
        "--install-tools",
        action="store_true",
        help="缺少 uv 时自动安装（否则交互询问）",
    )
    _add_mirror_args(prepare)
    prepare.set_defaults(func=cmd_env_prepare)

    deploy = subparsers.add_parser(
        "deploy",
        aliases=["depoly"],
        parents=[common],
        help="构建镜像并按顺序启动容器",
    )
    deploy.add_argument("--no-build", action="store_true", help="跳过镜像构建")
    deploy.add_argument("--no-cache", action="store_true", help="构建时不使用缓存")
    deploy.add_argument("--pull", action="store_true", help="构建前拉取最新基础镜像")
    deploy.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_WAIT_TIMEOUT,
        help=f"等待容器健康的秒数（默认 {DEFAULT_WAIT_TIMEOUT}）",
    )
    _add_mirror_args(deploy)
    deploy.set_defaults(func=cmd_deploy)

    reset = subparsers.add_parser(
        "reset", parents=[common], help="清空持久化存储并重置数据库"
    )
    reset.add_argument("-y", "--yes", action="store_true", help="跳过确认")
    reset.add_argument(
        "--keep-runtime",
        action="store_true",
        help="保留 var/uploads、var/import、var/tmp",
    )
    reset.add_argument(
        "--keep-down",
        action="store_true",
        help="清空后不重启容器",
    )
    reset.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_WAIT_TIMEOUT,
        help=f"等待容器健康的秒数（默认 {DEFAULT_WAIT_TIMEOUT}）",
    )
    reset.set_defaults(func=cmd_reset)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    global _DRY_RUN
    _configure_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 1
    _DRY_RUN = bool(getattr(args, "dry_run", False))
    if _DRY_RUN:
        warn("dry-run 模式：只打印执行计划，不修改任何状态")
    if getattr(args, "timeout", 1) <= 0:
        fail("--timeout 必须大于 0")
        return 1

    try:
        return int(args.func(args))
    except CommandError as exc:
        fail(str(exc))
        return exc.returncode if 0 < exc.returncode < 256 else 1
    except KeyboardInterrupt:
        _print("\n已取消")
        return 130
    except BrokenPipeError:
        return 0
    except Exception as exc:
        fail(f"未预期的错误: {exc}")
        if os.environ.get("MINIRAG_DEBUG"):
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
