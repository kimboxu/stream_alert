// lib/screens/notifications_page.dart
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/notification_model.dart';
import '../services/push_notification_service.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import '../services/api_service.dart';

class NotificationsPage extends StatefulWidget {
  const NotificationsPage({super.key});

  @override
  // ignore: library_private_types_in_public_api
  _NotificationsPageState createState() => _NotificationsPageState();
}

class _NotificationsPageState extends State<NotificationsPage> {
  List<NotificationModel> _notifications = [];
  bool _isLoading = true;
  bool _isLoadingMore = false;
  bool _hasMoreData = true;
  bool _isRefreshing = false;
  bool _autoScrollEnabled = false;
  bool _isNearBottom = true;
  int _currentPage = 1;
  final int _pageSize = 50;
  late ScrollController _scrollController;
  StreamSubscription<RemoteMessage>? _messageSubscription;

  @override
  void initState() {
    super.initState();
    _scrollController = ScrollController();
    _scrollController.addListener(_scrollListener);
    _loadNotifications(refresh: true);
    _setupMessageListener();

    // 노티피케이션을 받더라도 자동 스크롤 방지 설정
    _autoScrollEnabled = false;
  }

  void _scrollListener() {
    // 현재 스크롤 위치가 하단에서 얼마나 떨어져 있는지 확인
    if (_scrollController.hasClients) {
      final maxScroll = _scrollController.position.maxScrollExtent;
      final currentScroll = _scrollController.position.pixels;

      // 하단에서 100픽셀 이내면 하단으로 간주
      _isNearBottom = (maxScroll - currentScroll) < 100;

      // 하단 가까이 있을 때만 자동 스크롤 활성화
      _autoScrollEnabled = _isNearBottom;

      // 무한 스크롤 로직 - 상단에 가까워지면 더 많은 데이터 로드
      if (_scrollController.position.pixels >=
          _scrollController.position.maxScrollExtent - 200) {
        if (!_isLoadingMore && _hasMoreData) {
          _loadMoreNotifications();
        }
      }
    }
  }

  Future<void> _loadMoreNotifications() async {
    if (_isLoadingMore) return;

    setState(() {
      _isLoadingMore = true;
    });

    try {
      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username');
      final discordWebhooksURL = prefs.getString('discordWebhooksURL');

      if (username != null && discordWebhooksURL != null) {
        final newNotifications = await ApiService.getNotifications(
          username,
          discordWebhooksURL,
          page: _currentPage + 1,
          limit: _pageSize,
        );

        if (newNotifications.isEmpty) {
          _hasMoreData = false;
        } else {
          _currentPage++;
          setState(() {
            _notifications.addAll(newNotifications);
          });
        }
      }
    } catch (e) {
      if (kDebugMode) {
        print('더 많은 알림 로드 중 오류: $e');
      }
    } finally {
      setState(() {
        _isLoadingMore = false;
      });
    }
  }

  void _addNewNotification(RemoteMessage message) async {
    try {
      // 새 알림 데이터 생성
      final String messageId =
          message.messageId ?? DateTime.now().millisecondsSinceEpoch.toString();

      final notificationData = {
        'id': messageId,
        'username':
            message.notification?.title ?? message.data['username'] ?? '알림',
        'content':
            message.notification?.body ??
            message.data['content'] ??
            '새 메시지가 있습니다',
        'avatar_url': message.data['avatar_url'] ?? '',
        'timestamp': DateTime.now().toIso8601String(),
        'read': false,
      };

      // 추가 데이터가 있으면 병합
      if (message.data.isNotEmpty) {
        notificationData.addAll(message.data);
      }

      // 알림 객체 생성
      final newNotification = NotificationModel.fromJson(notificationData);

      // 중복 확인
      final existingIndex = _notifications.indexWhere(
        (n) => n.id == newNotification.id,
      );

      setState(() {
        if (existingIndex != -1) {
          // 기존 알림이 있으면 업데이트
          _notifications[existingIndex] = newNotification;
        } else {
          // 새 알림 추가
          _notifications.add(newNotification);
        }

        // 정렬 (최신 알림이 아래에 오도록)
        _notifications.sort((a, b) => a.timestamp.compareTo(b.timestamp));
      });

      // 자동 스크롤이 활성화된 경우에만 하단으로 스크롤
      if (_autoScrollEnabled && _scrollController.hasClients) {
        Future.delayed(Duration(milliseconds: 100), () {
          _scrollController.animateTo(
            _scrollController.position.maxScrollExtent,
            duration: Duration(milliseconds: 300),
            curve: Curves.easeOut,
          );
        });
      } else if (!_isNearBottom && _scrollController.hasClients) {
        // 새 메시지 알림 UI 표시 (옵션)
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('새 알림이 도착했습니다'),
            duration: Duration(seconds: 2),
            action: SnackBarAction(
              label: '보기',
              onPressed: () {
                _scrollController.animateTo(
                  _scrollController.position.maxScrollExtent,
                  duration: Duration(milliseconds: 300),
                  curve: Curves.easeOut,
                );
              },
            ),
          ),
        );
      }
    } catch (e) {
      if (kDebugMode) {
        print('새 알림 추가 중 오류: $e');
      }
    }
  }

  @override
  void dispose() {
    // 구독 취소
    _messageSubscription?.cancel();
    _scrollController.dispose();
    super.dispose();
  }

  void _setupMessageListener() {
    _messageSubscription = FirebaseMessaging.onMessage.listen((
      RemoteMessage message,
    ) {
      // 새 메시지를 알림 목록에 추가
      _addNewNotification(message);
    });
  }

Future<void> _loadNotifications({bool refresh = false}) async {
  setState(() {
    _isLoading = true;
  });

  try {
    // 새로고침이면 페이지 초기화
    if (refresh) {
      _currentPage = 1;
      _hasMoreData = true;
    }

    final prefs = await SharedPreferences.getInstance();
    final username = prefs.getString('username');
    final discordWebhooksURL = prefs.getString('discordWebhooksURL');

    if (username != null && discordWebhooksURL != null) {
      final notifications = await ApiService.getNotifications(
        username,
        discordWebhooksURL,
        page: _currentPage,
        limit: _pageSize,
      );

      setState(() {
        if (refresh) {
          _notifications = notifications;
        } else {
          _notifications.addAll(notifications);
        }

        _isLoading = false;

        // 오래된 메시지 순으로 정렬 (타임스탬프 오름차순)
        _notifications.sort((a, b) => a.timestamp.compareTo(b.timestamp));

        // 가져온 알림 수가 페이지 크기보다 작으면 더 이상 데이터가 없음
        if (notifications.length < _pageSize) {
          _hasMoreData = false;
        }
      });
    } else {
      setState(() {
        _isLoading = false;
      });
    }
  } catch (e) {
    if (kDebugMode) {
      print('알림 로드 중 오류: $e');
    }
    setState(() {
      _isLoading = false;
    });
  }
}

  Future<void> _refreshNotifications() async {
    if (_isRefreshing) return;

    setState(() {
      _isRefreshing = true;
    });

    try {
      // 서버에서 최신 알림 새로고침
      final pushService = PushNotificationService();
      final notifications = await pushService.loadNotificationsFromServer();

      setState(() {
        _notifications = notifications;
      });
    } catch (e) {
      if (kDebugMode) {
        print('알림 새로고침 중 오류: $e');
      }
    } finally {
      setState(() {
        _isRefreshing = false;
      });
    }
  }

  String _formatTimestamp(DateTime timestamp) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final yesterday = today.subtract(Duration(days: 1));
    final messageDate = DateTime(
      timestamp.year,
      timestamp.month,
      timestamp.day,
    );

    // 메시지 시간 형식 설정 (오전/오후 표시)
    String timeFormat = DateFormat('a h:mm').format(timestamp);
    timeFormat = timeFormat.replaceFirst('AM', '오전').replaceFirst('PM', '오후');

    // 날짜 비교
    if (messageDate == today) {
      // 오늘 메시지
      return timeFormat;
    } else if (messageDate == yesterday) {
      // 어제 메시지
      return '어제 $timeFormat';
    } else if (now.difference(timestamp).inDays < 7) {
      // 일주일 이내 메시지
      return '${DateFormat('E', 'ko_KR').format(timestamp)} $timeFormat';
    } else {
      // 그 외 메시지 (년-월-일 형식)
      return '${DateFormat('yyyy-MM-dd (E)', 'ko_KR').format(timestamp)} $timeFormat';
    }
  }

  @override
  Widget build(BuildContext context) {
  return Scaffold(
    appBar: AppBar(
      title: Text('받은 알림'),
      actions: [
        IconButton(
          icon: Icon(Icons.refresh),
          onPressed: _isRefreshing ? null : _refreshNotifications,
          tooltip: '알림 새로고침',
        ),
        // ... 기존 액션 버튼들
      ],
    ),
    body: _isLoading
      ? Center(child: CircularProgressIndicator())
      : Stack(
          children: [
            RefreshIndicator(
              onRefresh: _refreshNotifications,
              child: _notifications.isEmpty
                ? _buildEmptyNotifications()
                : _buildNotificationsList(),
            ),
            // 새 메시지 있을 때 스크롤 다운 버튼 (선택적)
            if (!_isNearBottom && _notifications.isNotEmpty)
              Positioned(
                right: 16,
                bottom: 16,
                child: FloatingActionButton(
                  mini: true,
                  backgroundColor: Colors.blue,
                  child: Icon(Icons.arrow_downward),
                  onPressed: () {
                    _scrollController.animateTo(
                      _scrollController.position.maxScrollExtent,
                      duration: Duration(milliseconds: 300),
                      curve: Curves.easeOut,
                    );
                  },
                ),
              ),
          ],
        ),
  );
}
  Widget _buildEmptyNotifications() {
    return ListView(
      physics: AlwaysScrollableScrollPhysics(),
      children: [
        SizedBox(
          height: MediaQuery.of(context).size.height * 0.7,
          child: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.notifications_off, size: 64, color: Colors.grey),
                SizedBox(height: 16),
                Text(
                  '받은 알림이 없습니다',
                  style: TextStyle(fontSize: 18, color: Colors.grey[600]),
                ),
                SizedBox(height: 24),
                Text(
                  '아래로 당겨서 새로고침',
                  style: TextStyle(fontSize: 14, color: Colors.grey[400]),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildNotificationsList() {
    // 날짜별로 메시지 그룹화
    Map<String, List<NotificationModel>> groupedNotifications = {};

    for (var notification in _notifications) {
      final date = DateFormat('yyyy-MM-dd').format(notification.timestamp);
      if (!groupedNotifications.containsKey(date)) {
        groupedNotifications[date] = [];
      }
      groupedNotifications[date]!.add(notification);
    }

    // 날짜 오름차순 정렬
    List<String> sortedDates =
        groupedNotifications.keys.toList()..sort((a, b) => a.compareTo(b));

    // 최종 위젯 리스트 생성 (날짜 구분선 포함)
    List<Widget> allWidgets = [];

    for (String date in sortedDates) {
      // 날짜 구분선 추가
      allWidgets.add(_buildDateDivider(date));

      // 해당 날짜의 알림 추가
      for (var notification in groupedNotifications[date]!) {
        allWidgets.add(_buildNotificationItem(notification));
      }
    }

    return ListView(
      controller: _scrollController,
      physics: AlwaysScrollableScrollPhysics(),
      children: allWidgets,
    );
  }

  // 날짜 구분선 위젯
  Widget _buildDateDivider(String dateStr) {
    DateTime date = DateFormat('yyyy-MM-dd').parse(dateStr);
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final yesterday = today.subtract(Duration(days: 1));
    final messageDate = DateTime(date.year, date.month, date.day);

    String displayText;

    // 날짜 비교
    if (messageDate == today) {
      displayText = '오늘';
    } else if (messageDate == yesterday) {
      displayText = '어제';
    } else if (now.difference(date).inDays < 7) {
      // 일주일 이내
      displayText = DateFormat('EEEE', 'ko_KR').format(date); // 요일 전체 이름
    } else {
      // 그 외 (년-월-일 형식)
      displayText = DateFormat('yyyy년 M월 d일 EEEE', 'ko_KR').format(date);
    }

    return Container(
      padding: EdgeInsets.symmetric(vertical: 8),
      margin: EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Expanded(child: Divider(color: Colors.grey[400], thickness: 0.5)),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              displayText,
              style: TextStyle(
                color: Colors.grey[600],
                fontSize: 12,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          Expanded(child: Divider(color: Colors.grey[400], thickness: 0.5)),
        ],
      ),
    );
  }

  Widget _buildNotificationItem(NotificationModel notification) {
    // 리치 알림(embeds가 있는 경우)
    if (notification.isRichNotification) {
      return Card(
        margin: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side:
              notification.color != 0
                  ? BorderSide(color: Color(notification.color), width: 2)
                  : BorderSide.none,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 상단바 (사용자명과 아바타)
            ListTile(
              contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              leading: CircleAvatar(
                backgroundImage:
                    notification.avatarUrl.isNotEmpty
                        ? NetworkImage(notification.avatarUrl)
                        : null,
                radius: 16,
                child:
                    notification.avatarUrl.isEmpty
                        ? Icon(Icons.person, size: 16)
                        : null,
              ),
              title: Text(
                notification.username,
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
              ),
              trailing: Text(
                _formatTimestamp(notification.timestamp),
                style: TextStyle(color: Colors.grey[600], fontSize: 12),
              ),
            ),

            // 제목이 있는 경우
            if (notification.title.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 4,
                ),
                child: Text(
                  notification.title,
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
              ),

            // 내용이 있는 경우
            if (notification.content.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 4,
                ),
                child: Text(
                  notification.content,
                  style: TextStyle(fontSize: 14),
                ),
              ),

            // 필드가 있는 경우 (Discord의 필드처럼 표시)
            if (notification.fields != null)
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 4,
                ),
                child: _buildFields(notification.fields!),
              ),

            // 이미지가 있는 경우
            if (notification.imageUrl.isNotEmpty)
              Container(
                constraints: BoxConstraints(maxHeight: 200),
                width: double.infinity,
                child: Image.network(
                  notification.imageUrl,
                  fit: BoxFit.cover,
                  errorBuilder:
                      (context, error, stackTrace) => Container(
                        height: 100,
                        color: Colors.grey[300],
                        child: Center(child: Icon(Icons.broken_image)),
                      ),
                ),
              ),

            // 푸터가 있는 경우
            if (notification.footerText.isNotEmpty)
              Padding(
                padding: const EdgeInsets.all(12.0),
                child: Row(
                  children: [
                    if (notification.footerIconUrl.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(right: 8.0),
                        child: Image.network(
                          notification.footerIconUrl,
                          width: 16,
                          height: 16,
                          errorBuilder:
                              (context, error, stackTrace) =>
                                  SizedBox(width: 16, height: 16),
                        ),
                      ),
                    Text(
                      notification.footerText,
                      style: TextStyle(color: Colors.grey[600], fontSize: 12),
                    ),
                  ],
                ),
              ),
          ],
        ),
      );
    } else {
      // 기존 기본 알림 표시 방식
      return Card(
        margin: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        child: Padding(
          padding: const EdgeInsets.all(12.0),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 아바타 이미지
              CircleAvatar(
                backgroundImage:
                    notification.avatarUrl.isNotEmpty
                        ? NetworkImage(notification.avatarUrl)
                        : null,
                radius: 20,
                child:
                    notification.avatarUrl.isEmpty ? Icon(Icons.person) : null,
              ),
              SizedBox(width: 12),
              // 알림 내용 - Expanded 위젯으로 감싸 넘침 방지
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        // 사용자 이름을 Flexible로 감싸 공간을 효율적으로 사용
                        Flexible(
                          child: Text(
                            notification.username,
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 16,
                            ),
                            // 넘칠 경우 말줄임표 표시
                            overflow: TextOverflow.ellipsis,
                            maxLines: 1,
                          ),
                        ),
                        SizedBox(width: 8),
                        Text(
                          _formatTimestamp(notification.timestamp),
                          style: TextStyle(
                            color: Colors.grey[600],
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                    SizedBox(height: 4),
                    // 메시지 내용도 넘침 방지
                    Text(
                      notification.content,
                      style: TextStyle(fontSize: 15),
                      // 내용이 너무 길면 2줄까지만 표시
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    }
  }

  // 필드 처리를 위한 새로운 메서드 추가
  Widget _buildFields(dynamic fields) {
    try {
      List<Widget> fieldWidgets = [];

      if (fields is List) {
        // fields가 리스트인 경우 (Discord 형식)
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
                      field['name']?.toString() ?? '',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 14,
                      ),
                    ),
                    Text(
                      field['value']?.toString() ?? '',
                      style: TextStyle(fontSize: 14),
                    ),
                  ],
                ),
              ),
            );
          }
        }
      } else if (fields is Map) {
        // fields가 맵인 경우
        fields.forEach((key, value) {
          fieldWidgets.add(
            Padding(
              padding: const EdgeInsets.only(bottom: 8.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    key,
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                  ),
                  Text(value?.toString() ?? '', style: TextStyle(fontSize: 14)),
                ],
              ),
            ),
          );
        });
      }

      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: fieldWidgets,
      );
    } catch (e) {
      if (kDebugMode) {
        print('필드 처리 중 오류: $e');
      }
      return SizedBox.shrink();
    }
  }
}
