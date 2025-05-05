import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/notification_model.dart';

/// 디스코드 스타일의 알림 위젯
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
          Container(
            width: 28,
            height: 28,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isDarkMode ? Colors.grey[800] : Colors.grey[200],
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(14),
              child:
                  notification.avatarUrl.isNotEmpty
                      ? Image.network(
                        notification.avatarUrl,
                        fit: BoxFit.cover,
                        width: 28,
                        height: 28,
                        errorBuilder:
                            (context, error, stackTrace) => Icon(
                              Icons.person,
                              size: 16,
                              color:
                                  isDarkMode
                                      ? Colors.white70
                                      : Colors.grey[700],
                            ),
                      )
                      : Icon(
                        Icons.person,
                        size: 16,
                        color: isDarkMode ? Colors.white70 : Colors.grey[700],
                      ),
            ),
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
  Widget _buildRichNotification(
    BuildContext context,
    bool isDarkMode,
    Color borderColor,
  ) {
    // 이미지 영역을 위한 고정 비율 상수
    const double embedImageRatio = 16 / 9; // 16:9 비율
    const double thumbnailSize = 80.0; // 썸네일 크기
    const double embedHeightMin = 180.0; // 임베드 최소 높이
    const double embedHeightMax = 300.0; // 임베드 최소 높이

    return Container(
      margin: const EdgeInsets.fromLTRB(8, 4, 8, 8),
      decoration: BoxDecoration(
        border: Border(left: BorderSide(color: borderColor, width: 4)),
        borderRadius: BorderRadius.circular(3),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 메인 컨텐츠 영역
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 텍스트 콘텐츠 영역
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // 작성자 정보
                      if (notification.authorName.isNotEmpty) ...[
                        InkWell(
                          onTap: () => _launchUrl(notification.authorUrl),
                          child: Text(
                            notification.authorName,
                            style: TextStyle(
                              fontWeight: FontWeight.w500,
                              color:
                                  isDarkMode
                                      ? Colors.grey[300]
                                      : Colors.grey[700],
                              fontSize: 14,
                            ),
                          ),
                        ),
                        SizedBox(height: 6),
                      ],

                      // 제목 (썸네일이 있는 경우 우측 여백 확보)
                      if (notification.title.isNotEmpty)
                        Padding(
                          padding:
                              notification.thumbnailUrl.isNotEmpty
                                  ? EdgeInsets.only(
                                    right: thumbnailSize + 10.0,
                                    bottom: 8.0,
                                  )
                                  : EdgeInsets.only(bottom: 8.0),
                          child:
                              notification.url.isNotEmpty
                                  ? InkWell(
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
                                    _processEmoji(notification.title),
                                    style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      color:
                                          isDarkMode
                                              ? Colors.grey[300]
                                              : Colors.grey[800],
                                      fontSize: 16,
                                    ),
                                  ),
                        ),

                      // 설명
                      if (notification.description.isNotEmpty)
                        Padding(
                          padding:
                              notification.thumbnailUrl.isNotEmpty
                                  ? EdgeInsets.only(right: thumbnailSize + 10.0)
                                  : EdgeInsets.zero,
                          child: Text(
                            _processEmoji(notification.description),
                            style: TextStyle(
                              color:
                                  isDarkMode ? Colors.white70 : Colors.black87,
                            ),
                          ),
                        ),

                      // 필드 목록
                      if (notification.fields != null)
                        ...notification.fields!.map((field) {
                          if (field is Map &&
                              field.containsKey('name') &&
                              field.containsKey('value')) {
                            return Padding(
                              padding: const EdgeInsets.only(top: 8.0),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    _processEmoji(field['name']!.toString()),
                                    style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      color:
                                          isDarkMode
                                              ? Colors.white
                                              : Colors.black87,
                                      fontSize: 14,
                                    ),
                                  ),
                                  Text(
                                    _processEmoji(
                                      field['value']?.toString() ?? '',
                                    ),
                                    style: TextStyle(
                                      color:
                                          isDarkMode
                                              ? Colors.white70
                                              : Colors.black87,
                                      fontSize: 14,
                                    ),
                                  ),
                                ],
                              ),
                            );
                          }
                          return SizedBox.shrink();
                        }).toList(),
                    ],
                  ),
                ),

                // 썸네일 영역 (고정 크기)
                if (notification.thumbnailUrl.isNotEmpty)
                  Container(
                    width: thumbnailSize,
                    height: thumbnailSize,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(4),
                      color: Colors.grey[300], // 로딩 배경색
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: Image.network(
                        notification.thumbnailUrl,
                        fit: BoxFit.cover,
                        width: thumbnailSize,
                        height: thumbnailSize,
                        errorBuilder:
                            (context, error, stackTrace) => Container(
                              width: thumbnailSize,
                              height: thumbnailSize,
                              color: Colors.grey[400],
                              child: Center(
                                child: Icon(
                                  Icons.broken_image,
                                  color: Colors.grey[200],
                                ),
                              ),
                            ),
                        loadingBuilder: (context, child, loadingProgress) {
                          if (loadingProgress == null) return child;
                          return Center(
                            child: CircularProgressIndicator(
                              value:
                                  loadingProgress.expectedTotalBytes != null
                                      ? loadingProgress.cumulativeBytesLoaded /
                                          loadingProgress.expectedTotalBytes!
                                      : null,
                              strokeWidth: 2,
                              color: Colors.grey[500],
                            ),
                          );
                        },
                      ),
                    ),
                  ),
              ],
            ),
          ),

          // 메인 이미지 영역 (고정 비율 유지)
          if (notification.imageUrl.isNotEmpty)
            Container(
              width: double.infinity,
              // 유튜브 임베드인 경우 더 큰 고정 높이 사용
              constraints: BoxConstraints(
                minHeight: embedHeightMin,
                maxHeight: embedHeightMax,
              ),
              decoration: BoxDecoration(
                color: Colors.grey[800], // 로딩 배경색
                borderRadius: BorderRadius.circular(4),
              ),
              child: AspectRatio(
                aspectRatio: embedImageRatio,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: Image.network(
                    notification.imageUrl,
                    fit: BoxFit.cover,
                    errorBuilder:
                        (context, error, stackTrace) => Container(
                          color: Colors.grey[400],
                          child: Center(
                            child: Icon(
                              Icons.broken_image,
                              color: Colors.grey[200],
                              size: 40,
                            ),
                          ),
                        ),
                    loadingBuilder: (context, child, loadingProgress) {
                      if (loadingProgress == null) return child;
                      return Center(
                        child: CircularProgressIndicator(
                          value:
                              loadingProgress.expectedTotalBytes != null
                                  ? loadingProgress.cumulativeBytesLoaded /
                                      loadingProgress.expectedTotalBytes!
                                  : null,
                          strokeWidth: 2,
                          color: Colors.grey[500],
                        ),
                      );
                    },
                  ),
                ),
              ),
            ),

          // 푸터 영역
          if (notification.footerText.isNotEmpty)
            Padding(
              padding: const EdgeInsets.all(8.0),
              child: Row(
                children: [
                  if (notification.footerIconUrl.isNotEmpty) ...[
                    Container(
                      width: 16,
                      height: 16,
                      margin: const EdgeInsets.only(right: 8.0),
                      decoration: BoxDecoration(
                        color: Colors.grey[300],
                        shape: BoxShape.circle,
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: Image.network(
                          notification.footerIconUrl,
                          fit: BoxFit.cover,
                          errorBuilder:
                              (context, error, stackTrace) => SizedBox(
                                width: 16,
                                height: 16,
                                child: Icon(
                                  Icons.image,
                                  size: 12,
                                  color: Colors.grey[400],
                                ),
                              ),
                        ),
                      ),
                    ),
                  ],
                  Expanded(
                    child: Text(
                      // 임베드 타임스탬프 또는 알림 타임스탬프 사용
                      "${notification.footerText} • ${_formatTimestamp(_getEmbedTimestamp())}",
                      style: TextStyle(
                        color: isDarkMode ? Colors.grey[400] : Colors.grey[600],
                        fontSize: 12,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  // 임베드 타임스탬프 추출 메서드
  DateTime _getEmbedTimestamp() {
    DateTime? embedTimestamp;
    // 임베드 데이터에서 타임스탬프 찾기
    if (notification.embedData != null &&
        notification.embedData!.containsKey('timestamp')) {
      try {
        String timestampStr = notification.embedData!['timestamp'].toString();
        embedTimestamp = DateTime.parse(timestampStr);
      } catch (e) {
        debugPrint('임베드 타임스탬프 파싱 오류: $e');
      }
    }
    // 임베드 타임스탬프가 있으면 사용, 없으면 알림 타임스탬프 사용
    return embedTimestamp ?? notification.timestamp;
  }

  // URL 실행 함수
  void _launchUrl(String url) async {
    if (url.isEmpty) return;

    try {
      final uri = Uri.parse(url);
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (e) {
      debugPrint('🚫 URL 실행 중 오류: $e');
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
    } else {
      // 그 외 메시지 (년-월-일 형식)
      return '${DateFormat('yyyy-MM-dd (E)', 'ko_KR').format(localTimestamp)} $timeFormat';
    }
  }

  String _processEmoji(String text) {
    // 이모지 매핑 정의
    final Map<String, String> emojiMap = {
      ':busts_in_silhouette:': '👥',
      ':heart:': '❤️',
      ':thumbsup:': '👍',
      ':thumbsdown:': '👎',
      ':smile:': '😊',
      ':laughing:': '😆',
      ':joy:': '😂',
    };

    // 모든 이모지 코드를 실제 이모지로 대체
    String processedText = text;
    emojiMap.forEach((code, emoji) {
      processedText = processedText.replaceAll(code, emoji);
    });

    return processedText;
  }
}
