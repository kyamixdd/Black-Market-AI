"""Tests for structured diagnostic logging and redaction."""
import json
import logging

from core.observability import JsonLogFormatter, log_event, redact_sensitive_text


def test_log_formatter_outputs_structured_fields_and_redacts_secrets():
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1,
        "request failed authorization: Bearer abc123 api_key=secret-value",
        (), None,
    )
    record.event = "api_request"
    record.request_id = "req-1"
    record.method = "GET"
    record.path = "/api/markets"
    record.status_code = 503
    record.duration_ms = 12.5
    formatted = JsonLogFormatter().format(record)
    payload = json.loads(formatted)
    assert payload["event"] == "api_request"
    assert payload["request_id"] == "req-1"
    assert payload["status_code"] == 503
    assert "abc123" not in formatted
    assert "secret-value" not in formatted
    assert "[REDACTED]" in formatted


def test_redactor_covers_token_password_and_secret_assignments():
    result = redact_sensitive_text("token=xyz password=hunter secret=private")
    assert "xyz" not in result and "hunter" not in result and "private" not in result


def test_log_event_does_not_emit_sensitive_fields(caplog):
    logger = logging.getLogger("observability-test")
    with caplog.at_level(logging.INFO):
        log_event(logger, logging.INFO, "paper_order", symbol="BTCUSDT", api_key="do-not-log")
    assert "paper_order" in caplog.text
    assert "BTCUSDT" in caplog.text
    assert "do-not-log" not in caplog.text



def test_function_trace_can_be_enabled_and_disabled_without_crashing(caplog):
    from core.observability import function_trace_enabled, set_function_trace_enabled

    assert function_trace_enabled() is False
    with caplog.at_level(logging.INFO):
        assert set_function_trace_enabled(True) is True
        assert function_trace_enabled() is True
        assert set_function_trace_enabled(False) is False
    assert "python_function_trace_changed" in caplog.text
    assert function_trace_enabled() is False



def test_log_event_redacts_secrets_in_structured_fields(caplog):
    logger = logging.getLogger("observability-field-redaction")
    with caplog.at_level(logging.INFO):
        log_event(logger, logging.INFO, "diagnostic", detail="token=private api_key=hidden")
    record = next(record for record in caplog.records if record.name == logger.name)
    assert record.detail == "token=[REDACTED] api_key=[REDACTED]"
    formatted = JsonLogFormatter().format(record)
    assert "private" not in formatted
    assert "hidden" not in formatted
    assert "[REDACTED]" in formatted
