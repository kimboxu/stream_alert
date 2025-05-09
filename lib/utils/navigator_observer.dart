//네비게이션 상태 모니터링 및 추적
import 'package:flutter/material.dart';
import 'navigation_helper.dart';

class AppNavigatorObserver extends NavigatorObserver {
  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didPush(route, previousRoute);
    _updateCurrentRoute(route);
    debugPrint('화면 이동: ${route.settings.name}');
  }
  
  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didPop(route, previousRoute);
    if (previousRoute != null) {
      _updateCurrentRoute(previousRoute);
      debugPrint('화면 뒤로가기: ${previousRoute.settings.name}');
    }
  }
  
  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    super.didReplace(newRoute: newRoute, oldRoute: oldRoute);
    if (newRoute != null) {
      _updateCurrentRoute(newRoute);
      debugPrint('화면 대체: ${newRoute.settings.name}');
    }
  }
  
  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didRemove(route, previousRoute);
    if (previousRoute != null) {
      _updateCurrentRoute(previousRoute);
      debugPrint('화면 제거: ${route.settings.name}');
    }
  }
  
  void _updateCurrentRoute(Route<dynamic> route) {
    if (route.settings.name != null) {
      NavigationHelper().setCurrentRouteName(route.settings.name!);
    }
  }
}