"""Make the repository root importable for every test module.

Without this, ``import agent.router`` fails when pytest is invoked from the
repository root, because pytest only puts each test file's own directory on
``sys.path``.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
