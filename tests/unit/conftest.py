import pytest

from tests.support.guards import install_model_guard


@pytest.fixture(autouse=True)
def _model_guard(monkeypatch):
    install_model_guard(monkeypatch)
    yield
