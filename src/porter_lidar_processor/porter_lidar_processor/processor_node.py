"""Porter LIDAR Processor Node — subscribes to /scan, publishes /scan/processed.

Applies a configurable chain of filters to raw LaserScan data from the
ydlidar_driver, producing a cleaned scan suitable for Nav2 and obstacle
avoidance. Filters can be toggled at runtime via a ``SetBool`` service
and parameters can be changed dynamically.

Architecture:
    /scan (ydlidar_driver) → [processor_node] → /scan/processed

Filters (applied in order when enabled):
    1. Range clamp   — discard values outside [min_range, max_range]
    2. Outlier reject — remove salt-and-pepper spikes (MAD-based)
    3. Median filter  — sliding-window median for denoising
    4. Smoothing      — moving average for gentle noise reduction
    5. ROI crop       — zero out ranges outside angular region of interest
    6. Downsample     — reduce point density (optional, for RPi performance)

Copyright 2026 VirtusCo. All rights reserved. Proprietary and confidential.
"""

import numpy as np
from porter_lidar_processor.filters import (
    downsample_filter,
    median_filter,
    moving_average_filter,
    outlier_rejection_filter,
    range_clamp_filter,
    roi_crop_filter,
)
import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from std_srvs.srv import SetBool


class ProcessorNode(Node):
    """ROS 2 node that filters LaserScan data for Porter Robot.

    Subscribes to ``/scan`` (raw) and publishes to ``/scan/processed``
    (filtered). All filter stages can be enabled/disabled and tuned
    via ROS parameters. A ``~/enable_filters`` service toggles the
    entire filter pipeline on/off at runtime.
    """

    def __init__(self):
        """Initialise the processor node with parameters, pub/sub, and service."""
        super().__init__('lidar_processor')

        # ── Declare parameters ────────────────────────────────────────────
        self._declare_parameters()

        # ── Read initial configuration ────────────────────────────────────
        self._load_config()

        # ── QoS: match the ydlidar_driver publisher (RELIABLE + KEEP_LAST) ─
        scan_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )

        # ── Subscriber ────────────────────────────────────────────────────
        self.scan_sub_ = self.create_subscription(
            LaserScan, 'scan', self._scan_callback, scan_qos)

        # ── Publisher ─────────────────────────────────────────────────────
        self.scan_pub_ = self.create_publisher(
            LaserScan, 'scan/processed', scan_qos)

        # ── Service: toggle filters on/off ────────────────────────────────
        self.filter_srv_ = self.create_service(
            SetBool, '~/enable_filters', self._enable_filters_callback)

        # ── Parameter change callback ─────────────────────────────────────
        self.add_on_set_parameters_callback(self._on_parameter_change)

        # ── Stats ─────────────────────────────────────────────────────────
        self.msg_count_ = 0

        self.get_logger().info(
            'Porter LIDAR Processor started — '
            f'filters_enabled={self.filters_enabled_}')

    # ══════════════════════════════════════════════════════════════════════
    # Parameter declaration
    # ══════════════════════════════════════════════════════════════════════

    def _declare_parameters(self):
        """Declare all typed parameters with defaults."""
        # Master switch
        self.declare_parameter('filters_enabled', True)

        # Range clamp
        self.declare_parameter('range_clamp.enabled', True)
        self.declare_parameter('range_clamp.min_range', 0.05)
        self.declare_parameter('range_clamp.max_range', 12.0)

        # Outlier rejection
        self.declare_parameter('outlier.enabled', True)
        self.declare_parameter('outlier.kernel_size', 5)
        self.declare_parameter('outlier.threshold', 1.5)

        # Median filter
        self.declare_parameter('median.enabled', True)
        self.declare_parameter('median.kernel_size', 5)

        # Smoothing (moving average)
        self.declare_parameter('smoothing.enabled', False)
        self.declare_parameter('smoothing.kernel_size', 3)

        # ROI crop
        self.declare_parameter('roi.enabled', False)
        self.declare_parameter('roi.angle_min_deg', -90.0)
        self.declare_parameter('roi.angle_max_deg', 90.0)

        # Downsample
        self.declare_parameter('downsample.enabled', False)
        self.declare_parameter('downsample.factor', 2)

    # ══════════════════════════════════════════════════════════════════════
    # Configuration loading
    # ══════════════════════════════════════════════════════════════════════

    def _load_config(self):
        """Read all parameters into instance variables."""
        self.filters_enabled_ = (
            self.get_parameter('filters_enabled').get_parameter_value().bool_value
        )

        # Range clamp
        self.range_clamp_enabled_ = (
            self.get_parameter('range_clamp.enabled')
            .get_parameter_value().bool_value
        )
        self.range_clamp_min_ = (
            self.get_parameter('range_clamp.min_range')
            .get_parameter_value().double_value
        )
        self.range_clamp_max_ = (
            self.get_parameter('range_clamp.max_range')
            .get_parameter_value().double_value
        )

        # Outlier rejection
        self.outlier_enabled_ = (
            self.get_parameter('outlier.enabled')
            .get_parameter_value().bool_value
        )
        self.outlier_kernel_ = (
            self.get_parameter('outlier.kernel_size')
            .get_parameter_value().integer_value
        )
        self.outlier_threshold_ = (
            self.get_parameter('outlier.threshold')
            .get_parameter_value().double_value
        )

        # Median
        self.median_enabled_ = (
            self.get_parameter('median.enabled')
            .get_parameter_value().bool_value
        )
        self.median_kernel_ = (
            self.get_parameter('median.kernel_size')
            .get_parameter_value().integer_value
        )

        # Smoothing
        self.smoothing_enabled_ = (
            self.get_parameter('smoothing.enabled')
            .get_parameter_value().bool_value
        )
        self.smoothing_kernel_ = (
            self.get_parameter('smoothing.kernel_size')
            .get_parameter_value().integer_value
        )

        # ROI crop
        self.roi_enabled_ = (
            self.get_parameter('roi.enabled')
            .get_parameter_value().bool_value
        )
        self.roi_angle_min_ = (
            self.get_parameter('roi.angle_min_deg')
            .get_parameter_value().double_value
        )
        self.roi_angle_max_ = (
            self.get_parameter('roi.angle_max_deg')
            .get_parameter_value().double_value
        )

        # Downsample
        self.downsample_enabled_ = (
            self.get_parameter('downsample.enabled')
            .get_parameter_value().bool_value
        )
        self.downsample_factor_ = (
            self.get_parameter('downsample.factor')
            .get_parameter_value().integer_value
        )

    # ══════════════════════════════════════════════════════════════════════
    # Dynamic parameter change callback
    # ══════════════════════════════════════════════════════════════════════

    def _on_parameter_change(self, params):
        """Handle dynamic parameter changes without restart.

        Args:
            params: List of changed Parameter objects.

        Returns:
            SetParametersResult indicating success.
        """
        from rcl_interfaces.msg import SetParametersResult

        for param in params:
            name = param.name
            val = param.value

            if name == 'filters_enabled':
                self.filters_enabled_ = val
                self.get_logger().info(
                    f'Filters {"enabled" if val else "disabled"}')
            elif name == 'range_clamp.enabled':
                self.range_clamp_enabled_ = val
            elif name == 'range_clamp.min_range':
                self.range_clamp_min_ = val
            elif name == 'range_clamp.max_range':
                self.range_clamp_max_ = val
            elif name == 'outlier.enabled':
                self.outlier_enabled_ = val
            elif name == 'outlier.kernel_size':
                self.outlier_kernel_ = val
            elif name == 'outlier.threshold':
                self.outlier_threshold_ = val
            elif name == 'median.enabled':
                self.median_enabled_ = val
            elif name == 'median.kernel_size':
                self.median_kernel_ = val
            elif name == 'smoothing.enabled':
                self.smoothing_enabled_ = val
            elif name == 'smoothing.kernel_size':
                self.smoothing_kernel_ = val
            elif name == 'roi.enabled':
                self.roi_enabled_ = val
            elif name == 'roi.angle_min_deg':
                self.roi_angle_min_ = val
            elif name == 'roi.angle_max_deg':
                self.roi_angle_max_ = val
            elif name == 'downsample.enabled':
                self.downsample_enabled_ = val
            elif name == 'downsample.factor':
                self.downsample_factor_ = val

        return SetParametersResult(successful=True)

    # ══════════════════════════════════════════════════════════════════════
    # Service: enable/disable filters
    # ══════════════════════════════════════════════════════════════════════

    def _enable_filters_callback(self, request, response):
        """Handle ~/enable_filters service request.

        Args:
            request: SetBool request (data=True to enable, False to disable).
            response: SetBool response.

        Returns:
            The populated response.
        """
        self.filters_enabled_ = request.data
        state = 'enabled' if request.data else 'disabled'
        response.success = True
        response.message = f'Filters {state}'
        self.get_logger().info(f'Service: filters {state}')
        return response

    # ══════════════════════════════════════════════════════════════════════
    # Scan processing callback
    # ══════════════════════════════════════════════════════════════════════

    def _scan_callback(self, msg: LaserScan):
        """Process incoming LaserScan and publish filtered result.

        Args:
            msg: Raw LaserScan from ydlidar_driver.
        """
        # Convert to numpy for efficient processing
        ranges = np.array(msg.ranges, dtype=np.float32)

        if self.filters_enabled_:
            ranges = self._apply_filters(ranges, msg)

        # Build output message — copy header and geometry from input
        out = LaserScan()
        out.header = msg.header
        out.angle_min = msg.angle_min
        out.angle_max = msg.angle_max
        out.angle_increment = msg.angle_increment
        out.time_increment = msg.time_increment
        out.scan_time = msg.scan_time
        out.range_min = msg.range_min
        out.range_max = msg.range_max
        out.ranges = ranges.tolist()

        # Copy intensities if present, otherwise empty
        if len(msg.intensities) > 0:
            out.intensities = list(msg.intensities)

        self.scan_pub_.publish(out)

        self.msg_count_ += 1
        if self.msg_count_ == 1:
            self.get_logger().info(
                f'First processed scan published '
                f'({len(ranges)} points)')

    # ══════════════════════════════════════════════════════════════════════
    # Filter pipeline
    # ══════════════════════════════════════════════════════════════════════

    def _apply_filters(
        self, ranges: np.ndarray, msg: LaserScan
    ) -> np.ndarray:
        """Apply the configured filter chain to range data.

        Filters are applied in a fixed order optimised for quality:
        1. Range clamp (remove physically impossible values first)
        2. Outlier rejection (remove spikes before smoothing)
        3. Median filter (denoise)
        4. Smoothing / moving average (optional gentle filtering)
        5. ROI crop (restrict angular field of view)
        6. Downsample (reduce density for constrained compute)

        Args:
            ranges: 1-D numpy array of range values.
            msg: Original LaserScan message (for geometry info).

        Returns:
            Filtered numpy array of ranges.
        """
        # 1. Range clamp
        if self.range_clamp_enabled_:
            ranges = range_clamp_filter(
                ranges, self.range_clamp_min_, self.range_clamp_max_)

        # 2. Outlier rejection
        if self.outlier_enabled_:
            ranges = outlier_rejection_filter(
                ranges, self.outlier_kernel_, self.outlier_threshold_)

        # 3. Median filter
        if self.median_enabled_:
            ranges = median_filter(ranges, self.median_kernel_)

        # 4. Smoothing
        if self.smoothing_enabled_:
            ranges = moving_average_filter(
                ranges, self.smoothing_kernel_)

        # 5. ROI crop
        if self.roi_enabled_:
            ranges = roi_crop_filter(
                ranges,
                msg.angle_min,
                msg.angle_max,
                msg.angle_increment,
                self.roi_angle_min_,
                self.roi_angle_max_,
            )

        # 6. Downsample
        if self.downsample_enabled_:
            ranges = downsample_filter(
                ranges, self.downsample_factor_)

        return ranges


def main(args=None):
    """Entry point for the processor node."""
    rclpy.init(args=args)
    node = ProcessorNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info('Shutting down Porter LIDAR Processor')
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
