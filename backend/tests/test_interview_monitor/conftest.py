# backend/tests/test_interview_monitor/conftest.py
import pytest
from pathlib import Path

@pytest.fixture
def results_dir():
    return Path(__file__).parent.parent.parent / "results"

@pytest.fixture
def timestamp():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
