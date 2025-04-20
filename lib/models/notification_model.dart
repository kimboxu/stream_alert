// lib/models/notification_model.dart
class NotificationModel {
  final String id;
  final String username;
  final String content;
  final String avatarUrl;
  final DateTime timestamp;
  final Map<String, dynamic>? additionalData;

  NotificationModel({
    required this.id,
    required this.username,
    required this.content,
    this.avatarUrl = '',
    required this.timestamp,
    this.additionalData,
  });

  factory NotificationModel.fromJson(Map<String, dynamic> json) {
    return NotificationModel(
      id: json['id'] ?? DateTime.now().millisecondsSinceEpoch.toString(),
      username: json['username'] ?? '알림',
      content: json['content'] ?? '',
      avatarUrl: json['avatar_url'] ?? '',
      timestamp:
          json['timestamp'] != null
              ? DateTime.parse(json['timestamp'])
              : DateTime.now(),
      additionalData: json,
    );
  }

  get read => null;

  Map<String, dynamic> toJson() {
  return {
    'id': id,
    'username': username,
    'content': content,
    'avatar_url': avatarUrl,
    'timestamp': timestamp.toIso8601String(),
    'read': additionalData?['read'] ?? false,
  };
}
}