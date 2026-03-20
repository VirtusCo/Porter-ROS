// Copyright 2026 VirtusCo
// Licensed under Apache-2.0

import 'package:flutter/material.dart';
import '../models/models.dart';
import '../theme/porter_theme.dart';

/// Airport map and wayfinding screen.
///
/// Shows a simplified terminal map with points of interest.
/// Touch a POI to get directions — future: integrates with Nav2 goals.
class MapScreen extends StatefulWidget {
  const MapScreen({super.key});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  MapPoi? _selectedPoi;

  /// Demo POIs (replace with real data from airport config or ROS service).
  static const List<MapPoi> _pois = [
    MapPoi(
        name: 'Gate A12',
        category: 'gate',
        x: 0.75,
        y: 0.2,
        description: 'Terminal 3, Level 2'),
    MapPoi(
        name: 'Gate B7',
        category: 'gate',
        x: 0.5,
        y: 0.15,
        description: 'Terminal 2, Level 2'),
    MapPoi(
        name: 'Gate C3',
        category: 'gate',
        x: 0.25,
        y: 0.2,
        description: 'Terminal 1, Level 2'),
    MapPoi(
        name: 'Restroom A',
        category: 'restroom',
        x: 0.65,
        y: 0.4,
        description: 'Near Gate A5'),
    MapPoi(
        name: 'Restroom B',
        category: 'restroom',
        x: 0.35,
        y: 0.4,
        description: 'Near Food Court'),
    MapPoi(
        name: 'Food Court',
        category: 'restaurant',
        x: 0.5,
        y: 0.5,
        description: '12 restaurants, Level 1'),
    MapPoi(
        name: 'Duty Free',
        category: 'shop',
        x: 0.6,
        y: 0.6,
        description: 'Main shopping area'),
    MapPoi(
        name: 'Info Desk',
        category: 'service',
        x: 0.5,
        y: 0.75,
        description: 'Airport information'),
    MapPoi(
        name: 'Lounge',
        category: 'service',
        x: 0.8,
        y: 0.5,
        description: 'Business & Priority'),
    MapPoi(
        name: 'Check-in',
        category: 'service',
        x: 0.5,
        y: 0.9,
        description: 'All airlines'),
  ];

  IconData _poiIcon(String category) {
    switch (category) {
      case 'gate':
        return Icons.flight;
      case 'restroom':
        return Icons.wc;
      case 'restaurant':
        return Icons.restaurant;
      case 'shop':
        return Icons.shopping_bag;
      case 'service':
        return Icons.info_outline;
      default:
        return Icons.place;
    }
  }

  Color _poiColor(String category) {
    switch (category) {
      case 'gate':
        return PorterTheme.accentCyan;
      case 'restroom':
        return PorterTheme.primaryBlue;
      case 'restaurant':
        return PorterTheme.warningAmber;
      case 'shop':
        return const Color(0xFFA78BFA);
      case 'service':
        return PorterTheme.successGreen;
      default:
        return Colors.grey;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Header.
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 16, 8),
          child: Row(
            children: [
              Text(
                'Airport Map',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const Spacer(),
              _LegendChip(
                  icon: Icons.flight,
                  color: PorterTheme.accentCyan,
                  label: 'Gate'),
              _LegendChip(
                  icon: Icons.restaurant,
                  color: PorterTheme.warningAmber,
                  label: 'Food'),
              _LegendChip(
                  icon: Icons.wc,
                  color: PorterTheme.primaryBlue,
                  label: 'WC'),
            ],
          ),
        ),
        const Divider(height: 1, color: PorterTheme.surfaceBorder),

        // Map area.
        Expanded(
          child: Row(
            children: [
              // Map canvas.
              Expanded(
                flex: 3,
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    return Stack(
                      children: [
                        // Background grid.
                        CustomPaint(
                          size: Size(
                              constraints.maxWidth, constraints.maxHeight),
                          painter: _MapGridPainter(),
                        ),
                        // POI markers.
                        ..._pois.map((poi) {
                          final left = poi.x * constraints.maxWidth - 16;
                          final top = poi.y * constraints.maxHeight - 16;
                          return Positioned(
                            left: left,
                            top: top,
                            child: GestureDetector(
                              onTap: () =>
                                  setState(() => _selectedPoi = poi),
                              child: AnimatedContainer(
                                duration: const Duration(milliseconds: 200),
                                width: 32,
                                height: 32,
                                decoration: BoxDecoration(
                                  color: _selectedPoi == poi
                                      ? _poiColor(poi.category)
                                      : _poiColor(poi.category)
                                          .withValues(alpha: 0.7),
                                  borderRadius: BorderRadius.circular(16),
                                  border: _selectedPoi == poi
                                      ? Border.all(
                                          color: Colors.white, width: 2)
                                      : null,
                                ),
                                child: Icon(
                                  _poiIcon(poi.category),
                                  size: 16,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                          );
                        }),
                        // Robot position (center).
                        Positioned(
                          left: constraints.maxWidth * 0.5 - 14,
                          top: constraints.maxHeight * 0.7 - 14,
                          child: Container(
                            width: 28,
                            height: 28,
                            decoration: BoxDecoration(
                              color: PorterTheme.successGreen,
                              borderRadius: BorderRadius.circular(14),
                              border:
                                  Border.all(color: Colors.white, width: 2),
                            ),
                            child: const Icon(Icons.navigation,
                                size: 14, color: Colors.white),
                          ),
                        ),
                      ],
                    );
                  },
                ),
              ),

              // POI detail panel.
              if (_selectedPoi != null)
                SizedBox(
                  width: 200,
                  child: _PoiDetail(
                    poi: _selectedPoi!,
                    iconData: _poiIcon(_selectedPoi!.category),
                    color: _poiColor(_selectedPoi!.category),
                    onNavigate: () {
                      // Future: send Nav2 goal.
                    },
                    onClose: () =>
                        setState(() => _selectedPoi = null),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

class _LegendChip extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String label;

  const _LegendChip({
    required this.icon,
    required this.color,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 8),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 4),
          Text(label,
              style: const TextStyle(
                  fontSize: 11, color: PorterTheme.textSecondary)),
        ],
      ),
    );
  }
}

class _PoiDetail extends StatelessWidget {
  final MapPoi poi;
  final IconData iconData;
  final Color color;
  final VoidCallback onNavigate;
  final VoidCallback onClose;

  const _PoiDetail({
    required this.poi,
    required this.iconData,
    required this.color,
    required this.onNavigate,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: PorterTheme.surfaceCard,
        border: Border(
          left: BorderSide(color: PorterTheme.surfaceBorder),
        ),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(iconData, color: color, size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  poi.name,
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 15,
                    color: PorterTheme.textPrimary,
                  ),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.close, size: 18),
                onPressed: onClose,
                constraints: const BoxConstraints(
                    minWidth: 32, minHeight: 32),
                padding: EdgeInsets.zero,
              ),
            ],
          ),
          const SizedBox(height: 8),
          if (poi.description != null)
            Text(
              poi.description!,
              style: const TextStyle(
                  fontSize: 13, color: PorterTheme.textSecondary),
            ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              icon: const Icon(Icons.navigation, size: 16),
              label: const Text('Navigate Here'),
              style: ElevatedButton.styleFrom(
                backgroundColor: color,
              ),
              onPressed: onNavigate,
            ),
          ),
        ],
      ),
    );
  }
}

/// Grid background painter for the map.
class _MapGridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = PorterTheme.surfaceBorder.withValues(alpha: 0.3)
      ..strokeWidth = 0.5;

    // Draw grid lines.
    const spacing = 40.0;
    for (double x = 0; x < size.width; x += spacing) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (double y = 0; y < size.height; y += spacing) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }

    // Terminal outline.
    final outlinePaint = Paint()
      ..color = PorterTheme.surfaceBorder
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;

    final terminalPath = Path()
      ..moveTo(size.width * 0.1, size.height * 0.1)
      ..lineTo(size.width * 0.9, size.height * 0.1)
      ..lineTo(size.width * 0.9, size.height * 0.95)
      ..lineTo(size.width * 0.1, size.height * 0.95)
      ..close();

    canvas.drawPath(terminalPath, outlinePaint);

    // Concourse lines.
    final concourseP = Paint()
      ..color = PorterTheme.surfaceBorder.withValues(alpha: 0.5)
      ..strokeWidth = 1;

    canvas.drawLine(
      Offset(size.width * 0.5, size.height * 0.1),
      Offset(size.width * 0.5, size.height * 0.95),
      concourseP,
    );
    canvas.drawLine(
      Offset(size.width * 0.1, size.height * 0.5),
      Offset(size.width * 0.9, size.height * 0.5),
      concourseP,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
