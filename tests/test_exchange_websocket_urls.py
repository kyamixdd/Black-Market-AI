"""Regression tests for Binance raw and combined WebSocket endpoints."""
from exchange.websocket_manager import FUTURES_WS_URL, SPOT_WS_URL, _stream_url


def test_spot_single_stream_uses_raw_stream_endpoint():
    assert _stream_url(SPOT_WS_URL, ["btcusdt@aggTrade"]) == (
        "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"
    )


def test_futures_combined_stream_uses_combined_stream_endpoint():
    assert _stream_url(FUTURES_WS_URL, ["btcusdt@aggTrade", "ethusdt@markPrice"]) == (
        "wss://fstream.binance.com/stream?streams=btcusdt@aggTrade/ethusdt@markPrice"
    )
