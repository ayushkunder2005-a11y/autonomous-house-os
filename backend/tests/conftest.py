import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DB = Path(__file__).resolve().parent / "test_house_os.db"
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["HOUSE_ENVIRONMENT"] = "test"
os.environ["HOUSE_DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB.as_posix()}"
os.environ["HOUSE_DATABASE_AUTO_CREATE"] = "true"
os.environ["HOUSE_SECRET_KEY"] = "test-secret-key-that-is-longer-than-thirty-two-characters"
os.environ["HOUSE_BOOTSTRAP_ADMIN_EMAIL"] = "admin@example.com"
os.environ["HOUSE_BOOTSTRAP_ADMIN_PASSWORD"] = "Admin-password-123!"
os.environ["HOUSE_BOOTSTRAP_ADMIN_PIN"] = "2468"
os.environ["HOUSE_COMMAND_TIMEOUT_SECONDS"] = "0.03"
os.environ["HOUSE_COMMAND_MAX_RETRIES"] = "1"
os.environ["HOUSE_RATE_LIMIT_PER_MINUTE"] = "10000"

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture(scope="session")
def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "admin@example.com", "password": "Admin-password-123!"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="session")
def simulation(client: TestClient, admin_headers: dict[str, str]) -> dict:
    response = client.post("/api/v1/simulation/bootstrap", headers=admin_headers)
    assert response.status_code == 201, response.text
    return response.json()
