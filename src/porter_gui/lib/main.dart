// Copyright 2026 VirtusCo
// Licensed under Apache-2.0

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'providers/providers.dart';
import 'screens/chat_screen.dart';
import 'screens/flight_info_screen.dart';
import 'screens/follow_me_screen.dart';
import 'screens/map_screen.dart';
import 'screens/status_screen.dart';
import 'services/ai_service.dart';
import 'services/ros_bridge_service.dart';
import 'theme/porter_theme.dart';
import 'widgets/widgets.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final rosBridge = RosBridgeService(
    url: const String.fromEnvironment(
      'ROS_BRIDGE_URL',
      defaultValue: 'ws://localhost:9090',
    ),
  );
  final aiService = AiService(
    baseUrl: const String.fromEnvironment(
      'AI_SERVER_URL',
      defaultValue: 'http://localhost:8085',
    ),
  );
  runApp(PorterApp(rosBridge: rosBridge, aiService: aiService));
}

/// Root Porter Robot GUI application.
class PorterApp extends StatelessWidget {
  final RosBridgeService rosBridge;
  final AiService aiService;

  const PorterApp({super.key, required this.rosBridge, required this.aiService});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(
            create: (_) => ConnectionProvider(rosBridge)),
        ChangeNotifierProvider(
            create: (_) => ChatProvider(rosBridge, aiService)),
        ChangeNotifierProvider(
            create: (_) => SystemStatusProvider(rosBridge)),
        ChangeNotifierProvider(
            create: (_) => EmergencyStopProvider(rosBridge)),
        ChangeNotifierProvider(
            create: (_) => FollowMeProvider(rosBridge)),
        ChangeNotifierProvider(
            create: (_) => FlightInfoProvider(rosBridge)),
      ],
      child: MaterialApp(
        title: 'Porter Robot',
        debugShowCheckedModeBanner: false,
        theme: PorterTheme.darkTheme,
        home: const PorterShell(),
      ),
    );
  }
}

/// Main shell — nav rail + content area + E-stop overlay.
class PorterShell extends StatefulWidget {
  const PorterShell({super.key});

  @override
  State<PorterShell> createState() => _PorterShellState();
}

class _PorterShellState extends State<PorterShell> {
  int _selectedIndex = 0;

  static const List<Widget> _screens = [
    ChatScreen(),
    FlightInfoScreen(),
    MapScreen(),
    StatusScreen(),
    FollowMeScreen(),
  ];

  @override
  void initState() {
    super.initState();
    // Auto-connect to rosbridge on start.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<ConnectionProvider>().connect();
    });
  }

  @override
  Widget build(BuildContext context) {
    final connection = context.watch<ConnectionProvider>();
    final eStop = context.watch<EmergencyStopProvider>();

    return Scaffold(
      body: Column(
        children: [
          // Connection banner (shown when disconnected).
          ConnectionBanner(
            connected: connection.connected,
            onReconnect: connection.connect,
          ),

          // Main content.
          Expanded(
            child: Row(
              children: [
                // Navigation rail.
                PorterNavRail(
                  selectedIndex: _selectedIndex,
                  onSelected: (i) => setState(() => _selectedIndex = i),
                ),

                // Screen content.
                Expanded(
                  child: Stack(
                    children: [
                      IndexedStack(
                        index: _selectedIndex,
                        children: _screens,
                      ),

                      // Emergency stop floating button (always visible).
                      Positioned(
                        bottom: 12,
                        right: 12,
                        child: _FloatingEStop(eStop: eStop),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Compact floating E-stop button — always visible in bottom-right.
class _FloatingEStop extends StatelessWidget {
  final EmergencyStopProvider eStop;

  const _FloatingEStop({required this.eStop});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: eStop.isEngaged ? () {} : eStop.engage,
      onLongPress: eStop.isEngaged ? () => _showDisengage(context) : null,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: 52,
        height: 52,
        decoration: BoxDecoration(
          color: eStop.isEngaged
              ? PorterTheme.emergencyRed
              : PorterTheme.surfaceCard,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: eStop.isEngaged
                ? PorterTheme.emergencyRed
                : PorterTheme.surfaceBorder,
            width: 2,
          ),
          boxShadow: eStop.isEngaged
              ? [
                  BoxShadow(
                    color: PorterTheme.emergencyRed.withValues(alpha: 0.4),
                    blurRadius: 12,
                    spreadRadius: 1,
                  ),
                ]
              : [],
        ),
        child: Icon(
          Icons.dangerous_rounded,
          size: 24,
          color: eStop.isEngaged ? Colors.white : PorterTheme.emergencyRed,
        ),
      ),
    );
  }

  void _showDisengage(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Disengage Emergency Stop?'),
        content: const Text(
          'Ensure the area around the robot is clear before disengaging.',
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
