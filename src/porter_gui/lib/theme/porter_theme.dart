// Copyright 2026 VirtusCo
// Licensed under Apache-2.0

import 'package:flutter/material.dart';

/// Porter Robot theme — Perplexity-inspired dark minimal UI.
///
/// Optimized for 7-inch 800×480 touchscreen with large touch targets.
/// Near-black background, subtle surfaces, soft teal accent, clean typography.
class PorterTheme {
  PorterTheme._();

  // ── Core palette ──────────────────────────────────────────────────────
  static const Color primaryBlue = Color(0xFF20B2AA);    // Soft teal accent
  static const Color accentCyan = Color(0xFF2EC4B6);     // Bright teal
  static const Color emergencyRed = Color(0xFFEF4444);   // Modern red
  static const Color successGreen = Color(0xFF22C55E);   // Modern green
  static const Color warningAmber = Color(0xFFF59E0B);   // Modern amber

  // ── Surfaces ──────────────────────────────────────────────────────────
  static const Color surfaceDark = Color(0xFF191A1A);    // App background
  static const Color surfaceCard = Color(0xFF242626);    // Cards & panels
  static const Color surfaceElevated = Color(0xFF2E3030); // Elevated card
  static const Color surfaceBorder = Color(0xFF393B3B);  // Subtle borders

  // ── Text ──────────────────────────────────────────────────────────────
  static const Color textPrimary = Color(0xFFEEEEEE);   // Off-white
  static const Color textSecondary = Color(0xFF9B9B9B);  // Muted grey
  static const Color textTertiary = Color(0xFF6B6B6B);   // Hint text

  /// Target screen dimensions.
  static const double screenWidth = 800;
  static const double screenHeight = 480;

  /// Minimum touch target size (Material Design guideline).
  static const double minTouchTarget = 48;

  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      fontFamily: 'sans-serif',
      colorScheme: const ColorScheme.dark(
        primary: primaryBlue,
        secondary: accentCyan,
        error: emergencyRed,
        surface: surfaceDark,
        onPrimary: Colors.white,
        onSecondary: Colors.black,
        onError: Colors.white,
        onSurface: textPrimary,
      ),
      scaffoldBackgroundColor: surfaceDark,
      cardTheme: CardThemeData(
        color: surfaceCard,
        elevation: 0,
        margin: const EdgeInsets.all(4),
        shape: RoundedRectangleBorder(
          borderRadius: const BorderRadius.all(Radius.circular(16)),
          side: BorderSide(color: surfaceBorder.withValues(alpha: 0.5)),
        ),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: surfaceDark,
        foregroundColor: textPrimary,
        elevation: 0,
        centerTitle: false,
        toolbarHeight: 48,
      ),
      textTheme: const TextTheme(
        headlineLarge: TextStyle(
          fontSize: 28,
          fontWeight: FontWeight.w700,
          color: textPrimary,
          letterSpacing: -0.5,
        ),
        headlineMedium: TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: textPrimary,
          letterSpacing: -0.3,
        ),
        titleLarge: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: textPrimary,
        ),
        titleMedium: TextStyle(
          fontSize: 15,
          fontWeight: FontWeight.w500,
          color: textPrimary,
        ),
        bodyLarge: TextStyle(
          fontSize: 16,
          color: textPrimary,
          height: 1.5,
        ),
        bodyMedium: TextStyle(
          fontSize: 14,
          color: textSecondary,
          height: 1.4,
        ),
        bodySmall: TextStyle(
          fontSize: 12,
          color: textSecondary,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          minimumSize: const Size(minTouchTarget, minTouchTarget),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          backgroundColor: primaryBlue,
          foregroundColor: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(
          minimumSize: const Size(minTouchTarget, minTouchTarget),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surfaceCard,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(24),
          borderSide: const BorderSide(color: surfaceBorder),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(24),
          borderSide: const BorderSide(color: surfaceBorder),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(24),
          borderSide: const BorderSide(color: accentCyan, width: 1.5),
        ),
        hintStyle: const TextStyle(color: textTertiary, fontSize: 14),
      ),
      dividerTheme: const DividerThemeData(
        color: surfaceBorder,
        thickness: 1,
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: surfaceCard,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: surfaceCard,
        labelStyle: const TextStyle(color: textPrimary, fontSize: 13),
        side: const BorderSide(color: surfaceBorder),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      ),
    );
  }
}
