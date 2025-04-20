import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../services/push_notification_service.dart';
import '../utils/url_helper.dart';
import '../widgets/settings_item.dart';

class PushNotificationSettingsPage extends StatefulWidget {
  final String username;
  final String discordWebhooksURL;

  const PushNotificationSettingsPage({
    super.key,
    required this.username,
    required this.discordWebhooksURL,
  });

  @override
  // ignore: library_private_types_in_public_api
  _PushNotificationSettingsPageState createState() =>
      _PushNotificationSettingsPageState();
}

class _PushNotificationSettingsPageState
    extends State<PushNotificationSettingsPage> {
  bool _isLoading = false;
  String _errorMessage = '';
  
  // 알림 설정 상태
  final Map<String, bool> _notificationSettings = {
    '뱅온 알림': true,
    '방제 변경 알림': true,
    '방종 알림': true,
    '유튜브 알림': true,
    '치지직 VOD': true,
    '카페 알림': true,
    '채팅 알림': true,
  };

  @override
  void initState() {
    super.initState();
    _initializePushService();
    _loadSettings();
  }

  Future<void> _initializePushService() async {
    try {
      final pushService = PushNotificationService();
      await pushService.initialize();
    } catch (e) {
      setState(() {
        _errorMessage = '푸시 알림 서비스 초기화 중 오류가 발생했습니다: $e';
      });
    }
  }

  Future<void> _loadSettings() async {
    setState(() {
      _isLoading = true;
      _errorMessage = '';
    });

    try {
      // 디스코드 웹훅 URL 정규화
      final normalizedWebhookUrl =
          UrlHelper.normalizeDiscordWebhookUrl(widget.discordWebhooksURL);

      // 사용자 설정 불러오기
      final data = await ApiService.getUserSettings(
        widget.username,
        normalizedWebhookUrl,
      );

      // 푸시 알림 설정 가져오기 (서버에서 추가적인 데이터 필요)
      if (data['settings'] != null && 
          data['settings']['push_notification_settings'] != null) {
        final pushSettings = data['settings']['push_notification_settings'];
        
        // 설정 적용
        if (pushSettings is Map) {
          pushSettings.forEach((key, value) {
            if (_notificationSettings.containsKey(key)) {
              _notificationSettings[key] = value as bool;
            }
          });
        }
      } else {
        // 기본값 사용
        _notificationSettings.updateAll((key, value) => true);
      }
    } catch (e) {
      setState(() {
        _errorMessage = '설정을 불러오는데 실패했습니다: $e';
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _saveSettings() async {
    setState(() {
      _isLoading = true;
      _errorMessage = '';
    });

    try {
      // 디스코드 웹훅 URL 정규화
      final normalizedWebhookUrl =
          UrlHelper.normalizeDiscordWebhookUrl(widget.discordWebhooksURL);

      // 설정 저장
      final success = await ApiService.savePushNotificationSettings(
        widget.username,
        normalizedWebhookUrl,
        _notificationSettings,
      );

      if (success) {
        // ignore: use_build_context_synchronously
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('알림 설정이 저장되었습니다')),
        );
      } else {
        setState(() {
          _errorMessage = '설정 저장에 실패했습니다';
        });
      }
    } catch (e) {
      setState(() {
        _errorMessage = '설정 저장 중 오류가 발생했습니다: $e';
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
      appBar: AppBar(
        title: const Text('푸시 알림 설정'),
        actions: [
          IconButton(
            icon: const Icon(Icons.save),
            onPressed: _isLoading ? null : _saveSettings,
            tooltip: '설정 저장',
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    return ListView(
      padding: const EdgeInsets.all(16.0),
      children: [
        const Text(
          '앱 푸시 알림 설정',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        const Text(
          '각 알림 유형별로 푸시 알림을 받을지 설정할 수 있습니다.',
          style: TextStyle(fontSize: 14, color: Colors.grey),
        ),
        const SizedBox(height: 16),
        ..._buildNotificationSettings(),
        const SizedBox(height: 16),
        if (_errorMessage.isNotEmpty)
          Container(
            padding: const EdgeInsets.all(8),
            margin: const EdgeInsets.only(bottom: 16),
            decoration: BoxDecoration(
              color: Colors.red.shade100,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              _errorMessage,
              style: const TextStyle(color: Colors.red),
            ),
          ),
        ElevatedButton(
          onPressed: _isLoading ? null : _saveSettings,
          child: _isLoading
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                )
              : const Text('설정 저장'),
        ),
      ],
    );
  }

  List<Widget> _buildNotificationSettings() {
    return _notificationSettings.entries.map((entry) {
      return Card(
        margin: const EdgeInsets.only(bottom: 8),
        child: SettingsCheckboxItem(
          title: entry.key,
          value: entry.value,
          onChanged: (value) {
            setState(() {
              _notificationSettings[entry.key] = value ?? true;
            });
          },
        ),
      );
    }).toList();
  }
}