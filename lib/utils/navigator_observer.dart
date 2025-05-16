import 'package:flutter/material.dart';
import 'navigation_helper.dart';

class AppNavigatorObserver extends NavigatorObserver {
  // 새 화면으로 이동 시 호출
  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didPush(route, previousRoute);
    _updateCurrentRoute(route);
    debugPrint('화면 이동: ${route.settings.name}');
  }
  
  // 화면 뒤로가기 시 호출
  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didPop(route, previousRoute);
    if (previousRoute != null) {
      _updateCurrentRoute(previousRoute);
      debugPrint('화면 뒤로가기: ${previousRoute.settings.name}');
    }
  }
  
  // 화면 교체 시 호출
  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    super.didReplace(newRoute: newRoute, oldRoute: oldRoute);
    if (newRoute != null) {
      _updateCurrentRoute(newRoute);
      debugPrint('화면 대체: ${newRoute.settings.name}');
    }
  }
  
  // 화면 제거 시 호출
  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didRemove(route, previousRoute);
    if (previousRoute != null) {
      _updateCurrentRoute(previousRoute);
      debugPrint('화면 제거: ${route.settings.name}');
    }
  }
  
  // 현재 경로 정보 업데이트
  void _updateCurrentRoute(Route<dynamic> route) {
    if (route.settings.name != null) {
      NavigationHelper().setCurrentRouteName(route.settings.name!);
    }
  }
}