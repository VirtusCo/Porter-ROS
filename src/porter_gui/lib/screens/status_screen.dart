// Copyright 2026 VirtusCo
// Licensed under Apache-2.0

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/models.dart';
import '../providers/providers.dart';
import '../theme/porter_theme.dart';
import '../widgets/widgets.dart';

/// System status dashboard — diagnostics, battery, CPU, robot state.
class StatusScreen extends StatelessWidget {
  const StatusScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final status = context.watch<SystemStatusProvider>();

    return Column(
      children: [
        // Header with overall status.
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 16, 8),
          child: Row(
            children: [
              Text(
                'System Status',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const Spacer(),
              _OverallBadge(level: status.overallHealth),
            ],
          ),
        ),
        const Divider(height: 1, color: PorterTheme.surfaceBorder),

        // Status grid.
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Top row: Robot state + vitals.
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Robot state card.
                    Expanded(
                      child: _RobotStateCard(state: status.robotState),
                    ),
                    const SizedBox(width: 8),
                    // Vitals column.
                    Expanded(
                      child: Column(
                        children: [
                          _VitalCard(
                            icon: Icons.battery_charging_full,
                            label: 'Battery',
                            value: status.batteryPercent >= 0
                                ? '${status.batteryPercent.toStringAsFixed(0)}%'
                                : 'N/A',
                            color: _batteryColor(status.batteryPercent),
                          ),
                          const SizedBox(height: 4),
                          _VitalCard(
                            icon: Icons.thermostat,
                            label: 'CPU Temp',
                            value: status.cpuTemp >= 0
                                ? '${status.cpuTemp.toStringAsFixed(1)}°C'
                                : 'N/A',
                            color: _tempColor(status.cpuTemp),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),

                // Diagnostics list.
                Padding(
                  padding: const EdgeInsets.only(left: 4),
                  child: Text(
                    'Subsystems',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          color: PorterTheme.textSecondary,
                        ),
                  ),
                ),
                const SizedBox(height: 6),
                if (status.diagnostics.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(16),
                    child: Center(
                      child: Text(
                        'Waiting for diagnostics...',
                        style:
                            TextStyle(color: PorterTheme.textTertiary),
                      ),
                    ),
                  )
                else
                  ...status.diagnostics.values
                      .map((d) => DiagnosticCard(status: d)),
              ],
            ),
          ),
        ),
      ],
    );
  }

  static Color _batteryColor(double percent) {
    if (percent < 0) return Colors.grey;
    if (percent < 20) return PorterTheme.emergencyRed;
    if (percent < 50) return PorterTheme.warningAmber;
    return PorterTheme.successGreen;
  }

  static Color _tempColor(double temp) {
    if (temp < 0) return Colors.grey;
    if (temp > 80) return PorterTheme.emergencyRed;
    if (temp > 65) return PorterTheme.warningAmber;
    return PorterTheme.successGreen;
  }
}

class _OverallBadge extends StatelessWidget {
  final HealthLevel level;

  const _OverallBadge({required this.level});

  String get label {
    switch (level) {
      case HealthLevel.ok:
        return 'ALL OK';
      case HealthLevel.warn:
        return 'WARNING';
      case HealthLevel.error:
        return 'ERROR';
      case HealthLevel.stale:
        return 'STALE';
      case HealthLevel.unknown:
        return 'UNKNOWN';
    }
  }

  Color get color {
    switch (level) {
      case HealthLevel.ok:
        return PorterTheme.successGreen;
      case HealthLevel.warn:
        return PorterTheme.warningAmber;
      case HealthLevel.error:
        return PorterTheme.emergencyRed;
      case HealthLevel.stale:
      case HealthLevel.unknown:
        return PorterTheme.textTertiary;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          StatusIndicator(level: level, size: 8),
          const SizedBox(width: 8),
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}

class _RobotStateCard extends StatelessWidget {
  final RobotState state;

  const _RobotStateCard({required this.state});

  String get label {
    switch (state) {
      case RobotState.booting:
        return 'Booting';
      case RobotState.idle:
        return 'Idle';
      case RobotState.followMe:
        return 'Follow Me';
      case RobotState.navigating:
        return 'Navigating';
      case RobotState.error:
        return 'Error';
      case RobotState.emergencyStop:
        return 'E-STOP';
    }
  }

  IconData get icon {
    switch (state) {
      case RobotState.booting:
        return Icons.hourglass_top;
      case RobotState.idle:
        return Icons.check_circle;
      case RobotState.followMe:
        return Icons.directions_walk;
      case RobotState.navigating:
        return Icons.navigation;
      case RobotState.error:
        return Icons.error;
      case RobotState.emergencyStop:
        return Icons.dangerous;
    }
  }

  Color get color {
    switch (state) {
      case RobotState.booting:
        return PorterTheme.warningAmber;
      case RobotState.idle:
        return PorterTheme.successGreen;
      case RobotState.followMe:
        return PorterTheme.accentCyan;
      case RobotState.navigating:
        return PorterTheme.primaryBlue;
      case RobotState.error:
      case RobotState.emergencyStop:
        return PorterTheme.emergencyRed;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Icon(icon, size: 32, color: color),
            const SizedBox(height: 8),
            Text(
              label,
              style: TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w600,
                color: color,
              ),
            ),
            const SizedBox(height: 4),
            const Text(
              'Robot State',
              style: TextStyle(
                  fontSize: 12, color: PorterTheme.textTertiary),
            ),
          ],
        ),
      ),
    );
  }
}

class _VitalCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  const _VitalCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(width: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  value,
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: color,
                  ),
                ),
                Text(
                  label,
                  style: const TextStyle(
                    fontSize: 11,
                    color: PorterTheme.textTertiary,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
