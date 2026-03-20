"""Launch file for the Porter Orchestrator — state machine and health monitor.

Launches both the ``porter_state_machine`` and ``lidar_health_monitor`` nodes
with parameters loaded from the ``orchestrator_params.yaml`` config file.

Usage:
    ros2 launch porter_orchestrator orchestrator_launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate the launch description for the orchestrator nodes."""
    pkg_dir = get_package_share_directory('porter_orchestrator')
    default_params = os.path.join(pkg_dir, 'config', 'orchestrator_params.yaml')

    params_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_params,
        description='Path to the orchestrator parameters YAML file')

    params_file = LaunchConfiguration('params_file')

    state_machine_node = Node(
        package='porter_orchestrator',
        executable='state_machine',
        name='porter_state_machine',
        parameters=[params_file],
        output='screen',
    )

    health_monitor_node = Node(
        package='porter_orchestrator',
        executable='health_monitor',
        name='lidar_health_monitor',
        parameters=[params_file],
        output='screen',
    )

    return LaunchDescription([
        params_arg,
        state_machine_node,
        health_monitor_node,
    ])
