# backend/tests/test_interview_monitor/conftest.py
import sys
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

import pytest

@pytest.fixture
def results_dir():
    return Path(__file__).parent.parent.parent / "results"

@pytest.fixture
def timestamp():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
