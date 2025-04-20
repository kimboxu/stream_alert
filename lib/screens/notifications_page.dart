// lib/screens/notifications_page.dart
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
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
  }

  void _scrollListener() {
    if (_scrollController.position.pixels >=
        _scrollController.position.maxScrollExtent - 200) {
      if (!_isLoadingMore && _hasMoreData) {
        _loadMoreNotifications();
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

        // 정렬 (오래된 알림이 위에, 최신 알림이 아래에 오도록)
        _notifications.sort((a, b) => a.timestamp.compareTo(b.timestamp));
      });

      // 스크롤을 맨 아래로 이동
      Future.delayed(Duration(milliseconds: 100), () {
        if (_scrollController.hasClients) {
          _scrollController.animateTo(
            _scrollController.position.maxScrollExtent,
            duration: Duration(milliseconds: 300),
            curve: Curves.easeOut,
          );
        }
      });
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

  Future<void> _clearAllNotifications() async {
    // 확인 대화상자 표시
    final confirm =
        await showDialog<bool>(
          context: context,
          builder:
              (context) => AlertDialog(
                title: Text('모든 알림 삭제'),
                content: Text('모든 알림을 삭제하시겠습니까?'),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(false),
                    child: Text('취소'),
                  ),
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(true),
                    child: Text('삭제'),
                  ),
                ],
              ),
        ) ??
        false;

    if (confirm) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setStringList('notifications', []);

      // 서버에서도 알림 삭제 요청 (서버 측 구현 필요)
      // - ApiService.clearNotifications() 같은 메서드 구현 가능

      setState(() {
        _notifications = [];
      });

      ScaffoldMessenger.of(
        // ignore: use_build_context_synchronously
        context,
      ).showSnackBar(SnackBar(content: Text('모든 알림이 삭제되었습니다')));
    }
  }

  String _formatTimestamp(DateTime timestamp) {
    final now = DateTime.now();
    final difference = now.difference(timestamp);

    if (difference.inDays > 0) {
      // 하루 이상 지났으면 날짜 표시
      return DateFormat('yyyy.MM.dd HH:mm').format(timestamp);
    } else if (difference.inHours > 0) {
      // 시간 단위 표시
      return '${difference.inHours}시간 전';
    } else if (difference.inMinutes > 0) {
      // 분 단위 표시
      return '${difference.inMinutes}분 전';
    } else {
      // 방금 전
      return '방금 전';
    }
  }

  // NotificationsPage 클래스 내에 추가
  Future<void> _generateTestNotifications() async {
    final prefs = await SharedPreferences.getInstance();
    final List<String> testNotifications = [];

    // 샘플 아바타 URL 및 사용자명
    final avatars = [
      'https://ui-avatars.com/api/?name=Big+Head&background=random',
      'https://ui-avatars.com/api/?name=Park+Dong&background=random',
      'https://ui-avatars.com/api/?name=Kim+Ppang&background=random',
    ];

    final usernames = ['빅헤드', '파크성', '김뽕'];

    // 샘플 메시지
    final messages = [
      '뱅온했습니다!',
      '안녕하세요 빅헤드입니다.',
      '방제가 변경되었습니다: 오늘은 롤 한판 고?',
      'VOD가 업로드되었습니다: 어제의 방송 하이라이트',
      '새로운 영상이 업로드되었습니다: 우왁굳 레전드 플레이 모음.zip',
      '거기있는너! 에이펙스 좋아하잖아',
      '방송 종료했습니다. 내일 뵐게요!',
    ];

    // 현재 시간
    final now = DateTime.now();

    // 테스트 알림 10개 생성
    for (int i = 0; i < 10; i++) {
      final randomUserIndex = i % usernames.length;
      final randomMsgIndex = i % messages.length;

      final notificationData = {
        'id': 'test-${DateTime.now().millisecondsSinceEpoch}-$i',
        'username': usernames[randomUserIndex],
        'content': messages[randomMsgIndex],
        'avatar_url': avatars[randomUserIndex],
        'timestamp': now.subtract(Duration(minutes: i * 30)).toIso8601String(),
        'read': false,
      };

      testNotifications.add(jsonEncode(notificationData));
    }

    // 저장
    await prefs.setStringList('notifications', testNotifications);

    // UI 업데이트
    await _loadNotifications();

    // 안내 메시지 표시
    ScaffoldMessenger.of(
      // ignore: use_build_context_synchronously
      context,
    ).showSnackBar(SnackBar(content: Text('테스트 알림이 생성되었습니다')));
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
          if (kDebugMode)
            IconButton(
              icon: Icon(Icons.science),
              onPressed: _generateTestNotifications,
              tooltip: '테스트 알림 생성',
            ),
          IconButton(
            icon: Icon(Icons.delete_sweep),
            onPressed: _notifications.isEmpty ? null : _clearAllNotifications,
            tooltip: '모든 알림 삭제',
          ),
        ],
      ),
      body:
          _isLoading
              ? Center(child: CircularProgressIndicator())
              : RefreshIndicator(
                onRefresh: _refreshNotifications,
                child:
                    _notifications.isEmpty
                        ? _buildEmptyNotifications()
                        : _buildNotificationsList(),
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
    return ListView.builder(
      controller: _scrollController,
      physics: AlwaysScrollableScrollPhysics(),
      itemCount: _notifications.length,
      itemBuilder: (context, index) {
        final notification = _notifications[index];
        return _buildNotificationItem(notification);
      },
    );
  }

  Widget _buildNotificationItem(NotificationModel notification) {
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
              child: notification.avatarUrl.isEmpty ? Icon(Icons.person) : null,
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
                        style: TextStyle(color: Colors.grey[600], fontSize: 12),
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
