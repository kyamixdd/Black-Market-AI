from notifications.telegram_client import TelegramClient


def test_failed_delivery_does_not_suppress_retry(monkeypatch):
    client = TelegramClient(token="123:test", chat_id="123")
    calls = {"count": 0}

    class FakeBot:
        async def send_message(self, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("temporary Telegram outage")

    async def fake_ensure_bot():
        client._bot = FakeBot()
        return True

    monkeypatch.setattr(client, "_ensure_bot", fake_ensure_bot)

    import asyncio
    assert asyncio.run(client.send_message("retry me")) is False
    assert asyncio.run(client.send_message("retry me")) is True
    assert calls["count"] == 2


def test_successful_delivery_is_deduplicated(monkeypatch):
    client = TelegramClient(token="123:test", chat_id="123")
    calls = {"count": 0}

    class FakeBot:
        async def send_message(self, **kwargs):
            calls["count"] += 1

    async def fake_ensure_bot():
        client._bot = FakeBot()
        return True

    monkeypatch.setattr(client, "_ensure_bot", fake_ensure_bot)

    import asyncio
    assert asyncio.run(client.send_message("once")) is True
    assert asyncio.run(client.send_message("once")) is False
    assert calls["count"] == 1
