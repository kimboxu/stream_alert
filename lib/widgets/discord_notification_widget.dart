// ignore_for_file: avoid_print

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../models/notification_model.dart';
import 'package:url_launcher/url_launcher.dart';

/// 디스코드 스타일의 알림 위젯
/// NotificationModel을 입력받아 디스코드와 유사한 UI로 표시합니다.
class DiscordNotificationWidget extends StatelessWidget {
  final NotificationModel notification;
  final Function()? onTap; // 알림 클릭 시 콜백

  const DiscordNotificationWidget({
    super.key,
    required this.notification,
    this.onTap,
  });
  //색상 코드 10 -> 16 진수 변환
  Color parseColor(int rawColor) {
    // 알파값이 없으면 불투명으로 채워준다
    if (rawColor <= 0xFFFFFF) {
      return Color(0xFF000000 | rawColor);
    } else {
      return Color(rawColor);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDarkMode = theme.brightness == Brightness.dark;

    // 알림에 색상 정보가 있으면 사용, 없으면 기본 색상 사용
    final borderColor = parseColor(notification.color);

    final cardBgColor = isDarkMode ? Color(0xFF2D2D2D) : Colors.white;

    return Card(
      margin: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      elevation: 2,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(
          color: borderColor,
          width: notification.isRichNotification ? 2 : 1,
        ),
      ),
      color: cardBgColor,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 상단 헤더 (사용자명과 아바타)
            _buildHeader(context, isDarkMode),

            // 리치 알림(임베드)이 있는 경우 표시
            if (notification.isRichNotification)
              _buildRichNotification(context, isDarkMode, borderColor),

            // 일반 텍스트 컨텐츠
            if (notification.content.isNotEmpty &&
                !notification.isRichNotification)
              Padding(
                padding: const EdgeInsets.all(12.0),
                child: Text(
                  _processEmoji(notification.content), // 이모지 처리 함수 적용
                  style: TextStyle(
                    color: isDarkMode ? Colors.white70 : Colors.black87,
                  ),
                ),
              ),

            // 푸터 (아직 미구현된 경우)
            if (notification.footerText.isNotEmpty &&
                !notification.isRichNotification)
              _buildFooter(context, isDarkMode),
          ],
        ),
      ),
    );
  }

  // 헤더 위젯 (사용자명, 아바타, 시간)
  Widget _buildHeader(BuildContext context, bool isDarkMode) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
      child: Row(
        children: [
          // 아바타
          CircleAvatar(
            backgroundImage:
                notification.avatarUrl.isNotEmpty
                    ? NetworkImage(notification.avatarUrl)
                    : null,
            radius: 14,
            backgroundColor: isDarkMode ? Colors.grey[800] : Colors.grey[200],
            child:
                notification.avatarUrl.isEmpty
                    ? Icon(
                      Icons.person,
                      size: 16,
                      color: isDarkMode ? Colors.white70 : Colors.grey[700],
                    )
                    : null,
          ),
          SizedBox(width: 8),

          // 사용자명
          Expanded(
            child: Text(
              notification.username,
              style: TextStyle(
                fontWeight: FontWeight.bold,
                fontSize: 14,
                color: isDarkMode ? Colors.white : Colors.black87,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),

          // 타임스탬프
          Text(
            _formatTimestamp(notification.timestamp),
            style: TextStyle(
              color: isDarkMode ? Colors.grey[400] : Colors.grey[600],
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  // 리치 알림 위젯 (임베드)
  // 리치 알림 전체를 Stack으로 감싸고
  Widget _buildRichNotification(
    BuildContext context,
    bool isDarkMode,
    Color borderColor,
  ) {
    return Stack(
      children: [
        Container(
          padding: const EdgeInsets.all(8.0),
          margin: const EdgeInsets.fromLTRB(8, 4, 8, 8),
          decoration: BoxDecoration(
            border: Border(left: BorderSide(color: borderColor, width: 4)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 작성자, 제목, 설명, 필드
              if (notification.authorName.isNotEmpty) ...[
                InkWell(
                  onTap: () => _launchUrl(notification.authorUrl),
                  child: Text(
                    notification.authorName,
                    style: TextStyle(
                      fontWeight: FontWeight.w500,
                      color: isDarkMode ? Colors.grey[300] : Colors.grey[700],
                      fontSize: 14,
                    ),
                  ),
                ),
                SizedBox(height: 6),
              ],
              // 제목
              if (notification.title.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(right: 80.0, bottom: 8.0),
                  child:
                      notification.url.isNotEmpty
                          ? InkWell(
                            // URL이 있을 때만 InkWell 적용
                            onTap: () => _launchUrl(notification.url),
                            child: Text(
                              _processEmoji(notification.title),
                              style: TextStyle(
                                fontWeight: FontWeight.bold,
                                color:
                                    isDarkMode
                                        ? Colors.lightBlue[300]
                                        : Colors.blue[700],
                                fontSize: 16,
                              ),
                            ),
                          )
                          : Text(
                            // URL이 없을 때는 일반 텍스트로 표시하고 색상도 변경
                            _processEmoji(notification.title),
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              color:
                                  isDarkMode
                                      ? Colors.grey[300]
                                      : Colors
                                          .grey[800], // 링크가 아닌 일반 텍스트 색상으로 변경
                              fontSize: 16,
                            ),
                          ),
                ),
              if (notification.description.isNotEmpty)
                Text(
                  _processEmoji(notification.description), // 이모지 처리 함수 적용
                  style: TextStyle(
                    color: isDarkMode ? Colors.white70 : Colors.black87,
                  ),
                ),
              if (notification.fields != null)
                ..._buildFields(notification.fields, isDarkMode),
              if (notification.imageUrl.isNotEmpty) ...[
                SizedBox(height: 8),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: Image.network(
                    notification.imageUrl,
                    fit: BoxFit.cover,
                    errorBuilder:
                        (context, error, stackTrace) =>
                            Container(height: 120, color: Colors.grey),
                  ),
                ),
              ],
              if (notification.footerText.isNotEmpty)
                _buildFooter(context, isDarkMode),
            ],
          ),
        ),
        // 썸네일을 오른쪽 상단에 고정
        if (notification.thumbnailUrl.isNotEmpty)
          Positioned(
            top: 12,
            right: 12,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: Image.network(
                notification.thumbnailUrl,
                width: 60,
                height: 60,
                fit: BoxFit.cover,
                errorBuilder:
                    (context, error, stackTrace) =>
                        Container(width: 60, height: 60, color: Colors.grey),
              ),
            ),
          ),
      ],
    );
  }

  // 필드 목록 위젯
  List<Widget> _buildFields(dynamic fields, bool isDarkMode) {
    List<Widget> fieldWidgets = [];

    try {
      if (fields is List) {
        // 리스트 형태일 경우
        for (var field in fields) {
          if (field is Map &&
              field.containsKey('name') &&
              field.containsKey('value')) {
            fieldWidgets.add(
              Padding(
                padding: const EdgeInsets.only(bottom: 8.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _processEmoji(field['name']!.toString()),
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        color: isDarkMode ? Colors.white : Colors.black87,
                        fontSize: 14,
                      ),
                    ),
                    Text(
                      field['value']?.toString() ?? '',
                      style: TextStyle(
                        color: isDarkMode ? Colors.white70 : Colors.black87,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              ),
            );
          }
        }
      }
    } catch (e) {
      print('필드 처리 중 오류: $e');
    }

    return fieldWidgets;
  }

  // 푸터 위젯 - 변경된 부분
  Widget _buildFooter(BuildContext context, bool isDarkMode) {
    // 타임스탬프 찾기 시도 - 임베드의 timestamp 사용
    DateTime? embedTimestamp;

    // 먼저 임베드 데이터에서 timestamp 필드 직접 찾기
    if (notification.embedData != null &&
        notification.embedData!.containsKey('timestamp')) {
      try {
        String timestampStr = notification.embedData!['timestamp'].toString();
        embedTimestamp = DateTime.parse(timestampStr);
      } catch (e) {
        print('임베드 타임스탬프 파싱 오류: $e');
      }
    }

    // 임베드 타임스탬프가 있으면 사용, 없으면 알림 타임스탬프 사용
    final displayTimestamp = embedTimestamp ?? notification.timestamp;

    return Padding(
      padding: const EdgeInsets.all(8.0),
      child: Row(
        children: [
          if (notification.footerIconUrl.isNotEmpty)
            Container(
              width: 16,
              height: 16,
              margin: const EdgeInsets.only(right: 8.0),
              child: Image.network(
                notification.footerIconUrl,
                errorBuilder:
                    (context, error, stackTrace) =>
                        SizedBox(width: 16, height: 16),
              ),
            ),
          Text(
            // 수정된 부분: 임베드 타임스탬프 또는 알림 타임스탬프 사용
            "${notification.footerText} • ${_formatTimestamp(displayTimestamp)}",
            style: TextStyle(
              color: isDarkMode ? Colors.grey[400] : Colors.grey[600],
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  // URL 실행 함수
  void _launchUrl(String url) async {
    if (url.isEmpty) return;

    try {
      final uri = Uri.parse(url);
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (e) {
      print('🚫 URL 실행 중 오류: $e');
    }
  }

  // 시간 포맷팅 함수
  String _formatTimestamp(DateTime timestamp) {
    // UTC 타임스탬프를 로컬 시간으로 변환
    final localTimestamp = timestamp.toLocal();

    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final yesterday = today.subtract(Duration(days: 1));
    final messageDate = DateTime(
      localTimestamp.year,
      localTimestamp.month,
      localTimestamp.day,
    );

    // 메시지 시간 형식 설정 (오전/오후 표시)
    String timeFormat = DateFormat('a h:mm').format(localTimestamp);
    timeFormat = timeFormat.replaceFirst('AM', '오전').replaceFirst('PM', '오후');

    // 날짜 비교
    if (messageDate == today) {
      // 오늘 메시지
      return timeFormat;
    } else if (messageDate == yesterday) {
      // 어제 메시지
      return '어제 $timeFormat';
    } else if (now.difference(localTimestamp).inDays < 7) {
      // 일주일 이내 메시지
      return '${DateFormat('E', 'ko_KR').format(localTimestamp)} $timeFormat';
    } else {
      // 그 외 메시지 (년-월-일 형식)
      return '${DateFormat('yyyy-MM-dd (E)', 'ko_KR').format(localTimestamp)} $timeFormat';
    }
  }

  String _processEmoji(String text) {
    // 이모지 매핑 정의
    final Map<String, String> emojiMap = {
      ':busts_in_silhouette:': '👥',
      // 더 많은 이모지 추가 가능
      ':heart:': '❤️',
      ':thumbsup:': '👍',
      ':thumbsdown:': '👎',
      ':smile:': '😊',
      ':laughing:': '😆',
      ':joy:': '😂',
      // 등등...
    };

    // 모든 이모지 코드를 실제 이모지로 대체
    String processedText = text;
    emojiMap.forEach((code, emoji) {
      processedText = processedText.replaceAll(code, emoji);
    });

    return processedText;
  }
}
