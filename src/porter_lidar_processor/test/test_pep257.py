"""Test pep257 compliance for porter_lidar_processor."""

# Copyright 2026 VirtusCo. All rights reserved.

from ament_pep257.main import main
import pytest


@pytest.mark.linter
@pytest.mark.pep257
def test_pep257():
    """Check pep257 compliance."""
    rc = main(argv=['--add-ignore', 'D100,D104,D213,D406,D407,D413'])
    assert rc == 0, 'Found code style errors / warnings'
