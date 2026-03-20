"""Common test fixtures for all VTI test layers.

Provides shared pytest fixtures used across unit, integration, system,
and hardware-in-the-loop test suites.
"""

import pytest
import os


@pytest.fixture
def workspace_root():
    """Returns the porter_robot workspace root path."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def virtus_msgs_available():
    """Check if virtus_msgs package is available (built).

    Skips the test if the virtus_msgs package has not been built yet.
    Build with: colcon build --packages-select virtus_msgs
    """
    try:
        from virtus_msgs.msg import SensorFusion  # noqa: F401
        return True
    except ImportError:
        pytest.skip(
            "virtus_msgs not built — run "
            "'colcon build --packages-select virtus_msgs' first"
        )


@pytest.fixture
def ros2_available():
    """Check if ROS 2 Python libraries are importable."""
    try:
        import rclpy  # noqa: F401
        return True
    except ImportError:
        pytest.skip("ROS 2 not available — source /opt/ros/jazzy/setup.bash first")


@pytest.fixture
def test_data_dir():
    """Returns path to test data directory (bags/, scenarios/)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def bag_dir():
    """Returns path to bag file directory."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bags')
