# Copyright 2026 VirtusCo. All rights reserved.
# Proprietary and confidential.
#
# Launch file for the Porter LIDAR Processor (C++) node.
#
# Usage:
#   ros2 launch porter_lidar_processor_cpp processor_launch.py
#   ros2 launch porter_lidar_processor_cpp processor_launch.py \
#       enable_smoothing:=false

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for the C++ processor node."""
    pkg_dir = get_package_share_directory('porter_lidar_processor_cpp')
    params_file = os.path.join(pkg_dir, 'config', 'processor_params.yaml')

    return LaunchDescription([
        # ── Launch arguments ──────────────────────────────────────────────
        DeclareLaunchArgument(
            'params_file',
            default_value=params_file,
            description='Path to processor parameters YAML file',
        ),

        # ── Processor node ────────────────────────────────────────────────
        Node(
            package='porter_lidar_processor_cpp',
            executable='lidar_processor_node',
            name='lidar_processor_node',
            output='screen',
            parameters=[
                LaunchConfiguration('params_file'),
            ],
            remappings=[
                ('scan', '/scan'),
                ('scan/processed', '/scan/processed'),
            ],
        ),
    ])
