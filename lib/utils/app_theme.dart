import 'package:flutter/material.dart';

class AppTheme {
  // 앱에서 사용할 색상 상수
  static const Color primaryColor = Color(0xFF5865F2);
  static const Color lightBackgroundColor = Color(0xFFF5F5F5);
  static const Color darkBackgroundColor = Color(0xFF36393F);
  static const Color darkCardColor = Color(0xFF2D2D2D);
  static const Color darkSurfaceColor = Color(0xFF2F3136);

  // 라이트 테마 설정
  static final ThemeData lightTheme = ThemeData(
    primarySwatch: Colors.blue,
    primaryColor: primaryColor,
    appBarTheme: const AppBarTheme(
      color: primaryColor,
      elevation: 0,
      iconTheme: IconThemeData(color: Colors.white),
      titleTextStyle: TextStyle(
        color: Colors.white,
        fontSize: 18,
        fontWeight: FontWeight.w600,
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 1,
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: Colors.grey[300]!),
      ),
    ),
    scaffoldBackgroundColor: lightBackgroundColor,
    dividerColor: Colors.grey[300],
    visualDensity: VisualDensity.adaptivePlatformDensity,
  );

  // 다크 테마 설정
  static final ThemeData darkTheme = ThemeData(
    brightness: Brightness.dark,
    primaryColor: primaryColor,
    colorScheme: const ColorScheme.dark(
      primary: primaryColor,
      surface: darkSurfaceColor,
      onSurface: Colors.white,
    ),
    appBarTheme: const AppBarTheme(
      color: darkSurfaceColor,
      elevation: 0,
      titleTextStyle: TextStyle(
        color: Colors.white,
        fontSize: 18,
        fontWeight: FontWeight.w600,
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: Colors.grey[800]!),
      ),
      color: darkCardColor,
    ),
    scaffoldBackgroundColor: darkBackgroundColor,
    dividerColor: Colors.grey[800],
    visualDensity: VisualDensity.adaptivePlatformDensity,
  );
}