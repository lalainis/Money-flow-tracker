import importlib
import os
import sys

import pytest


@pytest.fixture()
def app_module(tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"
    upload_dir = tmp_path / "uploads"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)

    module_names = ["app", "app_core", "models", "services", "settings"]
    for module_name in module_names:
        if module_name in sys.modules:
            del sys.modules[module_name]
    for module_name in list(sys.modules):
        if module_name == "routes" or module_name.startswith("routes."):
            del sys.modules[module_name]

    module = importlib.import_module("app")
    module.app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_path}",
    )

    with module.app.app_context():
        module.db.drop_all()
        module.db.create_all()
        module.ensure_schema_compatibility()
        module.ensure_seed_data()

    yield module

    with module.app.app_context():
        module.db.session.remove()
        module.db.drop_all()


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


@pytest.fixture()
def admin_token(client):
    response = client.post(
        "/api/auth/login",
        json={"phone": "29123456", "pin": "0308"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    return payload["token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}
