import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_LOGGING_RESERVED = frozenset({
    "name", "msg", "args", "created", "relativeCreated", "thread", "threadName",
    "msecs", "process", "processName", "filename", "funcName", "levelname",
    "levelno", "lineno", "module", "pathname", "exc_info", "exc_text",
    "stack_info", "getMessage", "message",
})


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, val in record.__dict__.items():
            if key in _LOGGING_RESERVED:
                continue
            try:
                json.dumps(val)
                log[key] = val
            except (TypeError, ValueError):
                log[key] = str(val)

        if record.exc_info and not record.exc_text:
            log["exception"] = self.formatException(record.exc_info)

        return json.dumps(log, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    logging.getLogger("sqlalchemy.engine").setLevel("WARNING")
    logging.getLogger("httpx").setLevel("WARNING")
    logging.getLogger("httpcore").setLevel("WARNING")
