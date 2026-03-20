"""Test flake8 compliance for porter_lidar_processor."""

# Copyright 2026 VirtusCo. All rights reserved.

from ament_flake8.main import main_with_errors
import pytest


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8():
    """Check flake8 compliance."""
    rc, errors = main_with_errors(argv=[])
    assert rc == 0, \
        'Found %d code style errors / warnings:\n' % len(errors) + \
        '\n'.join(errors)
