// ignore_for_file: unnecessary_import, use_build_context_synchronously

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'notification_settings_page.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'notifications_page.dart';
import 'settings_page.dart';
import '../utils/url_helper.dart';
import '../utils/navigation_helper.dart';
import '../services/push_notification_service.dart';

class HomePage extends StatefulWidget {
  final String username; // 사용자 이름
  final String discordWebhooksURL; // 디스코드 웹훅 URL

  const HomePage({
    super.key,
    required this.username,
    required this.discordWebhooksURL,
  });

  @override
  State<HomePage> createState() => HomePageState();
}

class HomePageState extends State<HomePage> with WidgetsBindingObserver {
  // 사용자 이름 상태 변수
  String _currentUsername = '';

  @override
  void initState() {
    super.initState();
    // 앱 생명주기 변화 감지를 위한 옵저버 등록
    WidgetsBinding.instance.addObserver(this);

    // 초기 사용자 이름 설정
    _currentUsername = widget.username;

    // 앱이 시작될 때 알림 새로고침
    WidgetsBinding.instance.addPostFrameCallback((_) {
      // 현재 컨텍스트 설정
      NavigationHelper().setContext(context);

      _refreshNotifications();
    });
  }

  // 사용자 이름 업데이트 메서드
  void updateUsername(String newUsername) {
    setState(() {
      _currentUsername = newUsername;
    });
  }

  @override
  void dispose() {
    // 옵저버 해제
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // 앱이 포그라운드로 돌아올 때마다 알림 새로고침
    if (state == AppLifecycleState.resumed) {
      _refreshNotifications();
    }
  }

  // 알림 데이터 새로고침
  Future<void> _refreshNotifications() async {
    final pushService = PushNotificationService();
    await pushService.loadNotifications(
      direction: LoadDirection.newer,
      pageSize: 50,
      currentPage: 1,
    );
  }

  @override
  Widget build(BuildContext context) {
    // 매 빌드마다 컨텍스트 갱신
    NavigationHelper().setContext(context);
    // Discord 웹훅 URL 정규화
    final normalizedWebhookUrl = UrlHelper.normalizeDiscordWebhookUrl(
      widget.discordWebhooksURL,
    );

    return Scaffold(
      appBar: AppBar(
        title: const Text('스트리머 알림 앱'),
        automaticallyImplyLeading: false,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(20.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // 프로필 아바타
              CircleAvatar(
                radius: 40,
                backgroundColor: Theme.of(context).primaryColor,
                child: Icon(Icons.person, size: 60, color: Colors.white),
              ),
              SizedBox(height: 20),
              Text(
                '$_currentUsername님 환영합니다!',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
              ),
              SizedBox(height: 10),
              Text(
                '스트리머 알림 설정을 관리하거나 로그아웃할 수 있습니다.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 15, color: Colors.grey[600]),
              ),
              SizedBox(height: 40),

              // 받은 알림 보기 버튼
              ElevatedButton.icon(
                onPressed: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (context) => NotificationsPage(),
                    ),
                  );
                },
                icon: Icon(Icons.notifications_active),
                label: const Text('받은 알림 보기'),
                style: ElevatedButton.styleFrom(
                  padding: EdgeInsets.symmetric(horizontal: 30, vertical: 15),
                  textStyle: TextStyle(fontSize: 16),
                  minimumSize: Size(250, 50),
                  backgroundColor: Colors.amber[700],
                ),
              ),
              SizedBox(height: 20),

              // 스트리머 알림 설정 버튼
              ElevatedButton.icon(
                onPressed: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder:
                          (context) => NotificationSettingsPage(
                            username: widget.username,
                            discordWebhooksURL: normalizedWebhookUrl,
                          ),
                    ),
                  );
                },
                icon: Icon(Icons.settings),
                label: const Text('스트리머 알림 설정'),
                style: ElevatedButton.styleFrom(
                  padding: EdgeInsets.symmetric(horizontal: 30, vertical: 15),
                  textStyle: TextStyle(fontSize: 16),
                  minimumSize: Size(250, 50),
                ),
              ),
              SizedBox(height: 20),

              // 앱 설정 버튼
              ElevatedButton.icon(
                onPressed: () async {
                  final result = await Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder:
                          (context) => SettingsPage(
                            username: _currentUsername,
                            discordWebhooksURL: normalizedWebhookUrl,
                          ),
                    ),
                  );

                  // 사용자 이름이 변경되었으면 업데이트
                  if (result != null && result is String) {
                    setState(() {
                      updateUsername(result);
                    });
                  }
                },
                icon: Icon(Icons.settings_applications),
                label: const Text('앱 설정'),
                style: ElevatedButton.styleFrom(
                  padding: EdgeInsets.symmetric(horizontal: 30, vertical: 15),
                  textStyle: TextStyle(fontSize: 16),
                  minimumSize: Size(250, 50),
                  backgroundColor: Colors.teal,
                ),
              ),
              SizedBox(height: 20),

              // 로그아웃 버튼
              OutlinedButton.icon(
                onPressed: () async {
                  bool confirm = await _showLogoutConfirmDialog(context);
                  if (confirm) {
                    _logout(context);
                  }
                },
                icon: Icon(Icons.logout),
                label: const Text('로그아웃'),
                style: OutlinedButton.styleFrom(
                  padding: EdgeInsets.symmetric(horizontal: 30, vertical: 15),
                  textStyle: TextStyle(fontSize: 16),
                  minimumSize: Size(250, 50),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // 로그아웃 확인 다이얼로그
  Future<bool> _showLogoutConfirmDialog(BuildContext context) async {
    return await showDialog<bool>(
          context: context,
          builder:
              (context) => AlertDialog(
                title: Text('로그아웃'),
                content: Text('정말 로그아웃 하시겠습니까?'),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(false),
                    child: Text('취소'),
                  ),
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(true),
                    child: Text('로그아웃'),
                  ),
                ],
              ),
        ) ??
        false;
  }

// 로그아웃 처리 메서드
  void _logout(BuildContext context) async {
    try {
      // 알림 서비스에서 토큰 제거
      final pushService = PushNotificationService();
      await pushService.removeToken();

      // 로컬 저장소에서 사용자 정보 제거
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('username');
      await prefs.remove('discordWebhooksURL');
      await prefs.remove('notifications');

      // 로그인 화면으로 이동
      Navigator.pushNamedAndRemoveUntil(context, '/', (route) => false);
    } catch (e) {
      debugPrint('로그아웃 중 오류: $e');
      // 오류가 발생해도 로그인 화면으로 이동
      Navigator.pushNamedAndRemoveUntil(context, '/', (route) => false);
    }
  }
}
