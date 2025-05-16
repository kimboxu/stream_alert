// ignore_for_file: library_private_types_in_public_api, unnecessary_import, use_build_context_synchronously

import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import '../models/streamer_data.dart';
import '../models/cafe_data.dart';
import '../models/chzzk_video.dart';
import '../models/youtube_data.dart';
import '../services/api_service.dart';
import '../utils/json_helpers.dart';
import '../utils/url_helper.dart';
import '../utils/cache_helper.dart';
import '../widgets/streamer_grid.dart';
import '../widgets/notification_summary.dart';
import 'streamer_settings_dialog.dart';

class NotificationSettingsPage extends StatefulWidget {
  final String username;
  final String discordWebhooksURL;

  const NotificationSettingsPage({
    super.key,
    required this.username,
    required this.discordWebhooksURL,
  });

  @override
  _NotificationSettingsPageState createState() =>
      _NotificationSettingsPageState();
}

class _NotificationSettingsPageState extends State<NotificationSettingsPage> {
  // 상태 변수
  bool _isLoading = true;
  String _errorMessage = '';

  // 재시도 관련 변수
  int _retryCount = 0;
  final int _maxRetries = 3;

  // 설정 데이터
  Map<String, dynamic> _settings = {};

  // 스트리머 데이터
  List<StreamerData> _streamers = [];

  // 추가 데이터 모델
  List<CafeData> _cafeData = [];
  List<ChzzkVideo> _chzzkVideo = [];
  List<YoutubeData> _youtubeData = [];

  // 데이터 빠른 접근을 위한 맵
  final Map<String, CafeData> _cafeDataMap = {};
  final Map<String, ChzzkVideo> _chzzkVideoMap = {};
  final Map<String, YoutubeData> _youtubeDataMap = {};

  // 선택된 사용자 맵
  final Map<String, Set<String>> _selectedChzzkVideoUsers = {};
  final Map<String, Set<String>> _selectedyoutubrUsers = {};
  final Map<String, Set<String>> _selectedCafeUsers = {};
  final Map<String, Set<String>> _selectedChzzkChatUsers = {};
  final Map<String, Set<String>> _selectedAfreecaChatUsers = {};

  // 사용 가능한 채팅 사용자
  final List<String> _availableChzzkChatUsers = [];
  final List<String> _availableAfreecaChatUsers = [];

  // 선택된 스트리머 데이터
  final Map<String, Set<String>> _selectedStreamers = {
    "뱅온 알림": {}, // 방송 시작 알림
    "방제 변경 알림": {}, // 방송 제목 변경 알림
    "방종 알림": {}, // 방송 종료 알림
  };

  // JSON 컨트롤러 - JSON 형식으로 데이터 관리
  final TextEditingController _chzzkVideoJsonController =
      TextEditingController();
  final TextEditingController _youtubeJsonController = TextEditingController();
  final TextEditingController _cafeJsonController = TextEditingController();
  final TextEditingController _chatJsonController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  // 설정 데이터 로드
  Future<void> _loadSettings() async {
    setState(() {
      _isLoading = true;
      _errorMessage = '';
    });

    try {
      // 사용자 설정과 스트리머 데이터 모두 로드
      await _fetchUserSettings();
      await _fetchStreamerData();
    } catch (e) {
      setState(() {
        _errorMessage = '연결 오류: $e';
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  // 사용자 설정 데이터 가져오기
  Future<void> _fetchUserSettings() async {
    try {
      // Discord 웹훅 URL 정규화
      final normalizedWebhookUrl = UrlHelper.normalizeDiscordWebhookUrl(
        widget.discordWebhooksURL,
      );

      // API 서비스를 통해 설정 가져오기
      final data = await ApiService.getUserSettings(
        widget.username,
        normalizedWebhookUrl,
      );

      setState(() {
        _settings = data['settings'];

        debugPrint('서버에서 받은 설정 데이터:');
        _settings.forEach((key, value) {
          debugPrint('$key: $value');
        });

        // JSON 데이터 정규화 - 항상 Map 형태로 변환
        Map<String, dynamic> youtubeAlarm = _ensureJsonMap(_settings['유튜브 알림']);
        Map<String, dynamic> chzzkVod = _ensureJsonMap(_settings['치지직 VOD']);
        Map<String, dynamic> cafeUserJson = _ensureJsonMap(
          _settings['cafe_user_json'],
        );
        Map<String, dynamic> chatUserJson = _ensureJsonMap(
          _settings['chat_user_json'],
        );

        // JSON 컨트롤러 설정
        _youtubeJsonController.text = jsonEncode(
          youtubeAlarm.isEmpty ? {} : youtubeAlarm,
        );
        _chzzkVideoJsonController.text = jsonEncode(
          chzzkVod.isEmpty ? {} : chzzkVod,
        );
        _cafeJsonController.text = jsonEncode(
          cafeUserJson.isEmpty ? {} : cafeUserJson,
        );
        _chatJsonController.text = jsonEncode(
          chatUserJson.isEmpty ? {} : chatUserJson,
        );

        // 선택된 스트리머 파싱
        _parseSelectedStreamers();
      });
    } catch (e) {
      setState(() {
        _errorMessage = '설정을 불러오는데 실패했습니다: $e';
        debugPrint('설정 불러오기 오류: $e');
        debugPrint('오류 스택 트레이스: ${StackTrace.current}');
      });
    }
  }

  // JSON 데이터를 일관되게 Map으로 변환하는 유틸리티 함수
  Map<String, dynamic> _ensureJsonMap(dynamic value) {
    if (value == null) {
      return {};
    }

    if (value is Map) {
      return Map<String, dynamic>.from(value);
    }

    if (value is String) {
      if (value.isEmpty) {
        return {};
      }
      try {
        // 문자열이 JSON 형식이면 파싱
        if (value.trim().startsWith('{')) {
          return jsonDecode(value);
        }

        // 쉼표로 구분된 리스트 형식이면 빈 객체로 처리
        return {};
      } catch (e) {
        debugPrint('JSON 파싱 오류: $e');

        return {};
      }
    }

    return {};
  }

  // 스트리머 데이터 가져오기
  Future<void> _fetchStreamerData() async {
    try {
      setState(() {
        if (!_isLoading) {
          _isLoading = true;
        }
        _errorMessage = '';
      });

      // API에서 스트리머 데이터 가져오기
      final data = await ApiService.getStreamers();

      // 각 종류별 데이터 파싱
      _streamers = ApiService.parseStreamers(data);
      _cafeData = ApiService.parseCafeData(data);
      _chzzkVideo = ApiService.parseChzzkVideo(data);
      _youtubeData = ApiService.parseYoutubeData(data);

      // 채팅 필터링 사용자 데이터 처리
      _processAvailableChatUsers(data);
      _initializeSelectedUsers();
      _parseSelectedJsons();

      // 데이터 가공
      _processFetchedData();

      // 프로필 이미지 URL 수집
      List<String> imageUrls =
          _streamers
              .where((streamer) => streamer.profileImageUrl.isNotEmpty)
              .map((streamer) => streamer.profileImageUrl)
              .toList();

      // 백그라운드에서 이미지 미리 로드
      _preloadImagesInBackground(imageUrls);

      setState(() {
        _retryCount = 0;
        _isLoading = false;
      });
    } catch (e) {
      _retryCount++;

      if (_retryCount < _maxRetries) {
        // 자동 재시도
        debugPrint('스트리머 정보 로드 실패, 자동 재시도 $_retryCount/$_maxRetries');
        await Future.delayed(Duration(seconds: 2)); // 잠시 대기 후 재시도
        return _fetchStreamerData(); // 재귀적으로 다시 시도
      } else {
        setState(() {
          _isLoading = false;
          _errorMessage = '스트리머 정보를 가져오는 데 실패했습니다: $e';
        });
      }
    }
  }

  // 백그라운드에서 이미지 미리 로드
  void _preloadImagesInBackground(List<String> imageUrls) {
    // 메인 UI 스레드를 차단하지 않고 비동기로 실행
    Future.microtask(() async {
      await CacheHelper.preloadImages(imageUrls);
    });
  }

  // 선택된 스트리머 파싱
  void _parseSelectedStreamers() {
    _selectedStreamers.forEach((key, value) {
      value.clear();

      String settingsValue = _settings[key] ?? '';
      if (settingsValue.isNotEmpty) {
        List<String> streamerNames = settingsValue.split(', ');
        value.addAll(streamerNames);
      }
    });
  }

  // 채팅 필터 사용자 처리
  void _processAvailableChatUsers(Map<String, dynamic> data) {
    if (data['chzzkChatFilter'] != null) {
      List chzzkChatFilterList = data['chzzkChatFilter'];
      for (var item in chzzkChatFilterList) {
        if (item is Map && item.containsKey('channelName')) {
          String channelName = item['channelName'];
          _availableChzzkChatUsers.add(channelName);
        }
      }
    }

    if (data['afreecaChatFilter'] != null) {
      List afreecaChatFilterList = data['afreecaChatFilter'];
      for (var item in afreecaChatFilterList) {
        if (item is Map && item.containsKey('channelName')) {
          String channelName = item['channelName'];
          _availableAfreecaChatUsers.add(channelName);
        }
      }
    }
  }

  // 선택된 사용자 초기화
  void _initializeSelectedUsers() {
    for (var cafe in _cafeData) {
      _selectedCafeUsers[cafe.channelID] = {};
    }

    for (var video in _chzzkVideo) {
      _selectedChzzkVideoUsers[video.channelID] = {};
    }

    for (var youtube in _youtubeData) {
      _selectedyoutubrUsers[youtube.channelID] = {};
    }
  }

  // JSON 설정 파싱
  void _parseSelectedJsons() {
    try {
      // 각 JSON을 파싱
      _parseYoutubeSettings();
      _parseChzzkVideoSettings();
      _parseCafeSettings();
      _parseChatFilters();
    } catch (e) {
      debugPrint('JSON 데이터 파싱 중 오류 발생: $e');
      debugPrint('오류 스택 트레이스: ${StackTrace.current}');
    }
  }

  // 유튜브 설정 파싱
  void _parseYoutubeSettings() {
    try {
      // 빈 문자열 검사
      if (_youtubeJsonController.text.trim().isEmpty) {
        _youtubeJsonController.text = "{}"; // 유효한 빈 JSON 객체 설정
      }

      // JSON 문자열에서 맵으로 변환
      Map<String, dynamic> youtubeMap = jsonDecode(_youtubeJsonController.text);

      // 알림 설정 초기화
      _selectedyoutubrUsers.clear();

      // 채널 ID를 키로 사용하는 맵 처리
      youtubeMap.forEach((channelID, channels) {
        _selectedyoutubrUsers[channelID] = Set<String>.from(channels);
      });

      debugPrint('파싱된 유튜브 알림 데이터: $_selectedyoutubrUsers');
    } catch (e) {
      debugPrint('유튜브 설정 파싱 중 오류: $e');
      debugPrint('오류 스택 트레이스: ${StackTrace.current}');

      // 오류 발생 시 빈 맵으로 초기화
      _selectedyoutubrUsers.clear();
    }
  }

  // 치지직 VOD 설정 파싱
  void _parseChzzkVideoSettings() {
    try {
      // 빈 문자열 검사
      if (_chzzkVideoJsonController.text.trim().isEmpty) {
        _chzzkVideoJsonController.text = "{}"; // 유효한 빈 JSON 객체 설정
      }

      // JSON 문자열에서 맵으로 변환
      Map<String, dynamic> vodMap = jsonDecode(_chzzkVideoJsonController.text);

      // 알림 설정 초기화
      _selectedChzzkVideoUsers.clear();

      // 채널 ID를 키로 사용하는 맵 처리
      vodMap.forEach((channelID, channels) {
        _selectedChzzkVideoUsers[channelID] = Set<String>.from(channels);
      });

      debugPrint('파싱된 치지직 VOD 데이터: $_selectedChzzkVideoUsers');
    } catch (e) {
      debugPrint('치지직 VOD 설정 파싱 중 오류: $e');
      debugPrint('오류 스택 트레이스: ${StackTrace.current}');

      // 오류 발생 시 빈 맵으로 초기화
      _selectedChzzkVideoUsers.clear();
    }
  }

  // 카페 설정 파싱
  void _parseCafeSettings() {
    try {
      // 빈 문자열 검사
      if (_cafeJsonController.text.trim().isEmpty) {
        _cafeJsonController.text = "{}"; // 유효한 빈 JSON 객체 설정
      }

      // JSON 문자열에서 맵으로 변환
      Map<String, dynamic> cafeUserJson = jsonDecode(_cafeJsonController.text);

      // 선택된 카페 사용자 초기화
      _selectedCafeUsers.clear();

      // 채널 ID를 키로 사용하는 맵 처리
      cafeUserJson.forEach((channelID, users) {
        _selectedCafeUsers[channelID] = Set<String>.from(users);
      });

      debugPrint('파싱된 카페 데이터: $_selectedCafeUsers');
    } catch (e) {
      debugPrint('카페 설정 파싱 중 오류: $e');
      debugPrint('오류 스택 트레이스: ${StackTrace.current}');

      // 오류 발생 시 빈 맵으로 초기화
      _selectedCafeUsers.clear();
    }
  }

  // 채팅 필터 파싱
  void _parseChatFilters() {
    try {
      // 빈 문자열 검사
      if (_chatJsonController.text.trim().isEmpty) {
        _chatJsonController.text = "{}"; // 유효한 빈 JSON 객체 설정
      }

      // JSON 문자열에서 맵으로 변환
      Map<String, dynamic> chatUserJson = jsonDecode(_chatJsonController.text);

      // 채팅 필터 사용자 맵 초기화
      _selectedChzzkChatUsers.clear();
      _selectedAfreecaChatUsers.clear();

      // 채널 ID를 키로 사용하는 맵 처리
      chatUserJson.forEach((channelID, users) {
        if (users is List) {
          // 채널 ID로 스트리머 찾기
          StreamerData? streamer = _findStreamerByChannelID(channelID);

          Set<String> userSet = Set<String>.from(users.where((u) => u != ""));

          if (streamer != null) {
            if (streamer.platform == 'chzzk') {
              _selectedChzzkChatUsers[channelID] = userSet;
            } else if (streamer.platform == 'afreeca') {
              _selectedAfreecaChatUsers[channelID] = userSet;
            }
          }
        }
      });

      debugPrint('파싱된 치지직 채팅 필터: $_selectedChzzkChatUsers');
      debugPrint('파싱된 아프리카 채팅 필터: $_selectedAfreecaChatUsers');
    } catch (e) {
      debugPrint('채팅 필터 파싱 중 오류: $e');
      debugPrint('오류 스택 트레이스: ${StackTrace.current}');

      // 오류 발생 시 빈 맵으로 초기화
      _selectedChzzkChatUsers.clear();
      _selectedAfreecaChatUsers.clear();
    }
  }

  // 채널 ID로 스트리머 찾기
  StreamerData? _findStreamerByChannelID(String channelID) {
    for (var streamer in _streamers) {
      if (streamer.channelID == channelID) {
        return streamer;
      }
    }
    return null;
  }

  // JSON 컨트롤러 업데이트 함수들
  void _updateCafeUserJson() {
    JsonHelper.updateJsonFromSelectedUsers(
      _selectedCafeUsers,
      _cafeJsonController,
    );
  }

  void _updateChzzkVideoUserJson() {
    JsonHelper.updateJsonFromSelectedUsers(
      _selectedChzzkVideoUsers,
      _chzzkVideoJsonController,
    );
  }

  void _updateYoutubeUserJson() {
    JsonHelper.updateJsonFromSelectedUsers(
      _selectedyoutubrUsers,
      _youtubeJsonController,
    );
  }

  void _updateChatUserJson() {
    // 여러 채팅 필터 설정을 하나의 JSON으로 병합
    JsonHelper.updateJsonFromMultipleSelectedUsers([
      _selectedChzzkChatUsers,
      _selectedAfreecaChatUsers,
    ], _chatJsonController);
  }

  // 설정 저장
  Future<void> _saveSettings() async {
    setState(() {
      _isLoading = true;
      _errorMessage = '';
    });

    try {
      // Discord 웹훅 URL 정규화 확인
      final normalizedWebhookUrl = UrlHelper.normalizeDiscordWebhookUrl(
        widget.discordWebhooksURL,
      );

      // 저장할 설정 데이터 준비
      Map<String, dynamic> data = {
        'username': widget.username,
        'discordWebhooksURL': normalizedWebhookUrl, // 정규화된 URL 사용
      };

      // 기본 알림 설정을 텍스트로 변환
      _selectedStreamers.forEach((key, value) {
        data[key] = value.join(', '); // 스트리머 목록을 쉼표로 구분된 문자열로 변환
      });

      // 유튜브 알림 설정 저장
      _updateYoutubeUserJson();
      data['유튜브 알림'] = _youtubeJsonController.text;

      // 치지직 VOD 설정 저장
      _updateChzzkVideoUserJson();
      data['치지직 VOD'] = _chzzkVideoJsonController.text;

      // 카페 설정 저장
      _updateCafeUserJson();
      data['cafe_user_json'] = _cafeJsonController.text;

      // 채팅 필터 설정 저장
      _updateChatUserJson();
      data['chat_user_json'] = _chatJsonController.text;

      // 디버깅용 로그

      debugPrint('저장할 데이터:');
      debugPrint('유튜브 알림: ${data['유튜브 알림']}');
      debugPrint('치지직 VOD: ${data['치지직 VOD']}');
      debugPrint('카페 설정: ${data['cafe_user_json']}');
      debugPrint('채팅 필터: ${data['chat_user_json']}');

      // API 서비스를 통해 서버에 저장
      bool success = await ApiService.saveUserSettings(data);

      if (success) {
        // 성공 메시지 표시
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('설정이 저장되었습니다')));
      } else {
        // 오류 메시지 표시
        setState(() {
          _errorMessage = '설정 저장에 실패했습니다';
        });
      }
    } catch (e) {
      // 예외 처리
      setState(() {
        _errorMessage = '연결 오류: $e';

        debugPrint('설정 저장 중 오류: $e');
      });
    } finally {
      // 로딩 상태 해제
      setState(() {
        _isLoading = false;
      });
    }
  }

  // 데이터 처리 - 효율적인 접근을 위해 Map 구조로 변환
  void _processFetchedData() {
    // 기존 맵 초기화
    _cafeDataMap.clear();
    _chzzkVideoMap.clear();
    _youtubeDataMap.clear();

    // 맵 구성
    for (var cafe in _cafeData) {
      _cafeDataMap[cafe.channelID] = cafe;
    }

    for (var video in _chzzkVideo) {
      _chzzkVideoMap[video.channelID] = video;
    }

    for (var youtube in _youtubeData) {
      _youtubeDataMap[youtube.channelID] = youtube;
    }
  }

  // 스트리머 설정 다이얼로그 열기
  void _openStreamerSettings(StreamerData streamer) {
    String channelID = streamer.channelID;

    // 스트리머 관련 데이터 가져오기
    CafeData? cafeData = _cafeDataMap[channelID];
    ChzzkVideo? chzzkVideo = _chzzkVideoMap[channelID];
    YoutubeData? youtubeData = _youtubeDataMap[channelID];

    // 현재 선택된 사용자 목록 가져오기
    Set<String> selectedCafeUsers =
        _selectedCafeUsers[streamer.channelID] ?? {};
    Set<String> selectedChzzkVideoUsers =
        _selectedChzzkVideoUsers[streamer.channelID] ?? {};
    Set<String> selectedyoutubrUsers =
        _selectedyoutubrUsers[streamer.channelID] ?? {};
    Set<String> selectedChzzkChatUsers =
        _selectedChzzkChatUsers[streamer.channelID] ?? {};
    Set<String> selectedAfreecaChatUsers =
        _selectedAfreecaChatUsers[streamer.channelID] ?? {};

    // 설정 다이얼로그 표시
    showDialog(
      context: context,
      builder:
          (context) => StreamerSettingsDialog(
            streamer: streamer,
            selectedSettings: Map.fromEntries(
              _selectedStreamers.entries.map(
                (e) => MapEntry(e.key, e.value.contains(streamer.name)),
              ),
            ),
            onSettingsChanged: (settings) {
              setState(() {
                settings.forEach((key, isSelected) {
                  if (isSelected) {
                    _selectedStreamers[key]!.add(streamer.name);
                  } else {
                    _selectedStreamers[key]!.remove(streamer.name);
                  }
                });
              });
            },

            // 각종 데이터와 콜백 함수 전달
            cafeData: cafeData,
            chzzkVideo: chzzkVideo,
            youtubeData: youtubeData,
            selectedCafeUsers: selectedCafeUsers,
            selectedChzzkVideoUsers: selectedChzzkVideoUsers,
            selectedyoutubrUsers: selectedyoutubrUsers,
            selectedChzzkChatUsers: selectedChzzkChatUsers,
            selectedAfreecaChatUsers: selectedAfreecaChatUsers,
            availableChzzkChatUsers: _availableChzzkChatUsers,
            availableAfreecaChatUsers: _availableAfreecaChatUsers,
            onCafeUsersChanged: (selectedUsers) {
              setState(() {
                if (selectedUsers.isEmpty) {
                  _selectedCafeUsers.remove(streamer.channelID);
                } else {
                  _selectedCafeUsers[streamer.channelID] = selectedUsers;
                }
                _updateCafeUserJson();
              });
            },
            onChzzkVideoUsersChanged: (selectedUsers) {
              setState(() {
                if (selectedUsers.isEmpty) {
                  _selectedChzzkVideoUsers.remove(streamer.channelID);
                } else {
                  _selectedChzzkVideoUsers[streamer.channelID] = selectedUsers;
                }
                _updateChzzkVideoUserJson();
              });
            },
            onyoutubrUsersChanged: (selectedUsers) {
              setState(() {
                if (selectedUsers.isEmpty) {
                  _selectedyoutubrUsers.remove(streamer.channelID);
                } else {
                  _selectedyoutubrUsers[streamer.channelID] = selectedUsers;
                }
                _updateYoutubeUserJson();
              });
            },
            onChzzkChatUsersChanged: (selectedUsers) {
              setState(() {
                if (selectedUsers.isEmpty) {
                  _selectedChzzkChatUsers.remove(streamer.channelID);
                } else {
                  _selectedChzzkChatUsers[streamer.channelID] = selectedUsers;
                }
                _updateChatUserJson();
              });
            },
            onAfreecaChatUsersChanged: (selectedUsers) {
              setState(() {
                if (selectedUsers.isEmpty) {
                  _selectedAfreecaChatUsers.remove(streamer.channelID);
                } else {
                  _selectedAfreecaChatUsers[streamer.channelID] = selectedUsers;
                }
                _updateChatUserJson();
              });
            },
          ),
    ).then((_) {
      // 다이얼로그 닫힌 후 JSON 설정 업데이트
      setState(() {
        _settings['유튜브 알림'] = _youtubeJsonController.text;
        _settings['치지직 VOD'] = _chzzkVideoJsonController.text;
        _settings['cafe_user_json'] = _cafeJsonController.text;
        _settings['chat_user_json'] = _chatJsonController.text;
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('스트리머 알림 설정'),
        actions: [
          // 저장 버튼
          IconButton(
            icon: Icon(Icons.save),
            onPressed: _isLoading ? null : _saveSettings,
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  // 데이터 다시 불러오기
  void _retryFetchData() {
    _retryCount = 0; // 재시도 카운트 초기화
    _fetchStreamerData(); // 데이터 다시 로드
  }

  // 메인 화면 구성
  Widget _buildBody() {
    // 로딩 중 상태
    if (_isLoading) {
      return Center(child: CircularProgressIndicator());
    }
    // 오류 발생 상태
    else if (_errorMessage.isNotEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_errorMessage, style: TextStyle(color: Colors.red)),
            SizedBox(height: 16),
            ElevatedButton.icon(
              onPressed: _retryFetchData,
              icon: Icon(Icons.refresh),
              label: Text('다시 시도'),
            ),
          ],
        ),
      );
    }
    // 정상 상태
    else {
      return ListView(
        padding: const EdgeInsets.all(16.0),
        children: [
          Text(
            '스트리머를 선택하여 알림 설정하기',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          SizedBox(height: 16),
          // 스트리머 그리드 위젯
          StreamerGrid(
            streamers: _streamers,
            selectedStreamers: _selectedStreamers,
            onStreamerTap: _openStreamerSettings,
          ),
          SizedBox(height: 24),
          // 알림 설정 요약 위젯
          NotificationSummary(
            selectedStreamers: _selectedStreamers,
            selectedChzzkChatUsers: _selectedChzzkChatUsers,
            selectedAfreecaChatUsers: _selectedAfreecaChatUsers,
            youtubeAlarm: jsonDecode(_youtubeJsonController.text),
            chzzkVod: jsonDecode(_chzzkVideoJsonController.text),
            cafeUserJson: jsonDecode(_cafeJsonController.text),
            allStreamers: _streamers,
          ),
          SizedBox(height: 20),
          // 오류 메시지 표시
          if (_errorMessage.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Text(_errorMessage, style: TextStyle(color: Colors.red)),
            ),
          // 저장 버튼
          ElevatedButton(
            onPressed: _isLoading ? null : _saveSettings,
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
                    : Text('설정 저장'),
          ),
        ],
      );
    }
  }
}
