// lib/models/notification_model.dart 수정
class NotificationModel {
  final String id;
  final String username;
  final String content;
  final String avatarUrl;
  final DateTime timestamp;
  final bool read;

  // 새로 추가된 필드들
  final String title;
  final String imageUrl;
  final String thumbnailUrl;
  final String url;
  final int color;
  final dynamic fields;
  final String footerText;
  final String footerIconUrl;

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
    this.color = 0, // 기본 색상 없음
    this.fields,
    this.footerText = '',
    this.footerIconUrl = '',
  });

  factory NotificationModel.fromJson(Map<String, dynamic> json) {
    // embeds가 있으면 첫 번째 embed에서 정보 추출
    Map<String, dynamic>? embed;
    if (json['embeds'] != null &&
        json['embeds'] is List &&
        (json['embeds'] as List).isNotEmpty) {
      embed = (json['embeds'] as List).first;
    }

    return NotificationModel(
      id: json['id'] ?? DateTime.now().millisecondsSinceEpoch.toString(),
      username: json['username'] ?? '알림',
      content: json['content'] ?? '',
      avatarUrl: json['avatar_url'] ?? '',
      timestamp:
          json['timestamp'] != null
              ? DateTime.parse(json['timestamp'])
              : DateTime.now(),
      read: json['read'] ?? false,

      // embed 데이터가 있으면 추출
      title: embed?['title'] ?? '',
      imageUrl: embed?['image']?['url'] ?? '',
      thumbnailUrl: embed?['thumbnail']?['url'] ?? '',
      url: embed?['url'] ?? '',
      color: embed?['color'] ?? 0,
      fields: embed?['fields'],
      footerText: embed?['footer']?['text'] ?? '',
      footerIconUrl: embed?['footer']?['icon_url'] ?? '',
    );
  }

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
    if (title.isNotEmpty ||
        imageUrl.isNotEmpty ||
        thumbnailUrl.isNotEmpty ||
        url.isNotEmpty ||
        color != 0 ||
        fields != null ||
        footerText.isNotEmpty ||
        footerIconUrl.isNotEmpty) {
      Map<String, dynamic> embed = {};

      if (title.isNotEmpty) embed['title'] = title;
      if (url.isNotEmpty) embed['url'] = url;
      if (color != 0) embed['color'] = color;

      if (imageUrl.isNotEmpty) {
        embed['image'] = {'url': imageUrl};
      }

      if (thumbnailUrl.isNotEmpty) {
        embed['thumbnail'] = {'url': thumbnailUrl};
      }

      if (fields != null) {
        embed['fields'] = fields;
      }

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

  // 일반 알림인지 리치 알림(embed)인지 확인
  bool get isRichNotification =>
      title.isNotEmpty ||
      imageUrl.isNotEmpty ||
      thumbnailUrl.isNotEmpty ||
      url.isNotEmpty;
}
