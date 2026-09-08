from __future__ import annotations

import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_addoption(parser):
    parser.addoption("--browser-tests", action="store_true", help="run the Chromium UI tests")


def pytest_configure(config):
    config.addinivalue_line("markers", "browser: requires Playwright and installed Chromium")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--browser-tests"):
        skip = pytest.mark.skip(reason="enable with --browser-tests")
        for item in items:
            if "browser" in item.keywords:
                item.add_marker(skip)
