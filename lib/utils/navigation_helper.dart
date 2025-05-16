import 'package:flutter/material.dart';
import '../screens/notifications_page.dart';

class NavigationHelper {
  // 싱글톤 패턴 구현
  static final NavigationHelper _instance = NavigationHelper._internal();

  factory NavigationHelper() {
    return _instance;
  }

  NavigationHelper._internal();

  // 현재 컨텍스트 저장 변수 (Navigator 조작에 필요)
  BuildContext? _currentContext;

  // 현재 경로 이름 저장 변수
  String _currentRouteName = '';

  // 글로벌 컨텍스트 설정 메서드
  void setContext(BuildContext context) {
    _currentContext = context;
  }

  // 현재 경로 이름 설정 메서드
  void setCurrentRouteName(String routeName) {
    _currentRouteName = routeName;
    debugPrint('현재 경로 업데이트: $routeName');
  }

  // 알림 페이지로 이동하는 메서드
  void navigateToNotificationsPage() {
    if (_currentContext != null) {
      // 이미 알림 페이지에 있는지 확인
      if (_currentRouteName == 'notifications_page') {
        debugPrint('이미 알림 페이지에 있어 이동하지 않음');
        return;
      }

      // 알림 페이지로 이동
      Navigator.push(
        _currentContext!,
        MaterialPageRoute(
          builder: (context) => NotificationsPage(),
          settings: RouteSettings(name: 'notifications_page'),
        ),
      );
    } else {
      debugPrint('유효한 컨텍스트가 없어 화면 이동할 수 없습니다.');
    }
  }
}
