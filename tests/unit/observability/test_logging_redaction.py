"""Tests that sensitive values never appear in log output."""



from src.pages_to_audio.observability.logging import _redact_dict


def test_redacts_api_key() -> None:
    obj = {"api_key": "sk-secret123", "data": "safe"}
    _redact_dict(obj)
    assert obj["api_key"] == "***REDACTED***"
    assert obj["data"] == "safe"


def test_redacts_password() -> None:
    obj = {"password": "hunter2", "name": "alice"}
    _redact_dict(obj)
    assert obj["password"] == "***REDACTED***"
    assert obj["name"] == "alice"


def test_redacts_bearer_token() -> None:
    obj = {"authorization": "Bearer abc123"}
    _redact_dict(obj)
    assert obj["authorization"] == "***REDACTED***"


def test_redacts_nested_secrets() -> None:
    obj = {"auth": {"secret": "hidden", "user": "bob"}}
    _redact_dict(obj)
    assert obj["auth"]["secret"] == "***REDACTED***"
    assert obj["auth"]["user"] == "bob"


def test_redacts_signed_url() -> None:
    obj = {
        "signed_url": "https://storage.example.com/file.jpg?token=abc&Signature=xyz",
        "path": "/safe/path",
    }
    _redact_dict(obj)
    # signed_url key itself is flagged as sensitive
    assert obj["signed_url"] == "***REDACTED***"


def test_redacts_gateway_token() -> None:
    obj = {"gateway_token": "tok-987"}
    _redact_dict(obj)
    assert obj["gateway_token"] == "***REDACTED***"


def test_safe_keys_unchanged() -> None:
    obj = {"session_id": "abc123", "question_id": "q1", "duration_ms": 42}
    _redact_dict(obj)
    assert obj["session_id"] == "abc123"
    assert obj["question_id"] == "q1"
    assert obj["duration_ms"] == 42
