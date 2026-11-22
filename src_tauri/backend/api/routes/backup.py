"""Authenticated manual SQLite backup endpoints."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import BACKUP_DIR, DATABASE_URL
from database.connection import Database
from core.disaster_recovery import BackupConfig, DatabaseBackupManager

router = APIRouter(prefix="/backup", tags=["backup"])

class BackupRequest(BaseModel):
    description: str = Field(default="manual", min_length=1, max_length=80)

@router.post("/create")
def create_manual_backup(request: BackupRequest):
    """Create a consistent, integrity-checked SQLite backup."""
    db = Database(DATABASE_URL)
    try:
        db.init_db()
        manager = DatabaseBackupManager(BackupConfig(backup_dir=BACKUP_DIR), db)
        path = manager.create_backup(request.description)
        metadata = manager.validate_backup(path)
        return {
            "status": "created",
            "filename": path.name,
            "metadata": metadata,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Backup creation failed: {exc}") from exc
    finally:
        db.close()

@router.get("/list")
def list_backups():
    """List managed backups without exposing arbitrary filesystem paths."""
    entries = []
    for path in sorted(BACKUP_DIR.glob("*.db*"), key=lambda item: item.stat().st_mtime, reverse=True):
        if path.name.endswith(".json") or path.name.endswith(".tmp"):
            continue
        metadata_path = Path(str(path) + ".json")
        metadata = None
        if metadata_path.is_file():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metadata = {"integrity_check": "metadata_unreadable"}
        entries.append({
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "metadata": metadata,
        })
    return {"backups": entries}
