// ignore_for_file: library_private_types_in_public_api, use_build_context_synchronously, unnecessary_import
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'firebase_options.dart';
import 'screens/login_page.dart';
import 'services/push_notification_service.dart';
import 'utils/navigation_helper.dart';
import 'utils/navigator_observer.dart';
import 'utils/app_theme.dart';

// 앱의 진입점
void main() async {
  // Flutter 엔진과 위젯 바인딩 초기화
  WidgetsFlutterBinding.ensureInitialized();

  // 한국어 날짜 형식 초기화
  await initializeDateFormatting('ko_KR', null);

  try {
    // Firebase 초기화
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );

    // 푸시 알림 서비스 초기화
    await PushNotificationService().initialize();

    debugPrint('앱 초기화 성공');
  } catch (e) {
    debugPrint('앱 초기화 중 오류 발생: $e');
  }

  // 앱 실행
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
  // 기본 테마 모드 설정
  ThemeMode _themeMode = ThemeMode.system;

  static const String themePreferenceKey = 'theme_mode';

  @override
  void initState() {
    super.initState();
    // 앱 시작시 저장된 테마 모드 불러오기
    _loadSavedThemeMode();
  }

  // 저장된 테마 모드를 불러오는 메서드
  Future<void> _loadSavedThemeMode() async {
    final prefs = await SharedPreferences.getInstance();
    final savedMode = prefs.getString(themePreferenceKey) ?? 'system';

    // 저장된 값에 따라 테마 모드 설정
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

  // 테마 모드를 로컬 저장소에 저장하는 메서드
  Future<void> _saveThemeMode(ThemeMode mode) async {
    final prefs = await SharedPreferences.getInstance();
    String modeString;

    // ThemeMode 열거형을 문자열로 변환
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

    // SharedPreferences에 저장
    await prefs.setString(themePreferenceKey, modeString);
  }

  @override
  Widget build(BuildContext context) {
    final app = MaterialApp(
      title: '스트리머 알림 앱',
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: _themeMode,
      builder: (context, child) {
        NavigationHelper().setContext(context);
        return child!;
      },
      navigatorObservers: [AppNavigatorObserver()],
      home: const LoginPage(),
    );

    // 웹에서는 최대 너비를 제한하는 컨테이너로 감싸기
    if (kIsWeb) {
      return Center(
        child: ClipRect(
          child: Container(
            constraints: BoxConstraints(
              maxWidth: 720, // 모바일 앱 스타일 너비 (조정 가능)
              maxHeight: double.infinity,
            ),
            child: app,
          ),
        ),
      );
    }

    // 앱에서는 그대로 반환
    return app;
  }
}
