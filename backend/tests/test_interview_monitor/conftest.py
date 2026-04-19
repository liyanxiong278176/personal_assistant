# backend/tests/test_interview_monitor/conftest.py
import pytest
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

@pytest.fixture
def results_dir():
    return Path(__file__).parent.parent.parent / "results"

@pytest.fixture
def timestamp():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
