"""Put the repository root on ``sys.path`` so tests can ``import agent.*``.

Works with or without a ``pyproject.toml`` (KARA-6 owns that file on its own
branch), so this suite runs standalone: ``pytest tests/test_llm_*.py``.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
