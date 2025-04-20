// screens/notification_settings_page.dart
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
  // ignore: library_private_types_in_public_api
  _NotificationSettingsPageState createState() =>
      _NotificationSettingsPageState();
}

class _NotificationSettingsPageState extends State<NotificationSettingsPage> {
  bool _isLoading = true;
  String _errorMessage = '';

  // Settings data
  Map<String, dynamic> _settings = {};

  // Streamer list data
  List<StreamerData> _streamers = [];

  // Additional data
  List<CafeData> _cafeData = [];
  List<ChzzkVideo> _chzzkVideo = [];
  List<YoutubeData> _youtubeData = [];

  // Selected user maps
  final Map<String, Set<String>> _selectedChzzkVideoUsers = {};
  final Map<String, Set<String>> _selectedyoutubrUsers = {};
  final Map<String, Set<String>> _selectedCafeUsers = {};
  final Map<String, Set<String>> _selectedChzzkChatUsers = {};
  final Map<String, Set<String>> _selectedAfreecaChatUsers = {};

  // Available chat users
  final List<String> _availableChzzkChatUsers = [];
  final List<String> _availableAfreecaChatUsers = [];

  // Selected streamer data
  final Map<String, Set<String>> _selectedStreamers = {
    "뱅온 알림": {},
    "방제 변경 알림": {},
    "방종 알림": {},
  };

  // JSON controllers
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

  Future<void> _loadSettings() async {
    setState(() {
      _isLoading = true;
      _errorMessage = '';
    });

    try {
      await _fetchUserSettings();
      await _fetchStreamerData();
      _parseChatFilters();
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

  Future<void> _fetchUserSettings() async {
    try {
      // Discord 웹훅 URL 정규화 확인
      final normalizedWebhookUrl = UrlHelper.normalizeDiscordWebhookUrl(
        widget.discordWebhooksURL,
      );

      final data = await ApiService.getUserSettings(
        widget.username,
        normalizedWebhookUrl, // 정규화된 URL 사용
      );

      setState(() {
        _settings = data['settings'];

        // 디버깅을 위한 로그 추가
        if (kDebugMode) {
          print('서버에서 받은 설정 데이터:');
          _settings.forEach((key, value) {
            if (kDebugMode) {
              print('$key: $value');
            }
          });

          // 유튜브 알림과 VOD 데이터 형식 확인
          if (_settings.containsKey('유튜브 알림')) {
            print('유튜브 알림 데이터 타입: ${_settings['유튜브 알림'].runtimeType}');
            print('유튜브 알림 데이터: ${_settings['유튜브 알림']}');
          }

          if (_settings.containsKey('치지직 VOD')) {
            print('치지직 VOD 데이터 타입: ${_settings['치지직 VOD'].runtimeType}');
            print('치지직 VOD 데이터: ${_settings['치지직 VOD']}');
          }
        }

        // Set JSON controllers
        _youtubeJsonController.text =
            _settings['유튜브 알림'] is String
                ? _settings['유튜브 알림'] ?? '{}'
                : jsonEncode(_settings['유튜브 알림'] ?? {});

        _chzzkVideoJsonController.text =
            _settings['치지직 VOD'] is String
                ? _settings['치지직 VOD'] ?? '{}'
                : jsonEncode(_settings['치지직 VOD'] ?? {});

        _cafeJsonController.text =
            _settings['cafe_user_json'] is String
                ? _settings['cafe_user_json'] ?? '{}'
                : jsonEncode(_settings['cafe_user_json'] ?? {});

        _chatJsonController.text =
            _settings['chat_user_json'] is String
                ? _settings['chat_user_json'] ?? '{}'
                : jsonEncode(_settings['chat_user_json'] ?? {});

        // Parse selected streamers
        _parseSelectedStreamers();
      });
    } catch (e) {
      setState(() {
        _errorMessage = '설정을 불러오는데 실패했습니다: $e';
        if (kDebugMode) {
          print('설정 불러오기 오류: $e');
          print('오류 스택 트레이스: ${StackTrace.current}');
        }
      });
    }
  }

  int _retryCount = 0;
  final int _maxRetries = 3;

  // 수정된 _fetchStreamerData 메소드
  Future<void> _fetchStreamerData() async {
    try {
      setState(() {
        if (!_isLoading) {
          _isLoading = true;
        }
        _errorMessage = '';
      });

      final data = await ApiService.getStreamers();

      // 스트리머 데이터 파싱
      _streamers = ApiService.parseStreamers(data);
      _cafeData = ApiService.parseCafeData(data);
      _chzzkVideo = ApiService.parseChzzkVideo(data);
      _youtubeData = ApiService.parseYoutubeData(data);
      _processAvailableChatUsers(data);
      _initializeSelectedUsers();
      _parseSelectedJsons();

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
        if (kDebugMode) {
          print('스트리머 정보 로드 실패, 자동 재시도 $_retryCount/$_maxRetries');
        }
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

  void _processAvailableChatUsers(Map<String, dynamic> data) {
    // Process Chzzk chat users
    if (data['chzzkChatFilter'] != null) {
      List chzzkChatFilterList = data['chzzkChatFilter'];
      for (var item in chzzkChatFilterList) {
        if (item is Map && item.containsKey('channelName')) {
          String channelName = item['channelName'];
          _availableChzzkChatUsers.add(channelName);
        }
      }
    }

    // Process Afreeca chat users
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

  void _initializeSelectedUsers() {
    // Initialize cafe users map
    for (var cafe in _cafeData) {
      _selectedCafeUsers[cafe.channelID] = {};
    }

    // Initialize chzzk video users map
    for (var video in _chzzkVideo) {
      _selectedChzzkVideoUsers[video.channelID] = {};
    }

    // Initialize youtube users map
    for (var youtube in _youtubeData) {
      _selectedyoutubrUsers[youtube.channelID] = {};
    }
  }

  // _parseSelectedJsons 메서드 개선
  void _parseSelectedJsons() {
    try {
      // 로깅을 통한 디버깅 - 실제 데이터 형태 확인
      if (kDebugMode) {
        print('유튜브 알림 원본 데이터: ${_settings['유튜브 알림']}');
        print('치지직 VOD 원본 데이터: ${_settings['치지직 VOD']}');
        print('cafe_user_json 원본 데이터: ${_settings['cafe_user_json']}');
        print('chat_user_json 원본 데이터: ${_settings['chat_user_json']}');
      }

      // 유튜브 알림 파싱
      _parseYoutubeSettings();

      // 치지직 VOD 파싱
      _parseChzzkVideoSettings();

      // 카페 설정 파싱
      _parseCafeSettings();

      // 채팅 필터 파싱
      _parseChatFilters();
    } catch (e) {
      if (kDebugMode) {
        print('JSON 데이터 파싱 중 오류 발생: $e');
        print('오류 스택 트레이스: ${StackTrace.current}');
      }
    }
  }

  // 유튜브 설정 파싱
  void _parseYoutubeSettings() {
    try {
      var youtubeData = _settings['유튜브 알림'];
      if (youtubeData == null) return;

      // 스트리머 ID를 채널 ID로 변환하는 맵 생성
      Map<String, String> streamerToChannelId = {};
      for (var streamer in _streamers) {
        streamerToChannelId[streamer.name] = streamer.channelID;
      }

      Map<String, dynamic> youtubeMap = {};

      // 문자열인 경우
      if (youtubeData is String) {
        if (youtubeData.isEmpty) return;

        if (youtubeData.startsWith('{')) {
          // JSON 문자열 형식
          youtubeMap = json.decode(youtubeData);
        } else {
          // 쉼표로 구분된 문자열 형식 (이전 형식)
          List<String> channels = youtubeData.split(', ');

          // 첫 번째 스트리머에게 할당 (임시 해결책)
          if (_streamers.isNotEmpty && channels.isNotEmpty) {
            youtubeMap[_streamers[0].channelID] = channels;
          }
        }
      } else if (youtubeData is Map) {
        // 맵 형식
        youtubeMap = Map<String, dynamic>.from(youtubeData);
      }

      // 알림 설정 초기화
      _selectedyoutubrUsers.clear();

      // 채널 ID를 키로 사용하는 맵 처리
      youtubeMap.forEach((channelID, channels) {
        List<String> channelList = [];

        if (channels is List) {
          channelList = List<String>.from(channels);
        } else if (channels is String) {
          channelList = [channels];
        }

        if (channelList.isNotEmpty) {
          _selectedyoutubrUsers[channelID] = Set<String>.from(channelList);
        }
      });

      if (kDebugMode) {
        print('파싱된 유튜브 알림 데이터: $_selectedyoutubrUsers');
      }
    } catch (e) {
      if (kDebugMode) {
        print('유튜브 설정 파싱 중 오류: $e');
        print('오류 스택 트레이스: ${StackTrace.current}');
      }
    }
  }

  // 치지직 VOD 설정 파싱
  void _parseChzzkVideoSettings() {
    try {
      var vodData = _settings['치지직 VOD'];
      if (vodData == null) return;

      // 스트리머 ID를 채널 ID로 변환하는 맵 생성
      Map<String, String> streamerToChannelId = {};
      for (var streamer in _streamers) {
        streamerToChannelId[streamer.name] = streamer.channelID;
      }

      Map<String, dynamic> vodMap = {};

      // 문자열인 경우
      if (vodData is String) {
        if (vodData.isEmpty) return;

        if (vodData.startsWith('{')) {
          // JSON 문자열 형식
          vodMap = json.decode(vodData);
        } else {
          // 쉼표로 구분된 문자열 형식 (이전 형식)
          List<String> channels = vodData.split(', ');

          // 스트리머 이름을 채널 ID로 변환하여 맵 생성
          for (var streamerName in channels) {
            String channelId =
                streamerToChannelId[streamerName] ?? streamerName;
            vodMap[channelId] = [streamerName];
          }
        }
      } else if (vodData is Map) {
        // 맵 형식
        vodMap = Map<String, dynamic>.from(vodData);
      }

      // 알림 설정 초기화
      _selectedChzzkVideoUsers.clear();

      // 채널 ID를 키로 사용하는 맵 처리
      vodMap.forEach((channelID, channels) {
        List<String> channelList = [];

        if (channels is List) {
          channelList = List<String>.from(channels);
        } else if (channels is String) {
          channelList = [channels];
        }

        if (channelList.isNotEmpty) {
          _selectedChzzkVideoUsers[channelID] = Set<String>.from(channelList);
        }
      });

      if (kDebugMode) {
        print('파싱된 치지직 VOD 데이터: $_selectedChzzkVideoUsers');
      }
    } catch (e) {
      if (kDebugMode) {
        print('치지직 VOD 설정 파싱 중 오류: $e');
        print('오류 스택 트레이스: ${StackTrace.current}');
      }
    }
  }

  // 카페 설정 파싱 (간소화된 버전)
  void _parseCafeSettings() {
    try {
      if (_settings['cafe_user_json'] == null ||
          _settings['cafe_user_json'].isEmpty) {
        if (kDebugMode) {
          print('cafe_user_json이 비어있습니다.');
        }
        return;
      }

      var cafeData = _settings['cafe_user_json'];
      Map<String, dynamic> cafeUserJson = {};

      // 문자열 또는 Map 형식 처리
      if (cafeData is String) {
        // 문자열 형식인 경우
        String trimmedJson = cafeData.trim();

        // 디버깅을 위한 로그 추가
        if (kDebugMode) {
          print('원본 cafe_user_json: $trimmedJson');
        }

        // 빈 객체인 경우
        if (trimmedJson == "{}" || trimmedJson.isEmpty) {
          if (kDebugMode) {
            print('cafe_user_json이 빈 객체입니다.');
          }
          return;
        }

        // 작은 따옴표를 큰 따옴표로 변환하여 유효한 JSON 형식으로 만들기
        if (trimmedJson.contains("'")) {
          trimmedJson = trimmedJson.replaceAll("'", "\"");
        }

        try {
          cafeUserJson = json.decode(trimmedJson);
        } catch (e) {
          if (kDebugMode) {
            print('JSON 파싱 중 오류 발생: $e');
            print('파싱 실패한 JSON 문자열: $trimmedJson');
          }
          return;
        }
      } else if (cafeData is Map) {
        // 이미 Map 형식인 경우
        cafeUserJson = Map<String, dynamic>.from(cafeData);
      } else {
        // 지원하지 않는 형식
        if (kDebugMode) {
          print('지원하지 않는 cafe_user_json 형식: ${cafeData.runtimeType}');
        }
        return;
      }

      // 선택된 카페 사용자 초기화
      _selectedCafeUsers.clear();

      // 채널 ID를 키로 사용하는 맵 처리
      cafeUserJson.forEach((channelID, users) {
        if (users is List) {
          _selectedCafeUsers[channelID] = Set<String>.from(users);
        } else if (users is String) {
          _selectedCafeUsers[channelID] = {users};
        }
      });

      if (kDebugMode) {
        print('파싱된 카페 데이터: $_selectedCafeUsers');
      }
    } catch (e) {
      if (kDebugMode) {
        print('카페 설정 파싱 중 오류: $e');
        print('오류 스택 트레이스: ${StackTrace.current}');
      }
    }
  }

  // 채팅 필터 파싱 (간소화된 버전)
  void _parseChatFilters() {
    try {
      if (_settings['chat_user_json'] == null ||
          _settings['chat_user_json'].isEmpty) {
        if (kDebugMode) {
          print('chat_user_json이 비어있습니다.');
        }
        return;
      }

      var chatData = _settings['chat_user_json'];
      Map<String, dynamic> chatUserJson = {};

      // 문자열 또는 Map 형식 처리
      if (chatData is String) {
        // 문자열 형식인 경우
        String trimmedJson = chatData.trim();

        // 디버깅을 위한 로그 추가
        if (kDebugMode) {
          print('원본 chat_user_json: $trimmedJson');
        }

        // 빈 객체인 경우
        if (trimmedJson == "{}" || trimmedJson.isEmpty) {
          if (kDebugMode) {
            print('chat_user_json이 빈 객체입니다.');
          }
          return;
        }

        // 작은 따옴표를 큰 따옴표로 변환하여 유효한 JSON 형식으로 만들기
        if (trimmedJson.contains("'")) {
          trimmedJson = trimmedJson.replaceAll("'", "\"");
        }

        try {
          chatUserJson = json.decode(trimmedJson);
        } catch (e) {
          if (kDebugMode) {
            print('JSON 파싱 중 오류 발생: $e');
            print('파싱 실패한 JSON 문자열: $trimmedJson');
          }
          return;
        }
      } else if (chatData is Map) {
        // 이미 Map 형식인 경우
        chatUserJson = Map<String, dynamic>.from(chatData);
      } else {
        // 지원하지 않는 형식
        if (kDebugMode) {
          print('지원하지 않는 chat_user_json 형식: ${chatData.runtimeType}');
        }
        return;
      }

      // 채팅 필터 사용자 맵 초기화
      _selectedChzzkChatUsers.clear();
      _selectedAfreecaChatUsers.clear();

      // 새로운 형식 파싱 (채널 ID를 키로 사용)
      chatUserJson.forEach((key, users) {
        if (users is List) {
          // 채널 ID로 스트리머 찾기
          StreamerData? streamer = _findStreamerByChannelID(key);

          Set<String> userSet = Set<String>.from(users.where((u) => u != ""));

          if (streamer != null) {
            if (streamer.platform == 'chzzk') {
              _selectedChzzkChatUsers[streamer.name] = userSet;
            } else if (streamer.platform == 'afreeca') {
              _selectedAfreecaChatUsers[streamer.name] = userSet;
            }
          } else {
            // 채널 ID로 스트리머를 찾지 못한 경우
            // 이 경우는 key가 실제로 채널 이름일 수 있음
            bool isChzzk = _streamers.any(
              (s) => s.name == key && s.platform == 'chzzk',
            );
            bool isAfreeca = _streamers.any(
              (s) => s.name == key && s.platform == 'afreeca',
            );

            if (isChzzk) {
              _selectedChzzkChatUsers[key] = userSet;
            } else if (isAfreeca) {
              _selectedAfreecaChatUsers[key] = userSet;
            } else {
              // 플랫폼을 결정할 수 없는 경우, 기본적으로 치지직으로 처리
              _selectedChzzkChatUsers[key] = userSet;
            }
          }
        }
      });

      if (kDebugMode) {
        print('파싱된 치지직 채팅 필터: $_selectedChzzkChatUsers');
        print('파싱된 아프리카 채팅 필터: $_selectedAfreecaChatUsers');
      }
    } catch (e) {
      if (kDebugMode) {
        print('채팅 필터 파싱 중 오류: $e');
        print('오류 스택 트레이스: ${StackTrace.current}');
      }
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
    Map<String, dynamic> chatUserJson = {};

    // 채널 이름에서 채널 ID를 찾는 헬퍼 함수
    String findChannelIdByName(String channelName) {
      // 스트리머 목록에서 해당 이름을 가진 스트리머를 찾아 채널 ID 반환
      for (var streamer in _streamers) {
        if (streamer.name == channelName) {
          return streamer.channelID;
        }
      }
      // 찾지 못한 경우 이름 그대로 반환 (기본 동작 유지)
      return channelName;
    }

    // 치지직 채팅 필터 추가 (새로운 형식 - channelID 사용)
    if (_selectedChzzkChatUsers.isNotEmpty) {
      _selectedChzzkChatUsers.forEach((streamerName, users) {
        String channelID = findChannelIdByName(streamerName);
        if (users.isNotEmpty) {
          // 채널 ID를 키로 사용하고 채팅 사용자 목록을 값으로 설정
          chatUserJson[channelID] = users.toList();
        } else {
          // 빈 사용자 목록도 포함
          chatUserJson[channelID] = [""];
        }
      });
    }

    // 아프리카 채팅 필터 추가 (새로운 형식 - channelID 사용)
    if (_selectedAfreecaChatUsers.isNotEmpty) {
      _selectedAfreecaChatUsers.forEach((streamerName, users) {
        String channelID = findChannelIdByName(streamerName);
        if (users.isNotEmpty) {
          // 채널 ID를 키로 사용하고 채팅 사용자 목록을 값으로 설정
          chatUserJson[channelID] = users.toList();
        } else {
          // 빈 사용자 목록도 포함
          chatUserJson[channelID] = [""];
        }
      });
    }

    // 채팅 JSON 컨트롤러 업데이트
    _chatJsonController.text = json.encode(chatUserJson);
  }

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

      // Prepare settings data
      Map<String, dynamic> data = {
        'username': widget.username,
        'discordWebhooksURL': normalizedWebhookUrl, // 정규화된 URL 사용
      };

      // 기본 알림 설정을 텍스트로 변환
      _selectedStreamers.forEach((key, value) {
        data[key] = value.join(', ');
      });

      // 유튜브 알림, 치지직 VOD, 카페 설정, 채팅 필터는 JSON으로 저장
      // 이렇게 하면 서버 측에서의 처리와 일관성을 유지할 수 있습니다

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
      if (kDebugMode) {
        print('저장할 데이터:');
        print('유튜브 알림: ${data['유튜브 알림']}');
        print('치지직 VOD: ${data['치지직 VOD']}');
        print('카페 설정: ${data['cafe_user_json']}');
        print('채팅 필터: ${data['chat_user_json']}');
      }

      // Send to API
      bool success = await ApiService.saveUserSettings(data);

      if (success) {
        ScaffoldMessenger.of(
          // ignore: use_build_context_synchronously
          context,
        ).showSnackBar(const SnackBar(content: Text('설정이 저장되었습니다')));
      } else {
        setState(() {
          _errorMessage = '설정 저장에 실패했습니다';
        });
      }
    } catch (e) {
      setState(() {
        _errorMessage = '연결 오류: $e';
        if (kDebugMode) {
          print('설정 저장 중 오류: $e');
        }
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  void _openStreamerSettings(StreamerData streamer) {
    // Find relevant data for the selected streamer
    CafeData? cafeData;
    for (var cafe in _cafeData) {
      if (cafe.channelID == streamer.channelID) {
        cafeData = cafe;
        break;
      }
    }

    // Find chzzkVideo
    ChzzkVideo? chzzkVideo;
    for (var video in _chzzkVideo) {
      if (video.channelID == streamer.channelID) {
        chzzkVideo = video;
        break;
      }
    }

    // Find youtubeData
    YoutubeData? youtubeData;
    for (var youtube in _youtubeData) {
      if (youtube.channelID == streamer.channelID) {
        youtubeData = youtube;
        break;
      }
    }

    // Get selected users for this streamer
    Set<String> selectedCafeUsers =
        _selectedCafeUsers[streamer.channelID] ?? {};
    Set<String> selectedChzzkVideoUsers =
        _selectedChzzkVideoUsers[streamer.channelID] ?? {};
    Set<String> selectedyoutubrUsers =
        _selectedyoutubrUsers[streamer.channelID] ?? {};
    Set<String> selectedChzzkChatUsers =
        _selectedChzzkChatUsers[streamer.name] ?? {};
    Set<String> selectedAfreecaChatUsers =
        _selectedAfreecaChatUsers[streamer.name] ?? {};

    // Show dialog
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
                // 중요: 여기에서는 이름 기반 맵을 업데이트
                if (selectedUsers.isEmpty) {
                  _selectedChzzkChatUsers.remove(streamer.name);
                } else {
                  _selectedChzzkChatUsers[streamer.name] = selectedUsers;
                }
                _updateChatUserJson(); // 이 메서드에서 채널 ID로 변환됨
              });
            },
            onAfreecaChatUsersChanged: (selectedUsers) {
              setState(() {
                // 중요: 여기에서는 이름 기반 맵을 업데이트
                if (selectedUsers.isEmpty) {
                  _selectedAfreecaChatUsers.remove(streamer.name);
                } else {
                  _selectedAfreecaChatUsers[streamer.name] = selectedUsers;
                }
                _updateChatUserJson(); // 이 메서드에서 채널 ID로 변환됨
              });
            },
          ),
    ).then((_) {
      // After dialog is closed, update the _settings map with all the latest JSON controllers
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
          IconButton(
            icon: Icon(Icons.save),
            onPressed: _isLoading ? null : _saveSettings,
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  void _retryFetchData() {
    _retryCount = 0; // 재시도 카운트 초기화
    _fetchStreamerData(); // 데이터 다시 로드
  }

  Widget _buildBody() {
    if (_isLoading) {
      return Center(child: CircularProgressIndicator());
    } else if (_errorMessage.isNotEmpty) {
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
    } else {
      return ListView(
        padding: const EdgeInsets.all(16.0),
        children: [
          Text(
            '스트리머를 선택하여 알림 설정하기',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          SizedBox(height: 16),
          StreamerGrid(
            streamers: _streamers,
            selectedStreamers: _selectedStreamers,
            onStreamerTap: _openStreamerSettings,
          ),
          SizedBox(height: 24),
          // 수정된 NotificationSummary 위젯 사용
          NotificationSummary(
            selectedStreamers: _selectedStreamers,
            selectedChzzkChatUsers: _selectedChzzkChatUsers,
            selectedAfreecaChatUsers: _selectedAfreecaChatUsers,
            youtubeAlarm: _settings['유튜브 알림'],
            chzzkVod: _settings['치지직 VOD'],
            cafeUserJson: _settings['cafe_user_json'],
          ),
          SizedBox(height: 20),
          if (_errorMessage.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Text(_errorMessage, style: TextStyle(color: Colors.red)),
            ),
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