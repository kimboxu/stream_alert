// ignore_for_file: use_build_context_synchronously, library_private_types_in_public_api

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../utils/url_helper.dart';
import '../main.dart';

class SettingsPage extends StatefulWidget {
  final String username;
  final String discordWebhooksURL;

  const SettingsPage({
    super.key,
    required this.username,
    required this.discordWebhooksURL,
  });

  @override
  _SettingsPageState createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  // 테마 설정용 변수
  String _themeMode = 'system'; // 'light', 'dark', 'system' 중 하나
  bool _isLoading = false; // 로딩 상태
  String _errorMessage = ''; // 오류 메시지
  final TextEditingController _usernameController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadSettings(); // 저장된 설정 불러오기
    _usernameController.text = widget.username; // 현재 사용자 이름 설정
  }

  // 저장된 테마 설정 불러오기
  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _themeMode = prefs.getString('theme_mode') ?? 'system';
    });
  }

  // 테마 모드 저장 및 적용
  Future<void> _saveThemeMode(String mode) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('theme_mode', mode);
    setState(() {
      _themeMode = mode;
    });
    
    // 전역 테마 변경 (MyApp 상태 업데이트)
    if (mode == 'light') {
      MyApp.of(context)?.setThemeMode(ThemeMode.light);
    } else if (mode == 'dark') {
      MyApp.of(context)?.setThemeMode(ThemeMode.dark);
    } else {
      MyApp.of(context)?.setThemeMode(ThemeMode.system);
    }
    
    // 변경 후 화면 다시 그리기 요청
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) setState(() {});
    });
  }

  // 사용자 이름 변경
  Future<void> _updateUsername() async {
    // 현재 이름과 같은 경우 무시
    if (_usernameController.text.trim() == widget.username) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('동일한 사용자 이름입니다.')));
      return;
    }

    // 로딩 상태 시작
    setState(() {
      _isLoading = true;
      _errorMessage = '';
    });

    try {
      // Discord 웹훅 URL 정규화
      final normalizedWebhookUrl = UrlHelper.normalizeDiscordWebhookUrl(
        widget.discordWebhooksURL,
      );

      // 서버에 사용자 이름 업데이트 요청
      final success = await ApiService.updateUsername(
        widget.username,
        normalizedWebhookUrl,
        _usernameController.text.trim(),
      );

      if (success) {
        // 로컬 저장소 업데이트
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('username', _usernameController.text.trim());

        // 성공 메시지
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('사용자 이름이 변경되었습니다.')));

        // 홈 화면으로 이동하며 새 사용자 이름 전달
        Navigator.pop(context, _usernameController.text.trim());
      } else {
        // 오류 메시지
        setState(() {
          _errorMessage = '사용자 이름 변경에 실패했습니다.';
        });
      }
    } catch (e) {
      // 예외 처리
      setState(() {
        _errorMessage = '오류가 발생했습니다: $e';
      });
    } finally {
      // 로딩 상태 종료
      setState(() {
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('설정')),
      body: ListView(
        padding: EdgeInsets.all(16.0),
        children: [
          // 테마 설정
          Card(
            child: Padding(
              padding: EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '테마 설정',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  SizedBox(height: 16),
                  // 라이트 모드 선택 옵션
                  RadioListTile<String>(
                    title: Text('라이트 모드'),
                    value: 'light',
                    groupValue: _themeMode,
                    activeColor: Theme.of(context).primaryColor,
                    onChanged: (value) {
                      _saveThemeMode(value!);
                      // 변경 후 즉시 효과를 보기 위해
                      MyApp.of(context)?.setThemeMode(ThemeMode.light);
                    },
                  ),
                  // 다크 모드 선택 옵션
                  RadioListTile<String>(
                    title: Text('다크 모드'),
                    value: 'dark',
                    groupValue: _themeMode,
                    activeColor: Theme.of(context).primaryColor,
                    onChanged: (value) {
                      _saveThemeMode(value!);
                      // 변경 후 즉시 효과를 보기 위해
                      MyApp.of(context)?.setThemeMode(ThemeMode.dark);
                    },
                  ),
                  // 시스템 설정 사용 옵션
                  RadioListTile<String>(
                    title: Text('시스템 설정 사용'),
                    value: 'system',
                    groupValue: _themeMode,
                    onChanged: (value) => _saveThemeMode(value!),
                  ),
                ],
              ),
            ),
          ),
          SizedBox(height: 16),
          // 사용자 정보
          Card(
            child: Padding(
              padding: EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '사용자 정보',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  SizedBox(height: 16),
                  // 사용자 이름 입력 필드
                  TextField(
                    controller: _usernameController,
                    decoration: InputDecoration(
                      labelText: '사용자 이름',
                      border: OutlineInputBorder(),
                      helperText: '사용자 이름을 변경하려면 여기에 입력하세요',
                    ),
                  ),
                  SizedBox(height: 8),
                  // 오류 메시지 표시
                  if (_errorMessage.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8.0),
                      child: Text(
                        _errorMessage,
                        style: TextStyle(color: Colors.red),
                      ),
                    ),
                  // 사용자 이름 변경 버튼
                  ElevatedButton(
                    onPressed: _isLoading ? null : _updateUsername,
                    child:
                        _isLoading
                            ? SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                            : Text('사용자 이름 변경'),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}