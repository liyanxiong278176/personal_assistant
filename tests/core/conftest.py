"""pytest configuration for tests/core directory."""

import sys
from pathlib import Path

# Add backend directory to path for app imports
backend_dir = Path(__file__).parent.parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
