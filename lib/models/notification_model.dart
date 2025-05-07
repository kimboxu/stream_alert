// ignore_for_file: unnecessary_import

import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

/// 알림 모델 클래스
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
  final String authorIconUrl;

  // 원본 임베드 데이터 저장
  final Map<String, dynamic>? embedData;

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
    this.authorIconUrl = '',
    this.embedData,
  });

  /// JSON으로부터 객체 생성
  factory NotificationModel.fromJson(Map<String, dynamic> json) {
    // embeds 디버깅 출력 (개발 모드에서만)
    if (json['embeds'] != null) {
      debugPrint('원본 embeds 데이터: ${json['embeds']}');
      debugPrint('embeds 타입: ${json['embeds'].runtimeType}');
    }

    // embeds 파싱 처리
    List<dynamic>? embedsList;
    Map<String, dynamic>? originalEmbed;
    if (json['embeds'] != null) {
      try {
        if (json['embeds'] is String) {
          // 문자열로 받은 경우 JSON 파싱
          embedsList = jsonDecode(json['embeds']);

          debugPrint('문자열에서 파싱된 embeds: $embedsList');
        } else if (json['embeds'] is List) {
          // 이미 리스트인 경우 그대로 사용
          embedsList = json['embeds'];

          debugPrint('리스트로 받은 embeds: $embedsList');
        }
      } catch (e) {
        debugPrint('Embeds 파싱 오류: $e');
        debugPrint('파싱 시도한 데이터: ${json['embeds']}');
      }
    }

    // 첫 번째 embed 객체 추출
    Map<String, dynamic>? embed;
    if (embedsList != null && embedsList.isNotEmpty) {
      if (embedsList.first is Map) {
        embed = Map<String, dynamic>.from(embedsList.first);
        originalEmbed = Map<String, dynamic>.from(embed); // 원본 임베드 데이터 저장

        debugPrint('첫 번째 embed: $embed');
      }
    }

    // embed에서 author 정보 추출
    String? authorIconUrl;
    if (embed != null &&
        embed['author'] != null &&
        embed['author']['icon_url'] != null) {
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
      authorIconUrl: authorIconUrl ?? '',

      // 원본 임베드 데이터 저장
      embedData: originalEmbed,
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

      // timestamp 필드 추가 (원본 임베드에서 가져오거나 현재 timestamp 사용)
      if (embedData != null && embedData!.containsKey('timestamp')) {
        embed['timestamp'] = embedData!['timestamp'];
      } else {
        embed['timestamp'] = timestamp.toIso8601String();
      }

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
    } else if (description.endsWith('치지직 영상 업로드!')) {
      return NotificationType.chzzkVOD;
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
}

/// 알림 유형 열거
enum NotificationType {
  youtube, // 유튜브 알림
  cafe, // 카페 알림
  chzzkVOD, // 치지직 VOD 알림
  streamStart, // 뱅온 알림
  streamChange, // 방제 변경 알림
  streamEnd, // 방종 알림
  chat, // 채팅 알림
  general, // 일반 알림
}
