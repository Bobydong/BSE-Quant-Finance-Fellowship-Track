"""Headless smoke test: every strategy renders in the app without crashing."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_every_strategy_renders():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    assert not at.exception
    options = at.sidebar.selectbox[1].options
    assert any(o.startswith("Mean reversion") for o in options)
    for option in options:
        at.sidebar.selectbox[1].set_value(option).run()
        assert not at.exception, option
        assert not at.error, option
        assert [t.label for t in at.tabs] == [
            "Performance", "Risk", "Costs", "Year by year", "Trade log", "Data"]
