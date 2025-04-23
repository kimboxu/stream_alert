// lib/models/notification_model.dart 개선 버전
// ignore_for_file: avoid_print

import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
/// 향상된 알림 모델 클래스
/// 디스코드 웹훅 형식의 알림 데이터를 처리하기 위한 모델
class NotificationModel {
  final String id;
  final String username;
  final String content;
  final String avatarUrl;
  final DateTime timestamp;
  final bool read;

  // 리치 임베드 필드
  final String title;
  final String imageUrl;
  final String thumbnailUrl;
  final String url;
  final int color;
  final dynamic fields;
  final String footerText;
  final String footerIconUrl;
  final String description;
  final String authorName;
  final String authorUrl;
  final String authorIconUrl;  // 추가: 작성자 아이콘 URL

  /// 생성자
  NotificationModel({
    required this.id,
    required this.username,
    required this.content,
    this.avatarUrl = '',
    required this.timestamp,
    this.read = false,
    this.title = '',
    this.imageUrl = '',
    this.thumbnailUrl = '',
    this.url = '',
    this.color = 0,
    this.fields,
    this.footerText = '',
    this.footerIconUrl = '',
    this.description = '',
    this.authorName = '',
    this.authorUrl = '',
    this.authorIconUrl = '',  // 추가
  });

  /// JSON으로부터 객체 생성
  factory NotificationModel.fromJson(Map<String, dynamic> json) {
    // embeds 디버깅 출력 (개발 모드에서만)
    if (kDebugMode && json['embeds'] != null) {
      print('원본 embeds 데이터: ${json['embeds']}');
      print('embeds 타입: ${json['embeds'].runtimeType}');
    }

    // embeds 파싱 처리
    List<dynamic>? embedsList;
    if (json['embeds'] != null) {
      try {
        if (json['embeds'] is String) {
          // 문자열로 받은 경우 JSON 파싱
          embedsList = jsonDecode(json['embeds']);
          if (kDebugMode) {
            print('문자열에서 파싱된 embeds: $embedsList');
          }
        } else if (json['embeds'] is List) {
          // 이미 리스트인 경우 그대로 사용
          embedsList = json['embeds'];
          if (kDebugMode) {
            print('리스트로 받은 embeds: $embedsList');
          }
        }
      } catch (e) {
        if (kDebugMode) {
          print('Embeds 파싱 오류: $e');
          print('파싱 시도한 데이터: ${json['embeds']}');
        }
      }
    }

    // 첫 번째 embed 객체 추출
    Map<String, dynamic>? embed;
    if (embedsList != null && embedsList.isNotEmpty) {
      if (embedsList.first is Map) {
        embed = Map<String, dynamic>.from(embedsList.first);
        if (kDebugMode) {
          print('첫 번째 embed: $embed');
        }
      }
    }

    // embed에서 author 정보 추출
    String? authorIconUrl;
    if (embed != null && embed['author'] != null && embed['author']['icon_url'] != null) {
      authorIconUrl = embed['author']['icon_url'];
    }

    return NotificationModel(
      id:
          json['notification_id'] ??
          json['id'] ??
          DateTime.now().millisecondsSinceEpoch.toString(),
      username: json['username'] ?? '알림',
      content: json['content'] ?? '',
      avatarUrl: json['avatar_url'] ?? '',
      timestamp:
          json['timestamp'] != null
              ? DateTime.parse(json['timestamp'])
              : DateTime.now(),
      read: json['read'] ?? false,

      // embed 필드들 추출
      title: embed?['title'] ?? '',
      imageUrl: embed?['image']?['url'] ?? '',
      thumbnailUrl: embed?['thumbnail']?['url'] ?? '',
      url: embed?['url'] ?? '',
      color: embed?['color'] ?? 0,
      fields: embed?['fields'],
      footerText: embed?['footer']?['text'] ?? '',
      footerIconUrl: embed?['footer']?['icon_url'] ?? '',

      // 카페 알림에 필요한 추가 정보
      description: embed?['description'] ?? '',
      authorName: embed?['author']?['name'] ?? '',
      authorUrl: embed?['author']?['url'] ?? '',
      authorIconUrl: authorIconUrl ?? '',  // 추가된 필드
    );
  }

  /// JSON으로 변환
  Map<String, dynamic> toJson() {
    Map<String, dynamic> baseJson = {
      'id': id,
      'username': username,
      'content': content,
      'avatar_url': avatarUrl,
      'timestamp': timestamp.toIso8601String(),
      'read': read,
    };

    // embed 데이터가 있는 경우 추가
    if (isRichNotification) {
      Map<String, dynamic> embed = {};

      if (title.isNotEmpty) embed['title'] = title;
      if (description.isNotEmpty) embed['description'] = description; 
      if (url.isNotEmpty) embed['url'] = url;
      if (color != 0) embed['color'] = color;

      // 작성자 정보가 있는 경우
      if (authorName.isNotEmpty) {
        Map<String, dynamic> author = {'name': authorName};
        if (authorUrl.isNotEmpty) author['url'] = authorUrl;
        if (authorIconUrl.isNotEmpty) author['icon_url'] = authorIconUrl;
        embed['author'] = author;
      }

      // 이미지 정보가 있는 경우
      if (imageUrl.isNotEmpty) {
        embed['image'] = {'url': imageUrl};
      }

      // 썸네일 정보가 있는 경우
      if (thumbnailUrl.isNotEmpty) {
        embed['thumbnail'] = {'url': thumbnailUrl};
      }

      // 필드 정보가 있는 경우
      if (fields != null) {
        embed['fields'] = fields;
      }

      // 푸터 정보가 있는 경우
      if (footerText.isNotEmpty) {
        embed['footer'] = {'text': footerText};
        if (footerIconUrl.isNotEmpty) {
          embed['footer']['icon_url'] = footerIconUrl;
        }
      }

      baseJson['embeds'] = [embed];
    }

    return baseJson;
  }

  /// 일반 알림인지 리치 알림(embed)인지 확인
  bool get isRichNotification =>
      title.isNotEmpty ||
      imageUrl.isNotEmpty ||
      thumbnailUrl.isNotEmpty ||
      url.isNotEmpty ||
      authorName.isNotEmpty ||
      description.isNotEmpty ||
      footerText.isNotEmpty ||
      (fields != null && (fields is List && (fields as List).isNotEmpty));

  /// 디버그용 문자열 표현
  @override
  String toString() {
    return 'NotificationModel(id: $id, username: $username, title: $title, isRich: $isRichNotification)';
  }
  
  /// 알림 유형 분류 (유튜브, 카페, 일반 등)
  NotificationType get type {
    if (username.contains('유튜브 알림') || footerText == 'YouTube') {
      return NotificationType.youtube;
    } else if (username.contains('카페 알림') || footerText == 'cafe') {
      return NotificationType.cafe;
    } else if (title.trim().endsWith('뱅온!')) {
      return NotificationType.streamStart;
    } else if (title.trim().endsWith('방제 변경')) {
      return NotificationType.streamChange;
    } else if (title.trim().endsWith('방송 종료')) {
      return NotificationType.streamEnd;
    } else if (username.contains('>>')) {
      return NotificationType.chat;
    } else {
      return NotificationType.general;
    }
  }
  
  /// 알림 타입에 맞는 아이콘 반환
  IconData get typeIcon {
    switch (type) {
      case NotificationType.youtube:
        return Icons.play_circle_filled;
      case NotificationType.cafe:
        return Icons.article;
      case NotificationType.streamStart:
        return Icons.live_tv;
      case NotificationType.streamChange:
        return Icons.live_tv;
      case NotificationType.streamEnd:
        return Icons.tv_off;
      case NotificationType.chat:
        return Icons.chat;
      case NotificationType.general:
      return Icons.notifications;
    }
  }
  
  /// 알림 타입에 맞는 색상 반환
  Color get typeColor {
    if (color != 0) return Color(color);
    
    switch (type) {
      case NotificationType.youtube:
        return Colors.red;
      case NotificationType.cafe:
        return Colors.green[700]!;
      case NotificationType.streamStart:
        return Colors.blue;
      case NotificationType.streamChange:
        return Colors.blue;
      case NotificationType.streamEnd:
        return Colors.orange;
      case NotificationType.chat:
        return Colors.purple;
      case NotificationType.general:
      return Colors.grey;
    }
  }
}

/// 알림 유형 열거
enum NotificationType {
  youtube,     // 유튜브 알림
  cafe,        // 카페 알림
  streamStart, // 뱅온 알림
  streamChange, // 방제 변경 알림
  streamEnd,   // 방종 알림
  chat,        // 채팅 알림
  general      // 일반 알림
}