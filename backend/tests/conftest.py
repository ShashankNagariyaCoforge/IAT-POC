"""Shared test fixtures and configuration."""

import sys
import os

# Add backend root to path so imports work when running from backend/tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
