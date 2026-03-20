// Copyright 2026 VirtusCo
// Licensed under Apache-2.0

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../models/models.dart';
import '../providers/providers.dart';
import '../theme/porter_theme.dart';

/// Flight information display — clean departure board.
class FlightInfoScreen extends StatelessWidget {
  const FlightInfoScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final flightProvider = context.watch<FlightInfoProvider>();
    final flights = flightProvider.flights;
    final timeFormat = DateFormat('HH:mm');

    return Column(
      children: [
        // Header.
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 16, 8),
          child: Row(
            children: [
              Text(
                'Departures',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const Spacer(),
              IconButton(
                icon: const Icon(Icons.refresh_rounded,
                    size: 20, color: PorterTheme.textTertiary),
                onPressed: flightProvider.refresh,
                tooltip: 'Refresh',
                style: IconButton.styleFrom(
                  minimumSize: const Size(36, 36),
                ),
              ),
            ],
          ),
        ),

        // Column headers.
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
          decoration: const BoxDecoration(
            border: Border(
              bottom: BorderSide(color: PorterTheme.surfaceBorder),
            ),
          ),
          child: const Row(
            children: [
              SizedBox(width: 80, child: Text('FLIGHT', style: _headerStyle)),
              SizedBox(width: 80, child: Text('AIRLINE', style: _headerStyle)),
              Expanded(child: Text('DESTINATION', style: _headerStyle)),
              SizedBox(width: 50, child: Text('GATE', style: _headerStyle)),
              SizedBox(width: 60, child: Text('TIME', style: _headerStyle)),
              SizedBox(
                  width: 80,
                  child: Text('STATUS', style: _headerStyle)),
            ],
          ),
        ),

        // Flight rows.
        Expanded(
          child: flights.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.flight_takeoff_rounded,
                          size: 40, color: PorterTheme.textTertiary),
                      const SizedBox(height: 12),
                      const Text('No flight data available',
                          style: TextStyle(color: PorterTheme.textSecondary)),
                    ],
                  ),
                )
              : ListView.separated(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  itemCount: flights.length,
                  separatorBuilder: (context, index) => const Divider(
                    height: 1,
                    indent: 20,
                    endIndent: 20,
                    color: PorterTheme.surfaceBorder,
                  ),
                  itemBuilder: (context, index) {
                    final flight = flights[index];
                    return _FlightRow(
                      flight: flight,
                      timeFormat: timeFormat,
                    );
                  },
                ),
        ),
      ],
    );
  }

  static const _headerStyle = TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w600,
    color: PorterTheme.textTertiary,
    letterSpacing: 1.2,
  );
}

class _FlightRow extends StatelessWidget {
  final FlightInfo flight;
  final DateFormat timeFormat;

  const _FlightRow({required this.flight, required this.timeFormat});

  Color get statusColor {
    switch (flight.status) {
      case 'Boarding':
        return PorterTheme.successGreen;
      case 'Delayed':
        return PorterTheme.emergencyRed;
      case 'Departed':
        return PorterTheme.textTertiary;
      default:
        return PorterTheme.accentCyan;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      child: Row(
        children: [
          SizedBox(
            width: 80,
            child: Text(
              flight.flightNumber,
              style: const TextStyle(
                fontWeight: FontWeight.w600,
                fontSize: 14,
                color: PorterTheme.textPrimary,
              ),
            ),
          ),
          SizedBox(
            width: 80,
            child: Text(
              flight.airline,
              style: const TextStyle(
                fontSize: 12,
                color: PorterTheme.textSecondary,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Expanded(
            child: Text(
              flight.destination,
              style: const TextStyle(
                fontSize: 14,
                color: PorterTheme.textPrimary,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          SizedBox(
            width: 50,
            child: Text(
              flight.gate,
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: PorterTheme.warningAmber,
              ),
            ),
          ),
          SizedBox(
            width: 60,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  timeFormat.format(flight.scheduledTime),
                  style: TextStyle(
                    fontSize: 14,
                    color: flight.estimatedTime != null
                        ? PorterTheme.textTertiary
                        : PorterTheme.textPrimary,
                    decoration: flight.estimatedTime != null
                        ? TextDecoration.lineThrough
                        : null,
                  ),
                ),
                if (flight.estimatedTime != null)
                  Text(
                    timeFormat.format(flight.estimatedTime!),
                    style: const TextStyle(
                      fontSize: 13,
                      color: PorterTheme.emergencyRed,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
              ],
            ),
          ),
          SizedBox(
            width: 80,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: statusColor.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                flight.status,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: statusColor,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
