"""Tests for authenticated backup route behavior."""
import json
from pathlib import Path

from fastapi import FastAPI
from starlette.requests import Request

from src_tauri.backend.api.routes import backup as backup_routes

def test_manual_backup_endpoint_returns_manifest_and_closes_database(monkeypatch, tmp_path):
    calls = []
    class FakeDatabase:
        pass
    class FakeManager:
        def __init__(self, config, db):
            calls.append(("manager", config.backup_dir))
            calls.append(("database", db))
        def create_backup(self, description):
            calls.append(("created", description))
            return tmp_path / "safe_backup.db.gz"
        def validate_backup(self, path):
            return {"backup_file": path.name, "integrity_check": "ok"}
    monkeypatch.setattr(backup_routes, "DatabaseBackupManager", FakeManager)
    monkeypatch.setattr(backup_routes, "BACKUP_DIR", tmp_path)
    app = FastAPI()
    app.state.database = FakeDatabase()
    request = Request({
        "type": "http", "method": "POST", "path": "/api/backup/create",
        "headers": [], "query_string": b"", "server": ("test", 80),
        "client": ("127.0.0.1", 1234), "scheme": "http",
        "http_version": "1.1", "root_path": "", "app": app,
    })

    response = backup_routes.create_manual_backup(
        backup_routes.BackupRequest(description="before upgrade"), request,
    )
    assert response["status"] == "created"
    assert response["metadata"]["integrity_check"] == "ok"
    assert ("created", "before upgrade") in calls
    assert ("database", app.state.database) in calls

def test_backup_listing_does_not_include_manifest_as_backup(monkeypatch, tmp_path):
    backup = tmp_path / "db_20261122_manual.db.gz"
    backup.write_bytes(b"test")
    Path(str(backup) + ".json").write_text(json.dumps({"integrity_check": "ok"}), encoding="utf-8")
    monkeypatch.setattr(backup_routes, "BACKUP_DIR", tmp_path)
    result = backup_routes.list_backups()
    assert [item["filename"] for item in result["backups"]] == [backup.name]
