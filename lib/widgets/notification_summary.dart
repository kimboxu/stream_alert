import 'package:flutter/material.dart';
import '../utils/string_helpers.dart';
import '../models/streamer_data.dart';

class NotificationSummary extends StatelessWidget {
  // 알림 설정 데이터
  final Map<String, Set<String>> selectedStreamers; // 선택된 스트리머 정보
  final Map<String, Set<String>> selectedChzzkChatUsers; // 치지직 채팅 필터링 사용자
  final Map<String, Set<String>> selectedAfreecaChatUsers; // 아프리카 채팅 필터링 사용자
  final Map<String, dynamic> youtubeAlarm; // 유튜브 알림 설정
  final Map<String, dynamic> vodAlarm; // VOD 알림 설정
  final Map<String, dynamic> cafeUserJson; // 카페 알림 설정
  final List<StreamerData> allStreamers; // 스트리머 정보 목록

  const NotificationSummary({
    super.key,
    required this.selectedStreamers,
    this.selectedChzzkChatUsers = const {},
    this.selectedAfreecaChatUsers = const {},
    this.youtubeAlarm = const {},
    this.vodAlarm = const {},
    this.cafeUserJson = const {},
    required this.allStreamers,
  });

  // 채널 ID로 스트리머 이름 찾기
  String _getStreamerNameById(String channelId) {
    for (var streamer in allStreamers) {
      if (streamer.channelID == channelId) {
        return streamer.name;
      }
    }
    return channelId; // 못 찾으면 ID 그대로 반환
  }

  @override
  Widget build(BuildContext context) {
    // 모든 알림 설정을 요약한 카드 구성
    return Card(
      margin: EdgeInsets.all(8),
      child: Padding(
        padding: EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '알림 설정 요약',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            Divider(),
            // 기본 알림 설정
            ...selectedStreamers.entries.map((entry) {
              return _buildSummaryItem(
                context,
                StringHelper.getSettingDisplayName(entry.key), // 설정 이름 변환
                entry.value.isEmpty ? '설정 없음' : entry.value.join(', '),
              );
            }),

            // VOD 알림 설정
            _buildVodSummary(context),

            // 유튜브 알림 설정
            _buildYoutubeSummary(context),

            // 카페 알림 설정
            _buildSectionTitle(context, '카페 알림 설정'),
            _buildCafeSummary(context),

            // 치지직 채팅 필터 설정
            if (selectedChzzkChatUsers.isNotEmpty) ...[
              _buildSectionTitle(context, '치지직 채팅 필터'),
              ...selectedChzzkChatUsers.entries.map((entry) {
                return _buildSummaryItem(
                  context,
                  _getStreamerNameById(entry.key), // 채널 ID를 이름으로 변환
                  entry.value.isEmpty ? '설정 없음' : entry.value.join(', '),
                );
              }),
            ],

            // 아프리카 채팅 필터 설정
            if (selectedAfreecaChatUsers.isNotEmpty) ...[
              _buildSectionTitle(context, '아프리카 채팅 필터'),
              ...selectedAfreecaChatUsers.entries.map((entry) {
                return _buildSummaryItem(
                  context,
                  _getStreamerNameById(entry.key), // 채널 ID를 이름으로 변환
                  entry.value.isEmpty ? '설정 없음' : entry.value.join(', '),
                );
              }),
            ],
          ],
        ),
      ),
    );
  }

  // VOD 요약 표시
  Widget _buildVodSummary(BuildContext context) {
    // 값이 없거나 빈 맵인 경우
    if (vodAlarm.isEmpty) {
      return _buildSummaryItem(context, 'VOD 알림', '설정 없음');
    }

    try {
      List<String> streamers = [];

      // Map 처리
      vodAlarm.forEach((_, value) {
        if (value is List) {
          streamers.addAll(List<String>.from(value));
        } else if (value is String) {
          streamers.add(value);
        }
      });

      // 중복 제거 및 정렬
      streamers = streamers.toSet().toList()..sort();

      // 표시할 문자열 구성
      String displayText = streamers.isEmpty ? '설정 없음' : streamers.join(', ');

      return _buildSummaryItem(context, 'VOD 알림', displayText);
    } catch (e) {
      debugPrint('VOD 알림 데이터 처리 중 오류: $e');
      return _buildSummaryItem(context, 'VOD 알림', '설정 오류');
    }
  }

  // 유튜브 알림 요약 표시
  Widget _buildYoutubeSummary(BuildContext context) {
    // 값이 없거나 빈 맵인 경우
    if (youtubeAlarm.isEmpty) {
      return _buildSummaryItem(context, '유튜브 알림', '설정 없음');
    }

    try {
      List<String> streamers = [];

      // Map 처리
      youtubeAlarm.forEach((_, value) {
        if (value is List) {
          streamers.addAll(List<String>.from(value));
        } else if (value is String) {
          streamers.add(value);
        }
      });

      // 중복 제거 및 정렬
      streamers = streamers.toSet().toList()..sort();

      // 표시할 문자열 구성
      String displayText = streamers.isEmpty ? '설정 없음' : streamers.join(', ');

      return _buildSummaryItem(context, '유튜브 알림', displayText);
    } catch (e) {
      debugPrint('유튜브 알림 데이터 처리 중 오류: $e');
      return _buildSummaryItem(context, '유튜브 알림', '설정 오류');
    }
  }

  // 카페 알림 요약 표시
  Widget _buildCafeSummary(BuildContext context) {
    // 값이 없거나 빈 맵인 경우
    if (cafeUserJson.isEmpty) {
      return _buildSummaryItem(context, '카페 알림', '설정 없음');
    }

    try {
      Map<String, List<String>> cafeStreamers = {};

      // Map 처리
      cafeUserJson.forEach((channelID, users) {
        if (users is List) {
          cafeStreamers[_getStreamerNameById(channelID)] = List<String>.from(
            users,
          );
        } else if (users is String) {
          cafeStreamers[_getStreamerNameById(channelID)] = [users];
        }
      });

      if (cafeStreamers.isEmpty) {
        return _buildSummaryItem(context, '카페 알림', '설정 없음');
      }

      // 표시할 내용 구성
      List<Widget> items = [];
      cafeStreamers.forEach((streamerName, users) {
        // 스트리머 이름을 레이블로, 사용자 목록을 값으로 표시
        items.add(_buildSummaryItem(context, streamerName, users.join(', ')));
      });

      return Column(children: items);
    } catch (e) {
      debugPrint('카페 알림 데이터 처리 중 오류: $e');
      return _buildSummaryItem(context, '카페 알림', '설정 오류');
    }
  }

  // 섹션 제목 표시 위젯
  Widget _buildSectionTitle(BuildContext context, String title) {
    return Padding(
      padding: const EdgeInsets.only(top: 16, bottom: 8),
      child: Text(title, style: TextStyle(fontWeight: FontWeight.bold)),
    );
  }

  // 요약 항목 표시 위젯
  Widget _buildSummaryItem(BuildContext context, String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 1,
            child: Text(label, style: TextStyle(fontWeight: FontWeight.bold)),
          ),
          Expanded(flex: 2, child: Text(value)),
        ],
      ),
    );
  }
}
