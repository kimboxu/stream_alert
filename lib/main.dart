// main.dart

// ignore_for_file: library_private_types_in_public_api, use_build_context_synchronously, unnecessary_import
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'firebase_options.dart';
import 'screens/login_page.dart';
import 'services/push_notification_service.dart';
import 'package:intl/date_symbol_data_local.dart';

void main() async {
  // Flutter 바인딩 초기화
  WidgetsFlutterBinding.ensureInitialized();

  await initializeDateFormatting('ko_KR', null);

  try {
    // Firebase 초기화
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );

    // 푸시 알림 서비스 초기화
    await PushNotificationService().initialize();
  } catch (e) {
      debugPrint('앱 초기화 중 오류: $e');
  }

  runApp(const MyApp());
}

class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  _MyAppState createState() => _MyAppState();

  // 전역에서 테마 모드를 변경할 수 있는 정적 메서드
  static _MyAppState? of(BuildContext context) =>
      context.findAncestorStateOfType<_MyAppState>();
}

class _MyAppState extends State<MyApp> {
  ThemeMode _themeMode = ThemeMode.system;

  @override
  void initState() {
    super.initState();
    // 초기 테마 모드 설정
    _setInitialThemeMode();
  }

  Future<void> _setInitialThemeMode() async {
    final prefs = await SharedPreferences.getInstance();
    final savedMode = prefs.getString('theme_mode') ?? 'system';

    setThemeMode(
      savedMode == 'light'
          ? ThemeMode.light
          : savedMode == 'dark'
          ? ThemeMode.dark
          : ThemeMode.system,
    );
  }

  // 테마 모드 변경 메서드
  void setThemeMode(ThemeMode mode) {
    setState(() {
      _themeMode = mode;
    });

    // 변경된 테마 모드 저장
    _saveThemeMode(mode);
  }

  Future<void> _saveThemeMode(ThemeMode mode) async {
    final prefs = await SharedPreferences.getInstance();
    String modeString;

    switch (mode) {
      case ThemeMode.light:
        modeString = 'light';
        break;
      case ThemeMode.dark:
        modeString = 'dark';
        break;
      default:
        modeString = 'system';
    }

    await prefs.setString('theme_mode', modeString);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '스트리머 알림 앱',
      theme: ThemeData(
        // 라이트 테마
        primarySwatch: Colors.blue,
        primaryColor: Color(0xFF5865F2),
        appBarTheme: AppBarTheme(
          color: Color(0xFF5865F2),
          elevation: 0,
          iconTheme: IconThemeData(color: Colors.white),
          titleTextStyle: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        cardTheme: CardTheme(
          elevation: 1,
          margin: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
            side: BorderSide(color: Colors.grey[300]!),
          ),
        ),
        scaffoldBackgroundColor: Color(0xFFF5F5F5),
        dividerColor: Colors.grey[300],
        visualDensity: VisualDensity.adaptivePlatformDensity,
      ),
      darkTheme: ThemeData(
        // 다크 테마
        brightness: Brightness.dark,
        primaryColor: Color(0xFF5865F2),
        colorScheme: ColorScheme.dark(
          primary: Color(0xFF5865F2),
          surface: Color(0xFF36393F),
          onSurface: Colors.white,
        ),
        appBarTheme: AppBarTheme(
          color: Color(0xFF2F3136),
          elevation: 0,
          titleTextStyle: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        cardTheme: CardTheme(
          elevation: 0,
          margin: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
            side: BorderSide(color: Colors.grey[800]!),
          ),
          color: Color(0xFF2D2D2D),
        ),
        scaffoldBackgroundColor: Color(0xFF36393F),
        dividerColor: Colors.grey[800],
        visualDensity: VisualDensity.adaptivePlatformDensity,
      ),
      // 현재 테마 모드 적용
      themeMode: _themeMode,
      home: const LoginPage(),
    );
  }
}
