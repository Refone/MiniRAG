import pytest
from fastapi.testclient import TestClient

from tests.support.guards import install_model_guard

install_model_guard()


@pytest.fixture
def client():
    from api.main import app

    test_client = TestClient(app)  # 不用 with：不触发 lifespan/startup_checks
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()
