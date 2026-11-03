from dataclasses import replace

import pytest

from api import main as api_main
from common.config.app_config import APP_CONFIG

pytestmark = pytest.mark.contract


def test_upload__invalid_or_oversize__400_413_and_202_args(
    client, monkeypatch, tmp_path
):
    """Given 上传路由 When 缺名/缺 session/超限/正常 Then 400/400/413/202。"""
    calls: list[dict] = []

    def fake_arun_import(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("service.import_service.arun_import", fake_arun_import)
    monkeypatch.setattr(api_main, "UPLOAD_TMP_DIR", tmp_path)

    missing_name = client.post(
        "/api/upload",
        files={"file": ("", b"x")},
        data={"session_id": "s1"},
    )
    # 空 filename 会被 Starlette 解析成普通表单字符串，FastAPI 在进入路由前返回 422。
    assert missing_name.status_code == 422, missing_name.text

    missing_session = client.post(
        "/api/upload",
        files={"file": ("a.txt", b"x")},
    )
    assert missing_session.status_code == 400, missing_session.text

    monkeypatch.setattr(api_main, "APP_CONFIG", replace(APP_CONFIG, max_upload_bytes=4))
    oversize = client.post(
        "/api/upload",
        files={"file": ("a.txt", b"12345")},
        data={"session_id": "s1"},
    )
    assert oversize.status_code == 413, oversize.text
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == []

    monkeypatch.setattr(api_main, "APP_CONFIG", APP_CONFIG)
    ok = client.post(
        "/api/upload",
        files={"file": ("a.txt", b"hello")},
        data={"session_id": "s1"},
    )
    assert ok.status_code == 202, ok.text
    payload = ok.json()
    assert payload["status"] == "pending"
    task_id = payload["task_id"]
    assert task_id
    assert (tmp_path / task_id / "a.txt").read_bytes() == b"hello"
    assert len(calls) == 1, calls
    assert calls[0]["task_id"] == task_id
    assert calls[0]["session_id"] == "s1"
    assert calls[0]["origin_file_path"].endswith("a.txt")
