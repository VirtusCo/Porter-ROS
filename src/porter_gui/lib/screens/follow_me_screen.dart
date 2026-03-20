// Copyright 2026 VirtusCo
// Licensed under Apache-2.0

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/providers.dart';
import '../theme/porter_theme.dart';

/// Follow-Me mode control screen.
class FollowMeScreen extends StatelessWidget {
  const FollowMeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final followMe = context.watch<FollowMeProvider>();
    final eStop = context.watch<EmergencyStopProvider>();
    final isActive = followMe.isActive;

    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Mode icon.
          AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            width: 96,
            height: 96,
            decoration: BoxDecoration(
              color: isActive
                  ? PorterTheme.accentCyan.withValues(alpha: 0.15)
                  : PorterTheme.surfaceCard,
              borderRadius: BorderRadius.circular(24),
              border: Border.all(
                color: isActive
                    ? PorterTheme.accentCyan
                    : PorterTheme.surfaceBorder,
                width: 2,
              ),
            ),
            child: Icon(
              Icons.directions_walk_rounded,
              size: 44,
              color: isActive
                  ? PorterTheme.accentCyan
                  : PorterTheme.textTertiary,
            ),
          ),
          const SizedBox(height: 24),
          Text(
            isActive ? 'Following You' : 'Follow Me',
            style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  color: isActive
                      ? PorterTheme.accentCyan
                      : PorterTheme.textPrimary,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            isActive
                ? 'Porter is following you. Keep walking!'
                : 'Tap the button to start Follow-Me mode.',
            style: const TextStyle(
                fontSize: 14, color: PorterTheme.textSecondary),
          ),
          const SizedBox(height: 32),

          // Toggle button.
          SizedBox(
            width: 200,
            height: 52,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: isActive
                    ? PorterTheme.emergencyRed
                    : PorterTheme.accentCyan,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                ),
                elevation: 0,
              ),
              onPressed: eStop.isEngaged ? null : followMe.toggle,
              child: Text(
                isActive ? 'STOP FOLLOWING' : 'START FOLLOWING',
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.5,
                ),
              ),
            ),
          ),

          if (eStop.isEngaged) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: BoxDecoration(
                color: PorterTheme.emergencyRed.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Text(
                'Emergency stop engaged. Disengage to use Follow-Me.',
                style: TextStyle(
                  color: PorterTheme.emergencyRed,
                  fontSize: 13,
                ),
              ),
            ),
          ],

          const SizedBox(height: 48),

          // Emergency stop.
          _EmergencyStopButton(eStop: eStop),
        ],
      ),
    );
  }
}

/// Emergency stop button widget.
class _EmergencyStopButton extends StatelessWidget {
  final EmergencyStopProvider eStop;

  const _EmergencyStopButton({required this.eStop});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onLongPress: eStop.isEngaged
          ? () => _showDisengageDialog(context)
          : eStop.engage,
      onTap: eStop.isEngaged ? () {} : eStop.engage,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: 100,
        height: 100,
        decoration: BoxDecoration(
          color: eStop.isEngaged
              ? PorterTheme.emergencyRed
              : PorterTheme.surfaceCard,
          borderRadius: BorderRadius.circular(28),
          border: Border.all(
            color: eStop.isEngaged
                ? PorterTheme.emergencyRed
                : PorterTheme.surfaceBorder,
            width: 3,
          ),
          boxShadow: eStop.isEngaged
              ? [
                  BoxShadow(
                    color: PorterTheme.emergencyRed.withValues(alpha: 0.4),
                    blurRadius: 16,
                    spreadRadius: 2,
                  ),
                ]
              : [],
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.dangerous_rounded,
              size: 32,
              color: eStop.isEngaged ? Colors.white : PorterTheme.emergencyRed,
            ),
            const SizedBox(height: 4),
            Text(
              eStop.isEngaged ? 'E-STOP\nON' : 'E-STOP',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color:
                    eStop.isEngaged ? Colors.white : PorterTheme.emergencyRed,
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showDisengageDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Disengage Emergency Stop?'),
        content: const Text(
          'Are you sure you want to disengage the emergency stop? '
          'Make sure the area around the robot is clear.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: PorterTheme.warningAmber,
            ),
            onPressed: () {
              eStop.disengage();
              Navigator.of(ctx).pop();
            },
            child: const Text('Disengage'),
          ),
        ],
      ),
    );
  }
}
