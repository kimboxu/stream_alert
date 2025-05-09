// ignore_for_file: library_private_types_in_public_api, depend_on_referenced_packages, use_build_context_synchronously

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'register_page.dart';
import 'home_page.dart';
import '../services/api_service.dart';
import '../services/push_notification_service.dart';
import '../utils/url_helper.dart';
import '../utils/navigation_helper.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  _LoginPageState createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final TextEditingController _usernameController = TextEditingController();
  final TextEditingController _discordWebhooksURL = TextEditingController();
  bool _isLoading = false;
  bool _isCheckingAutologin = true;
  String _message = '';
  bool _isError = false;

  @override
  void initState() {
    super.initState();
    // 자동 로그인 체크
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _checkAutoLogin();
    });
  }

  // 자동 로그인 확인
  Future<void> _checkAutoLogin() async {
    try {
      final prefs = await SharedPreferences.getInstance();

      // 저장된 사용자 정보 가져오기
      final savedUsername = prefs.getString('username');
      final savedWebhookURL = prefs.getString('discordWebhooksURL');

      // 백그라운드 알림 클릭 여부 확인
      final notificationClicked =
          prefs.getBool('notification_clicked') ?? false;

      // 사용자 정보가 있으면 자동 로그인
      if (savedUsername != null && savedWebhookURL != null) {
        // 알림 클릭으로 앱이 시작된 경우 플래그 초기화
        if (notificationClicked) {
          await prefs.setBool('notification_clicked', false);
        }

        // 홈 페이지로 이동
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder:
                (context) => HomePage(
                  username: savedUsername,
                  discordWebhooksURL: savedWebhookURL,
                ),
          ),
        );

        // 알림 클릭으로 앱이 시작된 경우 알림 페이지로 추가 이동
        if (notificationClicked) {
          // 홈 페이지가 로드된 후에 알림 페이지로 이동
          Future.delayed(Duration(milliseconds: 500), () {
            NavigationHelper().navigateToNotificationsPage();
          });
        }
      } else {
        // 자동 로그인 불가능
        setState(() {
          _isCheckingAutologin = false;
        });
      }
    } catch (e) {
      debugPrint('자동 로그인 확인 중 오류: $e');
      setState(() {
        _isCheckingAutologin = false;
      });
    }
  }

  Future<void> _login() async {
    setState(() {
      _isLoading = true;
      _message = '';
      _isError = false;
    });

    try {
      // Discord 웹훅 URL 정규화
      final normalizedWebhookUrl = UrlHelper.normalizeDiscordWebhookUrl(
        _discordWebhooksURL.text,
      );

      final response = await http.post(
        Uri.parse('${ApiService.baseUrl}/login'),
        body: {
          'username': _usernameController.text,
          'discordWebhooksURL': normalizedWebhookUrl, // 정규화된 URL 사용
        },
      );

      debugPrint('응답 상태 코드: ${response.statusCode}');
      debugPrint('응답 본문: ${response.body}');

      Map<String, dynamic> responseData = json.decode(response.body);

      if (response.statusCode == 200) {
        setState(() {
          _message = responseData['message'] ?? '로그인 성공!';
          _isError = false;
        });

        // 로그인 정보 저장 (정규화된 URL 저장)
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('username', _usernameController.text);
        await prefs.setString('discordWebhooksURL', normalizedWebhookUrl);

        // 푸시 알림 초기화 및 서버 알림 가져오기
        final pushService = PushNotificationService();
        await pushService.registerToken();

        // 로그인 성공 시 홈 화면으로 이동
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder:
                (context) => HomePage(
                  username: _usernameController.text,
                  discordWebhooksURL: normalizedWebhookUrl,
                ),
          ),
        );
      } else {
        setState(() {
          _message = responseData['message'] ?? '로그인 실패!';
          _isError = true;
        });
      }
    } catch (e) {
      setState(() {
        debugPrint('예외 발생: $e');

        _message = '연결 오류: $e';
        _isError = true;
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isCheckingAutologin) {
      return Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      appBar: AppBar(title: const Text('로그인')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            TextField(
              controller: _usernameController,
              decoration: const InputDecoration(
                labelText: '사용자 이름',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 20),
            TextField(
              controller: _discordWebhooksURL,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: '디스코드 웹훅 URL',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 20),
            if (_message.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 20),
                child: Text(
                  _message,
                  style: TextStyle(
                    color: _isError ? Colors.red : Colors.green,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ElevatedButton(
              onPressed: _isLoading ? null : _login,
              child:
                  _isLoading
                      ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                      : const Text('로그인'),
            ),
            TextButton(
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (context) => const RegisterPage()),
                );
              },
              child: const Text('회원가입하기'),
            ),
          ],
        ),
      ),
    );
  }
}
