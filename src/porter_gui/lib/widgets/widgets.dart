// Copyright 2026 VirtusCo
// Licensed under Apache-2.0

import 'package:flutter/material.dart';
import '../models/models.dart';
import '../theme/porter_theme.dart';

/// Status indicator dot with color coding.
class StatusIndicator extends StatelessWidget {
  final HealthLevel level;
  final double size;

  const StatusIndicator({
    super.key,
    required this.level,
    this.size = 10,
  });

  Color get color {
    switch (level) {
      case HealthLevel.ok:
        return PorterTheme.successGreen;
      case HealthLevel.warn:
        return PorterTheme.warningAmber;
      case HealthLevel.error:
        return PorterTheme.emergencyRed;
      case HealthLevel.stale:
        return Colors.grey;
      case HealthLevel.unknown:
        return Colors.grey.shade700;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
      ),
    );
  }
}

/// Card widget for diagnostics display.
class DiagnosticCard extends StatelessWidget {
  final DiagnosticStatus status;

  const DiagnosticCard({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            StatusIndicator(level: status.level),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    status.name,
                    style: Theme.of(context).textTheme.titleMedium,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    status.message,
                    style: Theme.of(context).textTheme.bodySmall,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Connection status banner shown when disconnected.
class ConnectionBanner extends StatelessWidget {
  final bool connected;
  final VoidCallback onReconnect;

  const ConnectionBanner({
    super.key,
    required this.connected,
    required this.onReconnect,
  });

  @override
  Widget build(BuildContext context) {
    if (connected) return const SizedBox.shrink();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      color: PorterTheme.emergencyRed.withValues(alpha: 0.15),
      child: Row(
        children: [
          const Icon(Icons.cloud_off,
              color: PorterTheme.emergencyRed, size: 16),
          const SizedBox(width: 8),
          const Expanded(
            child: Text(
              'Disconnected from robot',
              style: TextStyle(
                  color: PorterTheme.emergencyRed, fontSize: 13),
            ),
          ),
          TextButton(
            onPressed: onReconnect,
            style: TextButton.styleFrom(
              minimumSize: const Size(0, 32),
              padding: const EdgeInsets.symmetric(horizontal: 12),
            ),
            child: const Text(
              'Reconnect',
              style: TextStyle(
                  color: PorterTheme.emergencyRed,
                  fontWeight: FontWeight.w600,
                  fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }
}

/// Perplexity-style left navigation sidebar.
class PorterNavRail extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  const PorterNavRail({
    super.key,
    required this.selectedIndex,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 68,
      decoration: const BoxDecoration(
        color: PorterTheme.surfaceDark,
        border: Border(
          right: BorderSide(color: PorterTheme.surfaceBorder, width: 1),
        ),
      ),
      child: Column(
        children: [
          const SizedBox(height: 12),
          // VirtusCo logo.
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [PorterTheme.primaryBlue, PorterTheme.accentCyan],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Center(
              child: Text(
                'V',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
          const SizedBox(height: 20),
          _NavItem(
            icon: Icons.chat_bubble_outline,
            activeIcon: Icons.chat_bubble,
            label: 'Chat',
            selected: selectedIndex == 0,
            onTap: () => onSelected(0),
          ),
          _NavItem(
            icon: Icons.flight_takeoff_outlined,
            activeIcon: Icons.flight_takeoff,
            label: 'Flights',
            selected: selectedIndex == 1,
            onTap: () => onSelected(1),
          ),
          _NavItem(
            icon: Icons.map_outlined,
            activeIcon: Icons.map,
            label: 'Map',
            selected: selectedIndex == 2,
            onTap: () => onSelected(2),
          ),
          _NavItem(
            icon: Icons.monitor_heart_outlined,
            activeIcon: Icons.monitor_heart,
            label: 'Status',
            selected: selectedIndex == 3,
            onTap: () => onSelected(3),
          ),
          const Spacer(),
          _NavItem(
            icon: Icons.directions_walk_outlined,
            activeIcon: Icons.directions_walk,
            label: 'Follow',
            selected: selectedIndex == 4,
            onTap: () => onSelected(4),
          ),
          const SizedBox(height: 12),
        ],
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final IconData activeIcon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _NavItem({
    required this.icon,
    required this.activeIcon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2, horizontal: 6),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          width: 56,
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: selected
                ? PorterTheme.surfaceCard
                : Colors.transparent,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                selected ? activeIcon : icon,
                color: selected
                    ? PorterTheme.accentCyan
                    : PorterTheme.textTertiary,
                size: 22,
              ),
              const SizedBox(height: 3),
              Text(
                label,
                style: TextStyle(
                  fontSize: 10,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                  color: selected
                      ? PorterTheme.textPrimary
                      : PorterTheme.textTertiary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
