"""Tests for authenticated backup route behavior."""
import json
from pathlib import Path

from src_tauri.backend.api.routes import backup as backup_routes

def test_manual_backup_endpoint_returns_manifest_and_closes_database(monkeypatch, tmp_path):
    calls = []
    class FakeDatabase:
        def __init__(self, url): calls.append(("init", url))
        def init_db(self): calls.append(("initialized",))
        def close(self): calls.append(("closed",))
    class FakeManager:
        def __init__(self, config, db): calls.append(("manager", config.backup_dir))
        def create_backup(self, description):
            calls.append(("created", description))
            return tmp_path / "safe_backup.db.gz"
        def validate_backup(self, path):
            return {"backup_file": path.name, "integrity_check": "ok"}
    monkeypatch.setattr(backup_routes, "Database", FakeDatabase)
    monkeypatch.setattr(backup_routes, "DatabaseBackupManager", FakeManager)
    monkeypatch.setattr(backup_routes, "DATABASE_URL", "sqlite:///unit.db")
    monkeypatch.setattr(backup_routes, "BACKUP_DIR", tmp_path)

    response = backup_routes.create_manual_backup(backup_routes.BackupRequest(description="before upgrade"))
    assert response["status"] == "created"
    assert response["metadata"]["integrity_check"] == "ok"
    assert ("created", "before upgrade") in calls
    assert ("closed",) in calls

def test_backup_listing_does_not_include_manifest_as_backup(monkeypatch, tmp_path):
    backup = tmp_path / "db_20261122_manual.db.gz"
    backup.write_bytes(b"test")
    Path(str(backup) + ".json").write_text(json.dumps({"integrity_check": "ok"}), encoding="utf-8")
    monkeypatch.setattr(backup_routes, "BACKUP_DIR", tmp_path)
    result = backup_routes.list_backups()
    assert [item["filename"] for item in result["backups"]] == [backup.name]
