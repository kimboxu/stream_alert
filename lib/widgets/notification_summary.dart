import 'package:flutter/material.dart';
import 'dart:convert';
import '../utils/string_helpers.dart';

class NotificationSummary extends StatelessWidget {
  final Map<String, Set<String>> selectedStreamers;
  final Map<String, Set<String>> selectedChzzkChatUsers;
  final Map<String, Set<String>> selectedAfreecaChatUsers;
  final dynamic youtubeAlarm; // 유튜브 알림 데이터 (문자열 또는 맵)
  final dynamic chzzkVod; // 치지직 VOD 데이터 (문자열 또는 맵)
  final dynamic cafeUserJson; // 카페 사용자 데이터 (문자열 또는 맵)
  
  const NotificationSummary({
    super.key,
    required this.selectedStreamers,
    this.selectedChzzkChatUsers = const {},
    this.selectedAfreecaChatUsers = const {},
    this.youtubeAlarm,
    this.chzzkVod,
    this.cafeUserJson,
  });
  
  @override
  Widget build(BuildContext context) {
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
                StringHelper.getSettingDisplayName(entry.key),
                entry.value.isEmpty ? '설정 없음' : entry.value.join(', '),
              );
            }),
            
            // 치지직 VOD 알림 설정
            _buildSectionTitle(context, '치지직 VOD 알림'),
            _buildVodSummary(context),
            
            // 유튜브 알림 설정
            _buildSectionTitle(context, '유튜브 알림'),
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
                  entry.key, // 스트리머 이름
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
                  entry.key, // 스트리머 이름
                  entry.value.isEmpty ? '설정 없음' : entry.value.join(', '),
                );
              }),
            ],
          ],
        ),
      ),
    );
  }

  // 치지직 VOD 요약 표시 (간소화된 형식)
  Widget _buildVodSummary(BuildContext context) {
    // 치지직 VOD 데이터 처리
    if (chzzkVod == null) {
      return _buildSummaryItem(context, '치지직 VOD', '설정 없음');
    }

    try {
      List<String> streamers = [];
      
      if (chzzkVod is String) {
        // 문자열 형식인 경우 (JSON 문자열)
        if (chzzkVod.isEmpty || chzzkVod == "{}") {
          return _buildSummaryItem(context, '치지직 VOD', '설정 없음');
        }
        
        // JSON 파싱 처리
        Map<String, dynamic>? vodMap = _safeParseJson(chzzkVod);
        if (vodMap != null) {
          // Map의 값을 통합하여 모든 스트리머 이름 목록 생성
          vodMap.forEach((_, value) {
            if (value is List) {
              streamers.addAll(List<String>.from(value));
            } else if (value is String) {
              streamers.add(value);
            }
          });
        }
      } else if (chzzkVod is Map) {
        // Map 형식인 경우
        Map<String, dynamic> vodMap = Map<String, dynamic>.from(chzzkVod);
        vodMap.forEach((_, value) {
          if (value is List) {
            streamers.addAll(List<String>.from(value));
          } else if (value is String) {
            streamers.add(value);
          }
        });
      }
      
      // 중복 제거 및 정렬
      streamers = streamers.toSet().toList()..sort();
      
      // 표시할 문자열 구성
      String displayText = streamers.isEmpty ? '설정 없음' : streamers.join(', ');
      
      return _buildSummaryItem(context, '치지직 VOD', displayText);
    } catch (e) {
      debugPrint('치지직 VOD 데이터 처리 중 오류: $e');
      return _buildSummaryItem(context, '치지직 VOD', '설정 오류');
    }
  }

  // 유튜브 알림 요약 표시 (간소화된 형식)
  Widget _buildYoutubeSummary(BuildContext context) {
    // 유튜브 알림 데이터 처리
    if (youtubeAlarm == null) {
      return _buildSummaryItem(context, '유튜브 알림', '설정 없음');
    }

    try {
      List<String> streamers = [];
      
      if (youtubeAlarm is String) {
        // 문자열 형식인 경우 (JSON 문자열)
        if (youtubeAlarm.isEmpty || youtubeAlarm == "{}") {
          return _buildSummaryItem(context, '유튜브 알림', '설정 없음');
        }
        
        // JSON 파싱 처리
        Map<String, dynamic>? youtubeMap = _safeParseJson(youtubeAlarm);
        if (youtubeMap != null) {
          // Map의 값을 통합하여 모든 스트리머 이름 목록 생성
          youtubeMap.forEach((_, value) {
            if (value is List) {
              streamers.addAll(List<String>.from(value));
            } else if (value is String) {
              streamers.add(value);
            }
          });
        }
      } else if (youtubeAlarm is Map) {
        // Map 형식인 경우
        Map<String, dynamic> youtubeMap = Map<String, dynamic>.from(youtubeAlarm);
        youtubeMap.forEach((_, value) {
          if (value is List) {
            streamers.addAll(List<String>.from(value));
          } else if (value is String) {
            streamers.add(value);
          }
        });
      }
      
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

  // 카페 알림 요약 표시 (간소화된 형식)
  Widget _buildCafeSummary(BuildContext context) {
    // 카페 알림 데이터 처리
    if (cafeUserJson == null) {
      return _buildSummaryItem(context, '카페 알림', '설정 없음');
    }

    try {
      Map<String, List<String>> cafeStreamers = {};
      
      if (cafeUserJson is String) {
        // 문자열 형식인 경우 (JSON 문자열)
        if (cafeUserJson.isEmpty || cafeUserJson == "{}") {
          return _buildSummaryItem(context, '카페 알림', '설정 없음');
        }
        
        // JSON 파싱 처리
        Map<String, dynamic>? cafeMap = _safeParseJson(cafeUserJson);
        if (cafeMap != null) {
          cafeMap.forEach((channelID, users) {
            if (users is List) {
              cafeStreamers[channelID] = List<String>.from(users);
            } else if (users is String) {
              cafeStreamers[channelID] = [users];
            }
          });
        }
      } else if (cafeUserJson is Map) {
        // Map 형식인 경우
        Map<String, dynamic> cafeMap = Map<String, dynamic>.from(cafeUserJson);
        cafeMap.forEach((channelID, users) {
          if (users is List) {
            cafeStreamers[channelID] = List<String>.from(users);
          } else if (users is String) {
            cafeStreamers[channelID] = [users];
          }
        });
      }
      
      if (cafeStreamers.isEmpty) {
        return _buildSummaryItem(context, '카페 알림', '설정 없음');
      }
      
      // 표시할 내용 구성
      List<Widget> items = [];
      cafeStreamers.forEach((channelID, users) {
        // 채널 ID를 레이블로, 사용자 목록을 값으로 표시
        items.add(_buildSummaryItem(
          context,
          channelID,
          users.join(', '),
        ),);
      });
      
      return Column(children: items);
    } catch (e) {
      debugPrint('카페 알림 데이터 처리 중 오류: $e');
      return _buildSummaryItem(context, '카페 알림', '설정 오류');
    }
  }
  
  // JSON 문자열을 안전하게 파싱하는 유틸리티 메서드
  Map<String, dynamic>? _safeParseJson(String jsonString) {
    try {
      // 1. 문자열 정리 (앞뒤 공백 제거)
      String trimmedJson = jsonString.trim();
      
      // 2. 작은 따옴표를 큰 따옴표로 변환 (Python 스타일 -> JSON 스타일)
      if (trimmedJson.contains("'")) {
        trimmedJson = trimmedJson.replaceAll("'", "\"");
      }
      
      // 3. JSON 파싱
      return json.decode(trimmedJson) as Map<String, dynamic>;
    } catch (e) {
      debugPrint('JSON 파싱 오류: $e');
      debugPrint('파싱 시도한 문자열: $jsonString');
      return null;
    }
  }
  
  Widget _buildSectionTitle(BuildContext context, String title) {
    return Padding(
      padding: const EdgeInsets.only(top: 16, bottom: 8),
      child: Text(
        title,
        style: TextStyle(fontWeight: FontWeight.bold),
      ),
    );
  }
  
  Widget _buildSummaryItem(BuildContext context, String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 1,
            child: Text(
              label,
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
          ),
          Expanded(
            flex: 2,
            child: Text(value),
          ),
        ],
      ),
    );
  }
}