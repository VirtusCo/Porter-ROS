"""Launch file for the Virtus Observability Stack.

Starts all three observability nodes (log_bridge, metrics_emitter,
event_journal) with shared robot_id parameter and configurable data
directories.
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for the observability stack."""
    # Declare launch arguments
    robot_id_arg = DeclareLaunchArgument(
        'robot_id',
        default_value='porter-001',
        description='Unique identifier for this robot',
    )
    log_dir_arg = DeclareLaunchArgument(
        'log_dir',
        default_value='/opt/virtus/logs',
        description='Directory for structured log JSONL files',
    )
    metrics_dir_arg = DeclareLaunchArgument(
        'metrics_dir',
        default_value='/opt/virtus/metrics',
        description='Directory for metrics JSONL files',
    )
    events_dir_arg = DeclareLaunchArgument(
        'events_dir',
        default_value='/opt/virtus/events',
        description='Directory for event journal JSONL files',
    )
    incidents_dir_arg = DeclareLaunchArgument(
        'incidents_dir',
        default_value='/opt/virtus/incidents',
        description='Directory for frozen incident files',
    )
    retention_days_arg = DeclareLaunchArgument(
        'retention_days',
        default_value='30',
        description='Number of days to retain log and metrics files',
    )

    # Shared parameters
    robot_id = LaunchConfiguration('robot_id')
    log_dir = LaunchConfiguration('log_dir')
    metrics_dir = LaunchConfiguration('metrics_dir')
    events_dir = LaunchConfiguration('events_dir')
    incidents_dir = LaunchConfiguration('incidents_dir')
    retention_days = LaunchConfiguration('retention_days')

    # Log bridge node
    log_bridge_node = Node(
        package='porter_observability',
        executable='log_bridge',
        name='log_bridge',
        parameters=[{
            'robot_id': robot_id,
            'log_dir': log_dir,
            'retention_days': retention_days,
        }],
        output='screen',
    )

    # Metrics emitter node
    metrics_emitter_node = Node(
        package='porter_observability',
        executable='metrics_emitter',
        name='metrics_emitter',
        parameters=[{
            'robot_id': robot_id,
            'metrics_dir': metrics_dir,
            'retention_days': retention_days,
        }],
        output='screen',
    )

    # Event journal node
    event_journal_node = Node(
        package='porter_observability',
        executable='event_journal',
        name='event_journal',
        parameters=[{
            'robot_id': robot_id,
            'events_dir': events_dir,
            'incidents_dir': incidents_dir,
        }],
        output='screen',
    )

    return LaunchDescription([
        robot_id_arg,
        log_dir_arg,
        metrics_dir_arg,
        events_dir_arg,
        incidents_dir_arg,
        retention_days_arg,
        log_bridge_node,
        metrics_emitter_node,
        event_journal_node,
    ])
