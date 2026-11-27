"""Authenticated manual SQLite backup endpoints."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from config import BACKUP_DIR
from core.disaster_recovery import BackupConfig, DatabaseBackupManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/backup", tags=["backup"])

class BackupRequest(BaseModel):
    description: str = Field(default="manual", min_length=1, max_length=80)

@router.post("/create")
def create_manual_backup(payload: BackupRequest, request: Request):
    """Create a consistent, integrity-checked SQLite backup."""
    db = getattr(request.app.state, "database", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Application database is not ready.")
    try:
        manager = DatabaseBackupManager(BackupConfig(backup_dir=BACKUP_DIR), db)
        path = manager.create_backup(payload.description)
        metadata = manager.validate_backup(path)
        return {
            "status": "created",
            "filename": path.name,
            "metadata": metadata,
        }
    except Exception as exc:
        logger.exception("Manual backup creation failed")
        raise HTTPException(status_code=500, detail="Backup creation failed; inspect backend logs.") from exc

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
