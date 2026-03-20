# Copyright 2026 VirtusCo. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Launch YDLIDAR driver with RViz2 visualization and static TF."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for YDLIDAR + RViz2."""
    pkg_share = get_package_share_directory('ydlidar_driver')
    default_params = os.path.join(pkg_share, 'config', 'ydlidar_params.yaml')
    default_rviz = os.path.join(pkg_share, 'config', 'ydlidar_view.rviz')

    return LaunchDescription([
        # ── Launch Arguments ──────────────────────────────────────────
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Full path to the YDLIDAR parameters YAML file'
        ),
        DeclareLaunchArgument(
            'port',
            default_value='/dev/ttyUSB0',
            description='Serial port for the YDLIDAR device'
        ),
        DeclareLaunchArgument(
            'frame_id',
            default_value='laser_frame',
            description='TF frame ID for LaserScan messages'
        ),

        # ── Static TF: base_link → laser_frame ───────────────────────
        # This provides a minimal TF tree so RViz2 can render the scan.
        # In production, robot_state_publisher publishes this from URDF.
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='base_to_laser_tf',
            output='screen',
            arguments=[
                '--x', '0.0',
                '--y', '0.0',
                '--z', '0.1',
                '--roll', '0.0',
                '--pitch', '0.0',
                '--yaw', '0.0',
                '--frame-id', 'base_link',
                '--child-frame-id', 'laser_frame',
            ],
        ),

        # ── YDLIDAR Node ─────────────────────────────────────────────
        Node(
            package='ydlidar_driver',
            executable='ydlidar_node',
            name='ydlidar_node',
            output='screen',
            parameters=[
                LaunchConfiguration('params_file'),
                {
                    'port': LaunchConfiguration('port'),
                    'frame_id': LaunchConfiguration('frame_id'),
                }
            ],
        ),

        # ── RViz2 ────────────────────────────────────────────────────
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            output='screen',
            arguments=['-d', default_rviz],
        ),
    ])
