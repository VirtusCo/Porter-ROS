"""Launch file for the Porter LIDAR Processor node.

Launches the processor_node with parameters from processor_params.yaml.
Can be included in a larger bringup launch or run standalone.

Usage:
    ros2 launch porter_lidar_processor processor_launch.py
    ros2 launch porter_lidar_processor processor_launch.py \
        filters_enabled:=false
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for the processor node."""
    pkg_dir = get_package_share_directory('porter_lidar_processor')
    params_file = os.path.join(pkg_dir, 'config', 'processor_params.yaml')

    return LaunchDescription([
        # ── Launch arguments ──────────────────────────────────────────────
        DeclareLaunchArgument(
            'params_file',
            default_value=params_file,
            description='Path to processor parameters YAML file',
        ),

        DeclareLaunchArgument(
            'filters_enabled',
            default_value='true',
            description='Enable/disable the filter pipeline',
        ),

        # ── Processor node ────────────────────────────────────────────────
        Node(
            package='porter_lidar_processor',
            executable='processor_node',
            name='lidar_processor',
            output='screen',
            parameters=[
                LaunchConfiguration('params_file'),
                {
                    'filters_enabled':
                        LaunchConfiguration('filters_enabled'),
                },
            ],
            remappings=[
                ('scan', '/scan'),
                ('scan/processed', '/scan/processed'),
            ],
        ),
    ])
