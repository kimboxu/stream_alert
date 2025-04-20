// main.dart
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
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
    if (kDebugMode) {
      print('앱 초기화 중 오류: $e');
    }
  }
  
  runApp(const MyApp());
}

// main.dart의 MyApp 클래스 수정
class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '스트리머 알림 앱',
      theme: ThemeData(
        // 라이트 테마
        primarySwatch: Colors.blue,
        primaryColor: Color(0xFF5865F2), // Discord 색상과 유사
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
      // 시스템 테마 따라가기
      themeMode: ThemeMode.system,
      home: const LoginPage(),
    );
  }
}