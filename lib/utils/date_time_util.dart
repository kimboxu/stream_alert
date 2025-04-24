// 시간대 처리를 위한 유틸리티 클래스

import 'package:intl/intl.dart';
import 'package:flutter/material.dart';

class DateTimeUtil {
  // 앱 전체에서 사용할 기본 시간대 (한국 시간)
  static const int koreaTimeOffsetHours = 9;
  
  /// UTC 시간을 한국 시간으로 변환
  static DateTime toKoreanTime(DateTime utcTime) {
    return utcTime.toUtc().add(Duration(hours: koreaTimeOffsetHours));
  }
  
  /// ISO 문자열을 파싱하여 DateTime 객체 생성
  /// (서버에서 오는 JSON 데이터를 파싱할 때 사용)
  static DateTime? parseIsoString(String? isoString) {
    if (isoString == null || isoString.isEmpty) {
      return null;
    }
    
    try {
      return DateTime.parse(isoString);
    } catch (e) {
      debugPrint('날짜 파싱 오류: $e');
      return null;
    }
  }
  
  /// DateTime을 사용자 친화적인 형식으로 포맷팅
  static String formatFriendlyDateTime(DateTime timestamp) {
    // 항상 한국 시간 기준으로 표시
    final koreanTime = toKoreanTime(timestamp);
    
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final yesterday = today.subtract(Duration(days: 1));
    final messageDate = DateTime(
      koreanTime.year,
      koreanTime.month,
      koreanTime.day,
    );

    // 메시지 시간 형식 설정 (오전/오후 표시)
    String timeFormat = DateFormat('a h:mm').format(koreanTime);
    timeFormat = timeFormat.replaceFirst('AM', '오전').replaceFirst('PM', '오후');

    // 날짜 비교
    if (messageDate == today) {
      // 오늘 메시지
      return timeFormat;
    } else if (messageDate == yesterday) {
      // 어제 메시지
      return '어제 $timeFormat';
    } else if (now.difference(messageDate).inDays < 7) {
      // 일주일 이내 메시지
      return '${DateFormat('E', 'ko_KR').format(koreanTime)} $timeFormat';
    } else {
      // 그 외 메시지 (년-월-일 형식)
      return '${DateFormat('yyyy-MM-dd (E)', 'ko_KR').format(koreanTime)} $timeFormat';
    }
  }
  
  /// 서버에 저장하기 위한 ISO 형식 문자열 생성
  static String toIsoString(DateTime dateTime) {
    return dateTime.toUtc().toIso8601String();
  }
}

// 사용 예시:
// 1. discord_notification_widget.dart에서 호출
// 
// Widget _buildFooter(BuildContext context, bool isDarkMode) {
//   // 임베드 타임스탬프 또는 알림 타임스탬프 사용
//   DateTime? embedTimestamp;
//   
//   if (notification.embedData != null && notification.embedData!.containsKey('timestamp')) {
//     try {
//       String timestampStr = notification.embedData!['timestamp'].toString();
//       embedTimestamp = DateTime.parse(timestampStr);
//     } catch (e) {
//       print('임베드 타임스탬프 파싱 오류: $e');
//     }
//   }
//   
//   final displayTimestamp = embedTimestamp ?? notification.timestamp;
//   
//   return Padding(
//     padding: const EdgeInsets.all(8.0),
//     child: Row(
//       children: [
//         // ... 기존 코드 ...
//         Text(
//           "${notification.footerText} • ${DateTimeUtil.formatFriendlyDateTime(displayTimestamp)}",
//           style: TextStyle(color: isDarkMode ? Colors.grey[400] : Colors.grey[600], fontSize: 12),
//         ),
//       ],
//     ),
//   );
// }