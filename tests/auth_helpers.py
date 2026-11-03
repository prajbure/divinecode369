"""Synthetic credentials and isolated session storage for authentication tests."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from app import config
from app.admin_auth import hash_password

ORIGIN = "https://terminal.example"
PASSWORD = "only-for-tests-password-369"
PASSWORD_HASH = hash_password(PASSWORD)


@contextmanager
def admin_environment(folder, origin=ORIGIN):
    with patch.multiple(config, ADMIN_TOKEN="test-backend-only-key-" + "x" * 32,
                        ADMIN_USERNAME="owner", ADMIN_PASSWORD_HASH=PASSWORD_HASH,
                        ADMIN_ORIGIN=origin, ADMIN_SESSION_SECONDS=300,
                        ADMIN_SESSION_DATABASE_PATH=Path(folder) / "admin.sqlite3"):
        yield


def sign_in(client):
    status = client.get("/auth/admin/session")
    assert status.status_code == 200, status.text
    client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": status.json()["csrf_token"]})
    response = client.post("/auth/admin/login", json={"username": "owner", "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response
