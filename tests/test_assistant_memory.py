"""Persistent assistant memory validation, isolation, expiry, and retrieval tests."""
from datetime import datetime, timedelta, timezone

import pytest

from database.connection import Database
from database.repositories import Repository
from src_tauri.backend.assistant_memory import (
    MemoryValidationError,
    build_memory_record,
    retrieve_relevant_memories,
)


@pytest.fixture
def memory_repo(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'memory.db'}")
    db.init_db()
    yield Repository(db.session_maker())
    db.close()


def test_memory_persists_and_updates_version(memory_repo):
    record = build_memory_record(
        owner_key="owner-a", memory_type="semantic",
        content="I prefer detailed market explanations", tags=["style", "market"],
    )
    saved = memory_repo.save_assistant_memory(record)
    assert saved["version"] == 1
    fetched = memory_repo.get_assistant_memory(record["memory_id"], "owner-a")
    assert fetched["content"] == record["content"]

    updated = memory_repo.save_assistant_memory({
        **record, "content": "I prefer concise market explanations",
    })
    assert updated["version"] == 2
    assert memory_repo.get_assistant_memory(record["memory_id"], "owner-a")["content"].startswith("I prefer concise")


def test_memory_isolated_by_owner_and_delete_requires_owner(memory_repo):
    record = build_memory_record(
        owner_key="owner-a", memory_type="episodic",
        content="Completed a BTC market analysis workflow",
    )
    memory_repo.save_assistant_memory(record)
    assert memory_repo.get_assistant_memory(record["memory_id"], "owner-b") is None
    assert memory_repo.delete_assistant_memory(record["memory_id"], "owner-b") is False
    assert memory_repo.get_assistant_memory(record["memory_id"], "owner-a") is not None
    assert memory_repo.delete_assistant_memory(record["memory_id"], "owner-a") is True


def test_memory_expiration_is_enforced_and_cleanup_is_idempotent(memory_repo):
    expired = build_memory_record(
        owner_key="owner-a", memory_type="working",
        content="Current BTC analysis context", ttl_days=1,
    )
    expired["expires_at"] = datetime.now(timezone.utc) - timedelta(days=1)
    memory_repo.save_assistant_memory(expired)
    assert memory_repo.delete_expired_assistant_memories() == 1
    assert memory_repo.delete_expired_assistant_memories() == 0
    assert memory_repo.get_assistant_memory(expired["memory_id"], "owner-a") is None


def test_retrieval_is_bounded_and_query_relevant(memory_repo):
    relevant = build_memory_record(
        owner_key="owner-a", memory_type="semantic",
        content="I prefer detailed BTC market explanations", importance=0.9,
    )
    unrelated = build_memory_record(
        owner_key="owner-a", memory_type="semantic",
        content="My favorite color is charcoal gray", importance=0.9,
    )
    memory_repo.save_assistant_memory(relevant)
    memory_repo.save_assistant_memory(unrelated)
    result = retrieve_relevant_memories(memory_repo, "owner-a", "Explain BTC market", limit=1)
    assert len(result) == 1
    assert result[0]["memory_id"] == relevant["memory_id"]


@pytest.mark.parametrize("content", [
    "api_key=abcdef123456789",
    "Bearer abcdefghijklmnop",
    "password: secret-value",
])
def test_memory_rejects_credentials(content):
    with pytest.raises(MemoryValidationError):
        build_memory_record(owner_key="owner-a", memory_type="semantic", content=content)


def test_memory_rejects_invalid_type_and_ttl():
    with pytest.raises(MemoryValidationError):
        build_memory_record(owner_key="owner-a", memory_type="unknown", content="Valid memory content")
    with pytest.raises(MemoryValidationError):
        build_memory_record(owner_key="owner-a", memory_type="working", content="Valid memory content", ttl_days=500)


def test_memory_deduplicates_same_owner_type_and_content(memory_repo):
    first = build_memory_record(
        owner_key="owner-a", memory_type="semantic",
        content="I prefer detailed market explanations",
    )
    second = build_memory_record(
        owner_key="owner-a", memory_type="semantic",
        content="i prefer detailed market explanations",
    )
    saved_first = memory_repo.save_assistant_memory(first)
    saved_second = memory_repo.save_assistant_memory(second)
    assert saved_first["memory_id"] == saved_second["memory_id"]
    assert saved_second["version"] == 2
    assert len(memory_repo.retrieve_assistant_memories("owner-a", limit=20)) == 1


@pytest.mark.asyncio
async def test_assistant_remember_and_recall_commands_are_explicit(monkeypatch, tmp_path):
    from starlette.requests import Request
    from src_tauri.backend.api.routes import assistant as assistant_route
    from src_tauri.backend.api.routes.assistant import AssistantQuery

    db = Database(f"sqlite:///{tmp_path / 'api-memory.db'}")
    db.init_db()
    repository = Repository(db.session_maker())
    monkeypatch.setattr(assistant_route, "_memory_repository", lambda: repository)

    def make_request(token):
        return Request({
            "type": "http", "method": "POST", "path": "/api/assistant/query",
            "headers": [(b"authorization", ("Bearer " + token).encode())],
            "query_string": b"", "server": ("test", 80), "client": ("127.0.0.1", 1234),
            "scheme": "http", "http_version": "1.1", "root_path": "",
        })

    saved = await assistant_route.query_assistant(
        make_request("local-token-a"),
        AssistantQuery(query="Remember that I prefer detailed explanations"),
    )
    assert saved["status"] == "memory_saved"
    assert saved["memory"]["content"] == "I prefer detailed explanations"

    recalled = await assistant_route.query_assistant(
        make_request("local-token-a"),
        AssistantQuery(query="What do you remember about explanations?"),
    )
    assert recalled["status"] == "memory_retrieved"
    assert "detailed explanations" in recalled["answer"]

    other_user = await assistant_route.query_assistant(
        make_request("local-token-b"),
        AssistantQuery(query="What do you remember about explanations?"),
    )
    assert other_user["status"] == "memory_retrieved"
    assert other_user["memories"] == []
    db.close()
