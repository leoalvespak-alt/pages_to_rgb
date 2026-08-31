from __future__ import annotations

import contextvars
import re
from typing import Any

import structlog

_SENSITIVE_KEYS = re.compile(
    r"(api[_-]?key|password|secret|token|bearer|authorization|credential"
    r"|signed.?url|gateway.?token|hmac|dsn|private.?key)",
    re.IGNORECASE,
)

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_session_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="")
_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")


def bind_log_context(
    *,
    request_id: str = "",
    session_id: str = "",
    trace_id: str = "",
) -> None:
    if request_id:
        _request_id_var.set(request_id)
    if session_id:
        _session_id_var.set(session_id)
    if trace_id:
        _trace_id_var.set(trace_id)


def _add_context_vars(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    rid = _request_id_var.get()
    sid = _session_id_var.get()
    tid = _trace_id_var.get()
    if rid:
        event_dict["request_id"] = rid
    if sid:
        event_dict["session_id"] = sid
    if tid:
        event_dict["trace_id"] = tid
    return event_dict


def _redact_sensitive(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    _redact_dict(event_dict)
    return event_dict


def _redact_dict(obj: Any) -> None:
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            if _SENSITIVE_KEYS.search(str(k)):
                obj[k] = "***REDACTED***"
            else:
                val = obj[k]
                if isinstance(val, str) and "?" in val and ("token=" in val or "Signature=" in val):
                    # Signed URL — keep host+path only
                    obj[k] = val.split("?")[0] + "?***"
                else:
                    _redact_dict(val)
    elif isinstance(obj, list):
        for item in obj:
            _redact_dict(item)


def _add_logger_name(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    logger_name = getattr(logger, "name", None)
    if logger_name:
        event_dict["logger"] = logger_name
    return event_dict


def configure_logging(log_level: str = "INFO", service_name: str = "pages-to-audio") -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_context_vars,
            _redact_sensitive,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _add_logger_name,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(__import__("logging"), log_level, 20)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(name: str = "pages-to-audio") -> structlog.BoundLogger:
    return structlog.get_logger(name)
