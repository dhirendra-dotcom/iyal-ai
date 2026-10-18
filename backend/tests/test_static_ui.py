from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.static_ui import mount_landing_site, mount_local_ui


def test_static_ui_serves_local_assets_and_preserves_api(tmp_path):
    (tmp_path / "index.html").write_text('<script src="app.js"></script>', encoding="utf-8")
    (tmp_path / "app.js").write_text('console.log("local")', encoding="utf-8")
    app = FastAPI()

    @app.get("/")
    def root():
        return {"service": "api"}

    assert mount_local_ui(app, tmp_path)
    with TestClient(app) as client:
        assert client.get("/").json() == {"service": "api"}
        assert client.get("/app").url.path == "/app/"
        assert client.get("/app/").status_code == 200
        assert client.get("/app/app.js").text == 'console.log("local")'
        assert client.get("/app/missing.js").status_code == 404
        assert client.get("/app/%2e%2e/secret.txt").status_code == 404


def test_landing_site_at_root_does_not_shadow_api_or_app(tmp_path):
    ui = tmp_path / "ui"
    site = tmp_path / "site"
    ui.mkdir()
    site.mkdir()
    (ui / "index.html").write_text("chat-ui", encoding="utf-8")
    (site / "index.html").write_text("landing", encoding="utf-8")
    (site / "style.css").write_text("body{}", encoding="utf-8")
    (site / "hero.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBP")
    app = FastAPI()
    assert mount_local_ui(app, ui)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/sessions/{session_id}/thing")
    def thing(session_id: str):
        return {"session_id": session_id}

    assert mount_landing_site(app, site)
    with TestClient(app) as client:
        assert client.get("/").text == "landing"
        assert client.get("/style.css").text == "body{}"
        assert client.get("/hero.webp").headers["content-type"] == "image/webp"
        assert client.get("/app/").text == "chat-ui"
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/sessions/s1/thing").json() == {"session_id": "s1"}
        assert client.get("/missing.js").status_code == 404
        assert client.get("/%2e%2e/secret.txt").status_code == 404


def test_missing_landing_site_returns_false(tmp_path):
    app = FastAPI()
    assert mount_landing_site(app, tmp_path) is False


def test_missing_optional_ui_does_not_break_backend(tmp_path):
    app = FastAPI()
    assert mount_local_ui(app, tmp_path) is False
    assert all(getattr(route, "name", None) != "local-ui" for route in app.routes)
