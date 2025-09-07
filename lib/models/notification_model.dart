// ignore_for_file: unnecessary_import

import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

/// 알림 모델 클래스 - 다양한 유형의 알림을 표현
class NotificationModel {
  // 기본 알림 속성
  final String id;           // 알림 고유 ID
  final String username;     // 알림 발신자 이름
  final String content;      // 알림 내용
  final String avatarUrl;    // 발신자 아바타 이미지 URL
  final DateTime timestamp;  // 알림 발생 시간
  final bool read;           // 읽음 상태

  // 임베드 필드 (Discord 형식 임베드와 호환)
  final String title;          // 임베드 제목
  final String imageUrl;       // 큰 이미지 URL
  final String thumbnailUrl;   // 썸네일 이미지 URL
  final String url;            // 임베드 링크 URL
  final int color;             // 임베드 색상 (RGB)
  final dynamic fields;        // 임베드 필드 목록
  final String footerText;     // 푸터 텍스트
  final String footerIconUrl;  // 푸터 아이콘 URL
  final String description;    // 임베드 설명
  final String authorName;     // 작성자 이름
  final String authorUrl;      // 작성자 URL
  final String authorIconUrl;  // 작성자 아이콘 URL

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

  /// JSON으로부터 알림 객체 생성하는 팩토리 메서드
  factory NotificationModel.fromJson(Map<String, dynamic> json) {
    // embeds 디버깅 출력
    if (json['embeds'] != null) {
      debugPrint('원본 embeds 데이터: ${json['embeds']}');
      debugPrint('embeds 타입: ${json['embeds'].runtimeType}');
    }

    // embeds 파싱 처리 - 문자열 또는 리스트 형태로 받을 수 있음
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

    // NotificationModel 객체 생성 및 반환
    return NotificationModel(
      id:
          json['notification_id'] ??
          json['id'] ??
          DateTime.now().millisecondsSinceEpoch.toString(),  // ID 없으면 현재 시간 기반 생성
      username: json['username'] ?? '알림',
      content: json['content'] ?? '',
      avatarUrl: json['avatar_url'] ?? '',
      timestamp:
          json['timestamp'] != null
              ? DateTime.parse(json['timestamp'])
              : DateTime.now(),  // 타임스탬프 없으면 현재 시간
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

  /// 알림을 JSON으로 변환하는 메서드
  Map<String, dynamic> toJson() {
    // 기본 JSON 데이터
    Map<String, dynamic> baseJson = {
      'id': id,
      'username': username,
      'content': content,
      'avatar_url': avatarUrl,
      'timestamp': timestamp.toIso8601String(),
      'read': read,
    };

    // 임베드인 경우 추가 데이터 구성
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

      baseJson['embeds'] = [embed];  // 임베드 배열로 추가
    }

    return baseJson;
  }

  /// 임베드 포함 여부 확인 getter
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

  /// 알림 유형 분류 getter (유튜브, 카페, 일반 등)
  NotificationType get type {
    if (username.contains('유튜브 알림') || footerText == 'YouTube') {
      return NotificationType.youtube;  // 유튜브 알림
    } else if (username.contains('카페 알림') || footerText == 'cafe') {
      return NotificationType.cafe;  // 카페 알림
    } else if (description.endsWith('치지직 영상 업로드!')) {
      return NotificationType.chzzkVOD;  // 치지직 VOD 알림
    } else if (title.trim().endsWith('뱅온!')) {
      return NotificationType.streamStart;  // 방송 시작 알림
    } else if (title.trim().endsWith('방제 변경')) {
      return NotificationType.streamChange;  // 방송 제목 변경 알림
    } else if (title.trim().endsWith('방송 종료')) {
      return NotificationType.streamEnd;  // 방송 종료 알림
    } else if (username.contains('>>')) {
      return NotificationType.chat;  // 채팅 알림
    } else {
      return NotificationType.general;  // 일반 알림
    }
  }
}

/// 알림 유형 열거형
enum NotificationType {
  youtube,      // 유튜브 알림
  cafe,         // 카페 알림
  chzzkVOD,     // 치지직 VOD 알림
  streamStart,  // 뱅온 알림
  streamChange, // 방제 변경 알림
  streamEnd,    // 방종 알림
  streamHighlight,    // 방종 알림
  chat,         // 채팅 알림
  general,      // 일반 알림
}