# Copyright 2026 VirtusCo
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

"""Launch file for Porter ESP32 bridge nodes."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for motor and sensor bridge nodes."""
    return LaunchDescription([
        # --- Launch arguments ---
        DeclareLaunchArgument(
            'motor_port', default_value='/dev/esp32_motors',
            description='Serial port for ESP32 motor controller'),
        DeclareLaunchArgument(
            'sensor_port', default_value='/dev/esp32_sensors',
            description='Serial port for ESP32 sensor fusion'),
        DeclareLaunchArgument(
            'baudrate', default_value='115200',
            description='Serial baudrate for both ESP32 devices'),
        DeclareLaunchArgument(
            'wheel_separation', default_value='0.35',
            description='Distance between wheels in metres'),
        DeclareLaunchArgument(
            'wheel_radius', default_value='0.05',
            description='Wheel radius in metres'),

        # --- Motor bridge node ---
        Node(
            package='porter_esp32_bridge',
            executable='esp32_motor_bridge',
            name='esp32_motor_bridge',
            output='screen',
            parameters=[{
                'port': LaunchConfiguration('motor_port'),
                'baudrate': LaunchConfiguration('baudrate'),
                'wheel_separation': LaunchConfiguration('wheel_separation'),
                'wheel_radius': LaunchConfiguration('wheel_radius'),
            }],
            remappings=[
                ('cmd_vel', '/cmd_vel'),
                ('motor_status', '/motor_status'),
            ],
        ),

        # --- Sensor bridge node ---
        Node(
            package='porter_esp32_bridge',
            executable='esp32_sensor_bridge',
            name='esp32_sensor_bridge',
            output='screen',
            parameters=[{
                'port': LaunchConfiguration('sensor_port'),
                'baudrate': LaunchConfiguration('baudrate'),
            }],
            remappings=[
                ('environment', '/environment'),
                ('sensor_status', '/sensor_status'),
            ],
        ),
    ])
