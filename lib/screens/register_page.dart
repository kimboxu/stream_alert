// ignore_for_file: library_private_types_in_public_api, use_build_context_synchronously, depend_on_referenced_packages

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../utils/url_helper.dart';
import 'home_page.dart';

class RegisterPage extends StatefulWidget {
  const RegisterPage({super.key});

  @override
  _RegisterPageState createState() => _RegisterPageState();
}

class _RegisterPageState extends State<RegisterPage> {
  final TextEditingController _usernameController = TextEditingController();
  final TextEditingController _webhookController = TextEditingController();
  String _message = '';
  bool _isLoading = false;
  bool _isError = false;

  Future<void> _register() async {
    setState(() {
      _isLoading = true;
      _message = '';
      _isError = false;
    });

    try {
      final normalizedWebhookUrl = UrlHelper.normalizeDiscordWebhookUrl(_webhookController.text);
      
      final response = await http.post(
        Uri.parse('${ApiService.baseUrl}/register'),
        body: {
          'username': _usernameController.text,
          'discordWebhooksURL': normalizedWebhookUrl,
        },
      );

      Map<String, dynamic> responseData = json.decode(response.body);

      if (response.statusCode == 200) {
        setState(() {
          _message = responseData['message'] ?? '회원가입 성공!';
          _isError = false;
        });
        
        // 회원가입 성공 시 로그인 정보 저장
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('username', _usernameController.text);
        await prefs.setString('discordWebhooksURL', normalizedWebhookUrl);
        
        // 회원가입 성공 시 홈 화면으로 이동
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (context) => HomePage(
              username: _usernameController.text,
              discordWebhooksURL: normalizedWebhookUrl,
            ),
          ),
        );
      } else {
        setState(() {
          _message = responseData['message'] ?? '회원가입 실패!';
          _isError = true;
        });
      }
    } catch (e) {
      setState(() {
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
    return Scaffold(
      appBar: AppBar(title: const Text('회원가입')),
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
              controller: _webhookController,
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
              onPressed: _isLoading ? null : _register,
              child: _isLoading
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Text('회원가입'),
            ),
          ],
        ),
      ),
    );
  }
}