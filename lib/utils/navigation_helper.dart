import 'package:flutter/material.dart';
import '../screens/notifications_page.dart';

class NavigationHelper {
  // 싱글톤 패턴 구현
  static final NavigationHelper _instance = NavigationHelper._internal();
  
  factory NavigationHelper() {
    return _instance;
  }
  
  NavigationHelper._internal();
  
  // 현재 컨텍스트 저장 변수
  BuildContext? _currentContext;
  
  // 컨텍스트 설정 메서드
  void setContext(BuildContext context) {
    _currentContext = context;
  }
  
  // 알림 페이지로 이동하는 메서드
  void navigateToNotificationsPage() {
    if (_currentContext != null) {
      Navigator.push(
        _currentContext!,
        MaterialPageRoute(builder: (context) => NotificationsPage()),
      );
    } else {
      debugPrint('유효한 컨텍스트가 없어 화면 이동할 수 없습니다.');
    }
  }
}