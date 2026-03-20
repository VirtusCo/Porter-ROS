"""Hardware-in-the-loop test configuration.

Adds the --hil command-line option to pytest. HIL tests are skipped
by default (no hardware in CI). Pass --hil to run them on the physical robot.

Usage:
    pytest tests/hil/ --hil -v
"""

import pytest


def pytest_addoption(parser):
    """Add --hil option to pytest CLI."""
    parser.addoption(
        "--hil",
        action="store_true",
        default=False,
        help="Run hardware-in-the-loop tests (requires physical robot)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip HIL-marked tests unless --hil flag is provided."""
    if not config.getoption("--hil"):
        skip_hil = pytest.mark.skip(
            reason="Need --hil option to run hardware-in-the-loop tests"
        )
        for item in items:
            if "hil" in item.keywords:
                item.add_marker(skip_hil)
