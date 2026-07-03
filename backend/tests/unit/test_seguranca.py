
from app.core.logging import JsonFormatter, setup_logging
from app.core.middleware import get_client_ip


def test_json_formatter_output():
    import logging

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    data = __import__("json").loads(output)
    assert data["level"] == "INFO"
    assert data["message"] == "hello"
    assert data["logger"] == "test"
    assert "timestamp" in data


def test_json_formatter_with_extras():
    import logging

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="event",
        args=(),
        exc_info=None,
    )
    record.event_type = "auth.login.success"
    record.usuario_id = "user-123"
    output = formatter.format(record)
    data = __import__("json").loads(output)
    assert data["event_type"] == "auth.login.success"
    assert data["usuario_id"] == "user-123"


def test_json_formatter_with_exception():
    import logging

    formatter = JsonFormatter()
    try:
        raise ValueError("test error")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="failed",
        args=(),
        exc_info=exc_info,
    )
    output = formatter.format(record)
    data = __import__("json").loads(output)
    assert "exception" in data
    assert "ValueError" in data["exception"]


def test_setup_logging():
    setup_logging("WARNING")
    import logging

    root = logging.getLogger()
    assert root.level == logging.WARNING
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_get_client_ip_v4():
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [(b"x-forwarded-for", b"1.2.3.4")],
        "server": ("test", 80),
    }
    request = Request(scope)
    assert get_client_ip(request) == "1.2.3.4"
