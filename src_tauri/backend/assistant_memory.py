"""Validation and bounded retrieval helpers for persistent assistant memory."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Any

MEMORY_TYPES = {"working", "episodic", "semantic", "procedural"}
_SOURCE = {"user_explicit", "assistant_summary", "validated_workflow"}
_SECRET_PATTERNS = (
    re.compile(r"(?i)\\b(api[_ -]?key|secret|password|token|private[_ -]?key)\\s*[:=]\\s*\\S+"),
    re.compile(r"(?i)\\bBearer\\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"(?i)\\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\\b"),
)


class MemoryValidationError(ValueError):
    """Memory payload failed privacy or schema validation."""


def validate_memory_content(content: str) -> str:
    if not isinstance(content, str):
        raise MemoryValidationError("Memory content must be text.")
    normalized = " ".join(content.strip().split())
    if not 3 <= len(normalized) <= 1200:
        raise MemoryValidationError("Memory content must contain 3 to 1200 characters.")
    if any(pattern.search(normalized) for pattern in _SECRET_PATTERNS):
        raise MemoryValidationError("Memory content appears to contain a credential or secret.")
    return normalized


def build_memory_record(*, owner_key: str, memory_type: str, content: str,
                        source: str = "user_explicit", importance: float = 0.5,
                        confidence: float = 1.0, tags: list[str] | None = None,
                        ttl_days: int | None = None, memory_id: str | None = None) -> dict[str, Any]:
    if memory_type not in MEMORY_TYPES:
        raise MemoryValidationError("Unsupported memory type.")
    if source not in _SOURCE:
        raise MemoryValidationError("Unsupported memory source.")
    if not 0.0 <= float(importance) <= 1.0 or not 0.0 <= float(confidence) <= 1.0:
        raise MemoryValidationError("Importance and confidence must be between 0 and 1.")
    if ttl_days is not None and not 1 <= int(ttl_days) <= 365:
        raise MemoryValidationError("Memory expiration must be between 1 and 365 days.")
    safe_tags = []
    for tag in (tags or [])[:12]:
        if not isinstance(tag, str):
            continue
        value = " ".join(tag.strip().lower().split())
        if value and len(value) <= 32 and re.fullmatch(r"[a-z0-9 _-]+", value):
            safe_tags.append(value)
    expires_at = datetime.now(timezone.utc) + timedelta(days=int(ttl_days)) if ttl_days else None
    if memory_type == "working" and expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    return {
        "memory_id": memory_id or uuid4().hex,
        "owner_key": owner_key,
        "memory_type": memory_type,
        "content": validate_memory_content(content),
        "source": source,
        "importance": float(importance),
        "confidence": float(confidence),
        "tags": list(dict.fromkeys(safe_tags)),
        "expires_at": expires_at,
    }


def retrieve_relevant_memories(repository, owner_key: str, query: str, *, limit: int = 6) -> list[dict[str, Any]]:
    """Score owner-scoped candidates using request overlap, recency, confidence and importance."""
    candidates = repository.retrieve_assistant_memories(owner_key, limit=20)
    terms = set(re.findall(r"[a-z0-9]{2,}", query.lower()))
    scored = []
    now = datetime.now(timezone.utc)
    for item in candidates:
        content_terms = set(re.findall(r"[a-z0-9]{2,}", item["content"].lower()))
        tag_terms = set(re.findall(r"[a-z0-9]{2,}", " ".join(item.get("tags", [])).lower()))
        overlap = len(terms & (content_terms | tag_terms)) / max(1, len(terms))
        updated = item.get("updated_at")
        try:
            timestamp = datetime.fromisoformat(updated) if updated else now
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now - timestamp).total_seconds() / 86400)
        except (ValueError, TypeError):
            age_days = 365.0
        recency = 1.0 / (1.0 + age_days / 30.0)
        score = 0.55 * overlap + 0.25 * float(item["importance"]) + 0.15 * float(item["confidence"]) + 0.05 * recency
        item["relevance_score"] = round(score, 4)
        scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for score, item in scored[:max(1, min(int(limit), 10))] if score > 0.05]
