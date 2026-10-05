"""Shared test setup: make `bsequant` and `strategies` importable."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bsequant as bq  # noqa: E402


@pytest.fixture(scope="session")
def bch():
    return bq.load("BCH-1d")
