# Copyright 2026 VirtusCo
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Launch file for the Porter AI Assistant node."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for AI assistant.

    Set use_orchestrator:=true to launch the full orchestrator node
    with tool execution and conversation memory (for GUI integration).
    Default launches the simpler assistant_node.
    """
    pkg_share = get_package_share_directory('porter_ai_assistant')

    # Declare launch arguments
    params_file_arg = DeclareLaunchArgument(
        'params_file',
        default_value=os.path.join(pkg_share, 'config', 'assistant_params.yaml'),
        description='Path to the assistant parameters YAML file'
    )

    log_level_arg = DeclareLaunchArgument(
        'log_level',
        default_value='info',
        description='Logging level (debug, info, warn, error)'
    )

    use_orchestrator_arg = DeclareLaunchArgument(
        'use_orchestrator',
        default_value='false',
        description='Use orchestrator node with tool execution and memory'
    )

    # Simple assistant node (default)
    assistant_node = Node(
        package='porter_ai_assistant',
        executable='assistant_node',
        name='porter_ai_assistant',
        output='screen',
        parameters=[LaunchConfiguration('params_file')],
        arguments=['--ros-args', '--log-level',
                   LaunchConfiguration('log_level')],
        condition=UnlessCondition(LaunchConfiguration('use_orchestrator')),
    )

    # Orchestrator node (with tool execution + conversation memory)
    orchestrator_node = Node(
        package='porter_ai_assistant',
        executable='orchestrator_node',
        name='virtue_orchestrator',
        output='screen',
        parameters=[LaunchConfiguration('params_file')],
        arguments=['--ros-args', '--log-level',
                   LaunchConfiguration('log_level')],
        condition=IfCondition(LaunchConfiguration('use_orchestrator')),
    )

    return LaunchDescription([
        params_file_arg,
        log_level_arg,
        use_orchestrator_arg,
        assistant_node,
        orchestrator_node,
    ])
