"""
Observability Module - Structured Logging & Context Management.
Produces JSON logs compatible with Datadog/ELK/CloudWatch.
"""

import json
import logging
import threading
from datetime import datetime

# Thread-local storage for context (Session ID, User ID)
_log_context = threading.local()


def set_log_context(session_id: str, user_id: str | None = None, request_id: str | None = None):
    """Sets the context for the current execution thread."""
    _log_context.session_id = session_id
    _log_context.user_id = user_id or "anon"
    _log_context.request_id = request_id or "n/a"


def get_log_context() -> dict[str, str]:
    return {
        "session_id": getattr(_log_context, "session_id", "unknown"),
        "user_id": getattr(_log_context, "user_id", "unknown"),
        "request_id": getattr(_log_context, "request_id", "unknown"),
    }


class JSONFormatter(logging.Formatter):
    """Formats log records as a JSON string."""

    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            # Context injection
            **get_log_context(),
        }

        # Handle exceptions
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # Handle extra fields passed via logging.info(..., extra={...})
        if hasattr(record, "props"):
            log_record.update(record.props)

        return json.dumps(log_record)


def setup_observability(log_level=logging.INFO):
    """Configures the root logger to use JSON formatting."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console Handler (Standard Output)
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)

    # Optional: File Handler for persistence
    # file_handler = logging.FileHandler("app.json.log")
    # file_handler.setFormatter(JSONFormatter())
    # root_logger.addHandler(file_handler)
