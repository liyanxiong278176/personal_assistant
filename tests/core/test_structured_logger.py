# tests/core/test_structured_logger.py
import json
import logging
import pytest
from app.core.observability.logger import StructuredLogger, get_logger, StructuredFormatter


def test_structured_logger_format():
    """Test structured logger outputs valid JSON"""
    import io

    # Create a logger with a custom handler to capture output
    logger_instance = logging.getLogger("test_component_format")
    logger_instance.handlers.clear()  # Clear any existing handlers
    logger_instance.setLevel(logging.DEBUG)

    # Create a string buffer and handler
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(StructuredFormatter())
    logger_instance.addHandler(handler)
    logger_instance.propagate = False

    # Create our StructuredLogger wrapper
    logger = StructuredLogger("test_component_format")
    # Override the internal logger with our test logger
    logger._logger = logger_instance

    logger.info("test_message", key="value", count=42)

    output = buffer.getvalue()

    # Verify JSON format (pure JSON output, no prefix)
    log_entry = json.loads(output.strip())
    assert log_entry["level"] == "INFO"
    assert log_entry["component"] == "test_component_format"
    assert log_entry["message"] == "test_message"
    assert log_entry["key"] == "value"
    assert log_entry["count"] == 42


def test_get_logger_singleton():
    """Test get_logger returns same instance for same name"""
    logger1 = get_logger("test")
    logger2 = get_logger("test")
    assert logger1 is logger2

    logger3 = get_logger("other")
    assert logger1 is not logger3


def test_structured_logger_all_levels():
    """Test all log levels work correctly"""
    import io

    logger_instance = logging.getLogger("test_levels")
    logger_instance.handlers.clear()
    logger_instance.setLevel(logging.DEBUG)

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(StructuredFormatter())
    logger_instance.addHandler(handler)
    logger_instance.propagate = False

    logger = StructuredLogger("test_levels")
    logger._logger = logger_instance

    # Test each level
    logger.debug("debug_msg")
    logger.info("info_msg")
    logger.warning("warning_msg")
    logger.error("error_msg")
    logger.critical("critical_msg")

    lines = buffer.getvalue().strip().split("\n")
    assert len(lines) == 5

    levels = [json.loads(line)["level"] for line in lines]
    assert levels == ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
