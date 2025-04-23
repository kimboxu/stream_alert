// ignore_for_file: use_build_context_synchronously, library_private_types_in_public_api

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../utils/url_helper.dart';
import '../main.dart';
import '../theme_provider.dart';

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
  bool _isLoading = false;
  String _errorMessage = '';
  final TextEditingController _usernameController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadSettings();
    _usernameController.text = widget.username;
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _themeMode = prefs.getString('theme_mode') ?? 'system';
    });
  }

Future<void> _saveThemeMode(String mode) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString('theme_mode', mode);
  setState(() {
    _themeMode = mode;
  });
  
  // 전역 테마 변경
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

  Future<void> _updateUsername() async {
    if (_usernameController.text.trim() == widget.username) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('동일한 사용자 이름입니다.')));
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = '';
    });

    try {
      // 서버에 사용자 이름 업데이트 요청
      final normalizedWebhookUrl = UrlHelper.normalizeDiscordWebhookUrl(
        widget.discordWebhooksURL,
      );

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
        setState(() {
          _errorMessage = '사용자 이름 변경에 실패했습니다.';
        });
      }
    } catch (e) {
      setState(() {
        _errorMessage = '오류가 발생했습니다: $e';
      });
    } finally {
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
                  RadioListTile<String>(
                    title: Text('라이트 모드'),
                    value: 'light',
                    groupValue: _themeMode,
                    activeColor: Theme.of(context).primaryColor,
                    onChanged: (value) {
                      _saveThemeMode(value!);
                      // 변경 후 즉시 효과를 보기 위해 Provider나 상태관리 도구를 사용할 수도 있음
                      MyApp.of(context)?.setThemeMode(ThemeMode.light);
                    },
                  ),
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
                  TextField(
                    controller: _usernameController,
                    decoration: InputDecoration(
                      labelText: '사용자 이름',
                      border: OutlineInputBorder(),
                      helperText: '사용자 이름을 변경하려면 여기에 입력하세요',
                    ),
                  ),
                  SizedBox(height: 8),
                  if (_errorMessage.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8.0),
                      child: Text(
                        _errorMessage,
                        style: TextStyle(color: Colors.red),
                      ),
                    ),
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
