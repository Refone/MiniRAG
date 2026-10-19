"""单元测试: src/api/setup.py

被测对象:
    check_milvus / check_minio / check_mongodb   三类数据服务的检查编排
    runtime_dirs / ensure_runtime_dirs           运行时目录 (存在且可写)
    warn_missing_api_keys                        软检查 (API key 缺失仅告警)
    setup                                       汇总执行: 全部通过才不抛错, 失败项全部上报

外部依赖全部 mock: 三个 client 换成桩对象, 日志换成记录器,
目录经 monkeypatch runtime_dirs 指向 tmp_path, 用例全程不触网。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api import setup as setup_mod


# --------------------------------------------------------------------------- #
# 桩对象与 fixture
# --------------------------------------------------------------------------- #
class _FakeMilvus:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[str] = []

    def _raise(self):
        if self.error:
            raise self.error

    def check_health(self):
        self.calls.append("check_health")
        self._raise()

    def prepare_item_name_collection(self):
        self.calls.append("prepare_item_name_collection")
        self._raise()

    def prepare_chunks_collection(self):
        self.calls.append("prepare_chunks_collection")
        self._raise()


class _FakeMinio:
    def __init__(self, error: Exception | None = None):
        self.error = error

    def _raise(self):
        if self.error:
            raise self.error

    def check_health(self):
        self._raise()

    def prepare_bucket(self):
        self._raise()


class _FakeMongo:
    def __init__(self, error: Exception | None = None):
        self.error = error

    def check_health(self):
        if self.error:
            raise self.error


class _RecordingLogger:
    """记录所有日志调用, 替代 loguru, 让用例可断言日志内容。"""

    def __init__(self):
        self.messages: list[tuple[str, str]] = []

    def _record(self, level: str, message: str, *args, **kwargs):
        self.messages.append((level, message))

    def debug(self, message, *args, **kwargs):
        self._record("debug", message)

    def info(self, message, *args, **kwargs):
        self._record("info", message)

    def success(self, message, *args, **kwargs):
        self._record("success", message)

    def warning(self, message, *args, **kwargs):
        self._record("warning", message)

    def error(self, message, *args, **kwargs):
        self._record("error", message)

    def exception(self, message, *args, **kwargs):
        self._record("exception", message)


@pytest.fixture
def healthy_clients(monkeypatch):
    milvus, minio, mongo = _FakeMilvus(), _FakeMinio(), _FakeMongo()
    monkeypatch.setattr(setup_mod, "MILVUS_CLIENT", milvus)
    monkeypatch.setattr(setup_mod, "MINIO_CLIENT", minio)
    monkeypatch.setattr(setup_mod, "MONGODB_CLIENT", mongo)
    return milvus, minio, mongo


@pytest.fixture
def recording_logger(monkeypatch):
    logger = _RecordingLogger()
    monkeypatch.setattr(setup_mod, "logger", logger)
    return logger


@pytest.fixture
def tmp_runtime_dirs(monkeypatch, tmp_path):
    dirs = [tmp_path / "uploads", tmp_path / "import", tmp_path / "logs"]
    monkeypatch.setattr(setup_mod, "runtime_dirs", lambda: dirs)
    return dirs


# --------------------------------------------------------------------------- #
# setup: 全通过 / 部分失败汇总
# --------------------------------------------------------------------------- #
def test_setup_passes_when_all_checks_ok(healthy_clients, recording_logger, tmp_runtime_dirs):
    milvus, _, _ = healthy_clients

    setup_mod.setup()  # 不应抛异常

    # Milvus 检查按「连通性 -> item_name 集合 -> chunks 集合」顺序执行
    assert milvus.calls == [
        "check_health",
        "prepare_item_name_collection",
        "prepare_chunks_collection",
    ]
    # 运行时目录全部创建
    assert all(d.is_dir() for d in tmp_runtime_dirs)
    # 每个硬依赖步骤都有「自检通过」日志
    passed = [msg for level, msg in recording_logger.messages if "自检通过" in msg]
    assert len(passed) == len(setup_mod._HARD_STEPS)


def test_setup_reports_all_failures_with_hints(monkeypatch, recording_logger, tmp_runtime_dirs):
    monkeypatch.setattr(setup_mod, "MILVUS_CLIENT", _FakeMilvus(error=ConnectionError("milvus down")))
    monkeypatch.setattr(setup_mod, "MINIO_CLIENT", _FakeMinio())
    monkeypatch.setattr(setup_mod, "MONGODB_CLIENT", _FakeMongo(error=ConnectionError("mongo down")))

    with pytest.raises(RuntimeError) as exc_info:
        setup_mod.setup()

    message = str(exc_info.value)
    # 失败项全部上报 (2/4), 且带排查提示
    assert "2/4" in message
    assert "Milvus" in message and "milvus down" in message
    assert "MongoDB" in message and "mongo down" in message
    assert "MILVUS_ENDPOINT" in message
    assert "MONGODB_URI" in message
    # 前一步失败不阻断后续检查: MinIO 步骤应照常通过
    assert any("MinIO" in msg for level, msg in recording_logger.messages if "自检通过" in msg)


def test_setup_single_failure_counts_correctly(monkeypatch, recording_logger, tmp_runtime_dirs):
    monkeypatch.setattr(setup_mod, "MILVUS_CLIENT", _FakeMilvus(error=RuntimeError("boom")))
    monkeypatch.setattr(setup_mod, "MINIO_CLIENT", _FakeMinio())
    monkeypatch.setattr(setup_mod, "MONGODB_CLIENT", _FakeMongo())

    with pytest.raises(RuntimeError) as exc_info:
        setup_mod.setup()

    assert "1/4" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# 运行时目录
# --------------------------------------------------------------------------- #
def test_runtime_dirs_returns_configured_paths():
    from common.config.app_config import APP_CONFIG
    from common.config.env_config import ENV_CONFIG

    assert setup_mod.runtime_dirs() == [
        APP_CONFIG.upload_dir,
        Path(ENV_CONFIG.mineru.unzip_dir),
        Path(ENV_CONFIG.log.file_dir),
    ]


def test_ensure_runtime_dirs_creates_all(monkeypatch, tmp_path):
    dirs = [tmp_path / "a", tmp_path / "b", tmp_path / "c"]
    monkeypatch.setattr(setup_mod, "runtime_dirs", lambda: dirs)

    setup_mod.ensure_runtime_dirs()

    assert all(d.is_dir() for d in dirs)


def test_ensure_runtime_dirs_leaves_no_probe_files(monkeypatch, tmp_path):
    dirs = [tmp_path / "probe"]
    monkeypatch.setattr(setup_mod, "runtime_dirs", lambda: dirs)

    setup_mod.ensure_runtime_dirs()

    # 探针文件用完即删, 目录内不留残留
    assert list(dirs[0].iterdir()) == []


# --------------------------------------------------------------------------- #
# API key 软检查
# --------------------------------------------------------------------------- #
def test_warn_missing_api_keys_warns_only_for_empty(monkeypatch, recording_logger):
    monkeypatch.setattr(
        setup_mod,
        "_API_KEY_CHECKS",
        [
            ("MINERU_API_KEY", "", "PDF 解析 (MinerU)"),
            ("LLM_API_KEY", "sk-xxx", "问答生成 (LLM)"),
        ],
    )

    setup_mod.warn_missing_api_keys()

    warnings = [msg for level, msg in recording_logger.messages if level == "warning"]
    assert len(warnings) == 1
    assert "MINERU_API_KEY" in warnings[0]
