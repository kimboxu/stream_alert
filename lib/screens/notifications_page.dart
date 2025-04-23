// lib/screens/notifications_page.dart 개선 버전
// ignore_for_file: avoid_print

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/notification_model.dart';
import '../services/api_service.dart';
import '../widgets/discord_notification_widget.dart';

class NotificationsPage extends StatefulWidget {
  const NotificationsPage({super.key});

  @override
  // ignore: library_private_types_in_public_api
  _NotificationsPageState createState() => _NotificationsPageState();
}

class _NotificationsPageState extends State<NotificationsPage>
    with AutomaticKeepAliveClientMixin {
  List<NotificationModel> _notifications = [];
  bool _isLoading = true;
  bool _isLoadingMore = false;
  bool _hasMoreData = true;
  bool _isRefreshing = false;
  bool _loadFailed = false;
  bool _isOffline = false;
  int _currentPage = 1;
  final int _pageSize = 50;

  // 스크롤 관련 변수
  final ScrollController _scrollController = ScrollController();
  final bool _autoScrollEnabled = false;
  bool _isNearBottom = true;
  bool _hasNewMessage = false;
  int _newMessageCount = 0;

  // 타이머 관리
  Timer? _debounceTimer;
  final List<Timer> _activeTimers = [];
  StreamSubscription<RemoteMessage>? _messageSubscription;

  // 필터 관련 변수
  NotificationType? _selectedFilter;
  final TextEditingController _searchController = TextEditingController();
  String _searchQuery = '';

  @override
  bool get wantKeepAlive => true; // 페이지 상태 유지

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_scrollListener);

    // 오프라인 상태 확인
    _checkConnectivity().then((_) {
      _loadFirstNotifications();
    });

    _setupMessageListener();
  }

  @override
  void dispose() {
    _cleanupTimers();
    _messageSubscription?.cancel();
    _scrollController.removeListener(_scrollListener);
    _scrollController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  // 네트워크 연결 상태 확인
  Future<void> _checkConnectivity() async {
    try {
      final result = await InternetAddress.lookup('google.com');
      if (result.isNotEmpty && result[0].rawAddress.isNotEmpty) {
        setState(() {
          _isOffline = false;
        });
      }
    } on SocketException catch (_) {
      setState(() {
        _isOffline = true;
        _loadFailed = true;
      });
    }
  }

  // 모든 타이머 정리
  void _cleanupTimers() {
    _debounceTimer?.cancel();
    for (final timer in _activeTimers) {
      if (timer.isActive) {
        timer.cancel();
      }
    }
    _activeTimers.clear();
  }

  // FCM 메시지 리스너 설정
  void _setupMessageListener() {
    _messageSubscription = FirebaseMessaging.onMessage.listen((
      RemoteMessage message,
    ) {
      _addNewNotification(message);
    });
  }

  // 초기 데이터 로드 (로컬+서버)
  Future<void> _loadFirstNotifications() async {
    setState(() {
      _isLoading = true;
      _loadFailed = false;
    });

    try {
      // 1. 먼저 로컬 데이터 로드
      List<NotificationModel> localNotifications =
          await _getLocalNotifications();

      if (mounted) {
        setState(() {
          _notifications = localNotifications;
          _isLoading = false;
        });
      }

      // 2. 네트워크 연결 확인
      if (_isOffline) return;

      // 3. 서버에서 최신 데이터 로드
      _loadServerNotifications();
      _removeDuplicateNotifications();
    } catch (e) {
      if (kDebugMode) {
        print('초기 알림 로드 중 오류: $e');
      }
      if (mounted) {
        setState(() {
          _isLoading = false;
          _loadFailed = true;
        });
      }
    }
  }

  // 로컬 데이터 로드
  Future<List<NotificationModel>> _getLocalNotifications() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final localNotificationsJson = prefs.getStringList('notifications') ?? [];

      if (localNotificationsJson.isEmpty) {
        return [];
      }

      List<NotificationModel> localNotifications =
          localNotificationsJson
              .map((json) => NotificationModel.fromJson(jsonDecode(json)))
              .toList();

      // 시간순 정렬
      localNotifications.sort((a, b) => b.timestamp.compareTo(a.timestamp));

      return localNotifications;
    } catch (e) {
      if (kDebugMode) {
        print('로컬 알림 로드 중 오류: $e');
      }
      return [];
    }
  }

  // 서버에서 알림 로드
  Future<void> _loadServerNotifications() async {
    if (_isOffline) return;

    try {
      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username');
      final discordWebhooksURL = prefs.getString('discordWebhooksURL');

      if (username == null || discordWebhooksURL == null) return;

      // 서버에서 알림 로드
      final serverNotifications = await ApiService.getNotifications(
        username,
        discordWebhooksURL,
        page: 1,
        limit: _pageSize,
      );

      if (!mounted) return;

      // 중복 제거를 위한 ID 집합
      final Set<String> uniqueIds = _notifications.map((n) => n.id).toSet();
      final List<NotificationModel> newNotifications = [];

      // 중복 체크하고 새 항목만 추가
      for (var notification in serverNotifications) {
        if (!uniqueIds.contains(notification.id)) {
          newNotifications.add(notification);
          uniqueIds.add(notification.id); // 새 ID도 추가하여 후속 비교 시 중복 방지
        }
      }

      if (newNotifications.isNotEmpty) {
        setState(() {
          // 새 알림 추가하고 시간순 정렬
          _notifications.addAll(newNotifications);
          _notifications.sort((a, b) => b.timestamp.compareTo(a.timestamp));
          _currentPage = 1;
          _hasMoreData = true;
        });

        _removeDuplicateNotifications();
        // 로컬에 저장
        // _updateLocalNotifications(_notifications);
      }
    } catch (e) {
      if (kDebugMode) {
        print('서버 알림 로드 중 오류: $e');
      }
    }
  }

  // 과거 알림 로드 (스크롤 시)
  Future<void> _loadOlderMessages() async {
    // 이미 로딩 중이거나 오프라인이면 실행하지 않음
    if (_isLoadingMore || _isOffline) return;

    setState(() {
      _isLoadingMore = true;
      _loadFailed = false;
    });

    try {
      // 사용자 정보 가져오기
      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username');
      final discordWebhooksURL = prefs.getString('discordWebhooksURL');

      if (username != null && discordWebhooksURL != null) {
        // 다음 페이지 데이터 가져오기
        final newNotifications = await ApiService.getNotifications(
          username,
          discordWebhooksURL,
          page: _currentPage + 1, // 다음 페이지 요청
          limit: _pageSize,
        );

        if (!mounted) return;

        if (newNotifications.isEmpty) {
          // 더 이상 데이터가 없으면 hasMoreData를 false로 설정
          setState(() {
            _hasMoreData = false;
            _isLoadingMore = false;
          });
        } else {
          // 중복 체크를 위한 ID Set 생성
          final existingIds = _notifications.map((n) => n.id).toSet();

          // 중복되지 않은 항목만 필터링
          final uniqueNotifications =
              newNotifications
                  .where(
                    (notification) => !existingIds.contains(notification.id),
                  )
                  .toList();

          if (uniqueNotifications.isEmpty) {
            // 모든 항목이 중복이면 다음 페이지로 넘어감
            _currentPage++; // 페이지 증가
            setState(() {
              _isLoadingMore = false;
            });
            // 재귀적으로 다음 페이지 데이터 로드
            _loadOlderMessages();
            return;
          }

          setState(() {
            // 고유 항목을 기존 목록 앞에 추가 (더 오래된 메시지)
            _notifications.insertAll(0, uniqueNotifications);
            _notifications.sort((a, b) => b.timestamp.compareTo(a.timestamp));
            _currentPage++; // 페이지 증가
            _isLoadingMore = false;
          });

          _removeDuplicateNotifications();
          // 백그라운드에서 로컬 저장 처리
          // _updateLocalNotifications(_notifications);
        }
      } else {
        // 사용자 정보가 없는 경우
        setState(() {
          _isLoadingMore = false;
          _loadFailed = true;
        });
      }
    } catch (e) {
      // API 호출 오류 처리
      if (kDebugMode) {
        print('더 많은 알림 로드 중 오류: $e');
      }

      setState(() {
        _isLoadingMore = false;
        _loadFailed = true;
      });

      // 네트워크 연결 확인
      try {
        await _checkConnectivity();
      } catch (_) {}

      // 오프라인이 아니면 스낵바 표시
      if (!_isOffline && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('이전 알림을 불러오는 중 오류가 발생했습니다'),
            action: SnackBarAction(
              label: '다시 시도',
              onPressed: () => _loadOlderMessages(),
            ),
            duration: const Duration(seconds: 4),
          ),
        );
      }
    }
  }

  // 스크롤 리스너
  void _scrollListener() {
    // 스크롤 리스너에 디바운싱 적용
    if (_debounceTimer?.isActive ?? false) {
      _debounceTimer?.cancel(); // 기존 타이머 취소
    }

    _debounceTimer = Timer(const Duration(milliseconds: 100), () {
      if (!mounted) return;

      try {
        // 현재 스크롤 위치 확인
        if (_scrollController.hasClients) {
          final maxScroll = _scrollController.position.maxScrollExtent;
          final currentScroll = _scrollController.position.pixels;

          // reverse: true 리스트에서는 스크롤 값이 0에 가까울수록 하단(최신 메시지)
          // 일정 값 이하면 하단으로 간주
          bool isNearBottom = currentScroll < 50; // 50픽셀 이하일 때 하단으로 간주

          // 상태가 변경되었을 때만 setState 호출하여 성능 최적화
          if (isNearBottom != _isNearBottom && mounted) {
            setState(() {
              _isNearBottom = isNearBottom;
              if (isNearBottom) {
                _hasNewMessage = false;
                _newMessageCount = 0;
              }
            });
          }

          // 무한 스크롤 로직 - 스크롤 위치가 일정 지점을 넘어가면 더 많은 데이터 로드
          if (!_isLoadingMore && _hasMoreData && mounted) {
            if (currentScroll >= maxScroll * 0.7) {
              // 70% 지점에서 데이터 로드 시작
              _loadOlderMessages();
            }
          }
        }
      } catch (e) {
        // 스크롤 위치 읽기 오류 처리
        if (kDebugMode) {
          print('스크롤 위치 읽기 오류: $e');
        }
      }
    });
    // 생성된 타이머를 목록에 추가
    _activeTimers.add(_debounceTimer!);
  }

  // 로컬에 알림 저장
  Future<void> _updateLocalNotifications(
    List<NotificationModel> notifications,
  ) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final notificationsJson =
          notifications
              .map((notification) => jsonEncode(notification.toJson()))
              .toList();

      await prefs.setStringList('notifications', notificationsJson);
    } catch (e) {
      if (kDebugMode) {
        print('알림 로컬 저장 중 오류: $e');
      }
    }
  }

  // 알림 리프레시
  Future<void> _refreshNotifications() async {
    if (_isRefreshing) return;

    setState(() {
      _isRefreshing = true;
    });

    try {
      await _checkConnectivity();

      if (_isOffline) {
        setState(() {
          _isRefreshing = false;
        });
        return;
      }

      // 서버에서 최신 데이터 가져오기
      await _loadServerNotifications();

      // 중복 알림 제거
      _removeDuplicateNotifications();

      setState(() {
        _isRefreshing = false;
      });
    } catch (e) {
      setState(() {
        _isRefreshing = false;
        _loadFailed = true;
      });

      if (kDebugMode) {
        print('새로고침 중 오류: $e');
      }
    }
  }

  // 중복 알림 제거
  void _removeDuplicateNotifications() {
    // ID 기준으로 중복 제거
    final Map<String, NotificationModel> uniqueNotifications = {};

    for (var notification in _notifications) {
      // 항상 가장 최신 버전의 알림을 유지
      if (!uniqueNotifications.containsKey(notification.id) ||
          notification.timestamp.isAfter(
            uniqueNotifications[notification.id]!.timestamp,
          )) {
        uniqueNotifications[notification.id] = notification;
      }
    }

    // 맵에서 리스트로 변환하고 시간순 정렬
    final List<NotificationModel> deduplicatedList =
        uniqueNotifications.values.toList()
          ..sort((a, b) => b.timestamp.compareTo(a.timestamp));

    if (_notifications.length != deduplicatedList.length) {
      if (kDebugMode) {
        print('중복 알림 ${_notifications.length - deduplicatedList.length}개 제거됨');
      }

      setState(() {
        _notifications = deduplicatedList;
      });

      // 로컬에 저장
      _updateLocalNotifications(deduplicatedList);
    }
  }

  // 새 메시지 알림 추가
  void _addNewNotification(RemoteMessage message) async {
    if (!mounted) return;

    try {
      // 새 알림 데이터 생성
      final String messageId =
          message.messageId ?? DateTime.now().millisecondsSinceEpoch.toString();

      final notificationData = {
        'id': messageId,
        'username':
            message.notification?.title ?? message.data['username'] ?? '알림',
        'content': message.notification?.body ?? message.data['content'] ?? '',
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
          // 새 알림 추가 - 최신 메시지를 목록 끝에 추가
          _notifications.add(newNotification);
          // 정렬
          _notifications.sort((a, b) => b.timestamp.compareTo(a.timestamp));
        }
        _removeDuplicateNotifications();
        // 로컬에도 저장
        // _updateLocalNotifications(_notifications);
      });

      // 자동 스크롤이 활성화된 경우에만 하단으로 스크롤
      if (_autoScrollEnabled && _scrollController.hasClients && mounted) {
        Future.delayed(Duration(milliseconds: 100), () {
          if (_scrollController.hasClients) {
            _scrollController.animateTo(
              0, // 역방향 리스트뷰에서는 0이 최하단(최신 메시지)
              duration: Duration(milliseconds: 300),
              curve: Curves.easeOut,
            );
          }
        });
      } else if (!_isNearBottom && _scrollController.hasClients && mounted) {
        // 새 메시지 알림 UI 표시 - 새 메시지가 왔고 현재 하단에 있지 않을 때 표시
        setState(() {
          _hasNewMessage = true;
          _newMessageCount++;
        });
      }
    } catch (e) {
      if (kDebugMode) {
        print('새 알림 추가 중 오류: $e');
      }
    }
  }

  // 알림 필터링
  List<NotificationModel> get _filteredNotifications {
    return _notifications.where((notification) {
      // 유형 필터 적용
      if (_selectedFilter != null && notification.type != _selectedFilter) {
        return false;
      }

      // 검색어 필터 적용
      if (_searchQuery.isNotEmpty) {
        return notification.username.toLowerCase().contains(
              _searchQuery.toLowerCase(),
            ) ||
            notification.content.toLowerCase().contains(
              _searchQuery.toLowerCase(),
            ) ||
            notification.title.toLowerCase().contains(
              _searchQuery.toLowerCase(),
            ) ||
            notification.description.toLowerCase().contains(
              _searchQuery.toLowerCase(),
            );
      }

      return true;
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context); // AutomaticKeepAliveClientMixin 요구사항

    return Scaffold(
      appBar: AppBar(
        title: Text('받은 알림'),
        actions: [
          // 필터 아이콘
          IconButton(
            icon: Icon(Icons.filter_list),
            onPressed: _showFilterDialog,
            tooltip: '알림 필터',
          ),
          // 새로고침 아이콘
          IconButton(
            icon: Icon(Icons.refresh),
            onPressed:
                (_isRefreshing || _isLoading) ? null : _refreshNotifications,
            tooltip: '알림 새로고침',
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            // 검색 필드
            Padding(
              padding: const EdgeInsets.all(8.0),
              child: TextField(
                controller: _searchController,
                decoration: InputDecoration(
                  hintText: '알림 검색...',
                  prefixIcon: Icon(Icons.search),
                  suffixIcon:
                      _searchQuery.isNotEmpty
                          ? IconButton(
                            icon: Icon(Icons.clear),
                            onPressed: () {
                              _searchController.clear();
                              setState(() {
                                _searchQuery = '';
                              });
                            },
                          )
                          : null,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                  contentPadding: EdgeInsets.symmetric(vertical: 0),
                ),
                onChanged: (value) {
                  setState(() {
                    _searchQuery = value;
                  });
                },
              ),
            ),

            // 필터 표시기
            if (_selectedFilter != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8.0),
                child: Row(
                  children: [
                    Text('필터: ', style: TextStyle(fontWeight: FontWeight.bold)),
                    Chip(
                      label: Text(_getFilterName(_selectedFilter!)),
                      onDeleted: () {
                        setState(() {
                          _selectedFilter = null;
                        });
                      },
                    ),
                    Spacer(),
                    if (_filteredNotifications.length != _notifications.length)
                      Text(
                        '${_filteredNotifications.length}/${_notifications.length}개 표시',
                        style: TextStyle(color: Colors.grey),
                      ),
                  ],
                ),
              ),

            // 오프라인 배너
            if (_isOffline)
              Container(
                color: Colors.amber[700],
                padding: EdgeInsets.symmetric(vertical: 8, horizontal: 16),
                child: Row(
                  children: [
                    Icon(Icons.wifi_off, color: Colors.white),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '오프라인 상태입니다. 저장된 알림만 표시됩니다.',
                        style: TextStyle(color: Colors.white),
                      ),
                    ),
                    TextButton(
                      onPressed: () async {
                        await _checkConnectivity();
                        if (!_isOffline) {
                          _refreshNotifications();
                        }
                      },
                      style: TextButton.styleFrom(
                        backgroundColor: Colors.amber[900],
                      ),
                      child: Text('재연결', style: TextStyle(color: Colors.white)),
                    ),
                  ],
                ),
              ),

            // 메인 컨텐츠 영역
            Expanded(
              child:
                  _isLoading
                      ? Center(child: CircularProgressIndicator())
                      : _buildNotificationsList(),
            ),

            // 새 메시지 알림 배너 (하단에 표시)
            if (_hasNewMessage && !_isNearBottom)
              GestureDetector(
                onTap: () {
                  if (_scrollController.hasClients) {
                    _scrollController.animateTo(
                      0, // 최신 메시지 위치
                      duration: Duration(milliseconds: 300),
                      curve: Curves.easeOut,
                    );
                    setState(() {
                      _hasNewMessage = false;
                      _newMessageCount = 0;
                    });
                  }
                },
                child: Container(
                  color: Theme.of(context).primaryColor,
                  padding: EdgeInsets.symmetric(vertical: 10, horizontal: 16),
                  child: Center(
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          _newMessageCount > 0
                              ? '새 알림 $_newMessageCount개가 있습니다'
                              : '새 알림이 있습니다',
                          style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        SizedBox(width: 8),
                        Icon(Icons.arrow_downward, color: Colors.white),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
      floatingActionButton:
          _isNearBottom
              ? null
              : FloatingActionButton(
                onPressed: () {
                  if (_scrollController.hasClients) {
                    _scrollController.animateTo(
                      0, // 최신 메시지(하단)으로 이동
                      duration: Duration(milliseconds: 300),
                      curve: Curves.easeOut,
                    );
                    setState(() {
                      _hasNewMessage = false;
                      _newMessageCount = 0;
                    });
                  }
                },
                tooltip: '최신 알림으로',
                child: Icon(Icons.arrow_downward),
              ),
    );
  }

  // 알림 목록 위젯
  Widget _buildNotificationsList() {
    final filteredNotifications = _filteredNotifications;

    if (filteredNotifications.isEmpty) {
      return _buildEmptyState();
    }

    return RefreshIndicator(
      onRefresh: _refreshNotifications,
      child: NotificationListener<ScrollNotification>(
        onNotification: (scrollNotification) {
          if (scrollNotification is OverscrollNotification &&
              scrollNotification.overscroll < 0 &&
              _scrollController.position.pixels >=
                  _scrollController.position.maxScrollExtent - 20) {
            if (!_isLoadingMore &&
                _hasMoreData &&
                !_loadFailed &&
                !_isOffline) {
              _loadOlderMessages();
            }
          }
          return false;
        },
        child: ListView.builder(
          controller: _scrollController,
          physics: const AlwaysScrollableScrollPhysics(),
          reverse: true, // 최신 메시지를 하단에 표시
          itemCount:
              filteredNotifications.length +
              (_isLoadingMore ? 1 : 0) +
              (_loadFailed ? 1 : 0),
          itemBuilder: (context, index) {
            // 로딩 인디케이터 (리스트 상단)
            if (_isLoadingMore && index == 0) {
              return Padding(
                padding: const EdgeInsets.all(8.0),
                child: Center(child: CircularProgressIndicator()),
              );
            }

            // 로드 실패 메시지 (리스트 상단)
            if (_loadFailed && index == 0) {
              return Card(
                margin: EdgeInsets.all(8),
                color: Colors.red[100],
                child: Padding(
                  padding: const EdgeInsets.all(8.0),
                  child: Row(
                    children: [
                      Icon(Icons.error_outline, color: Colors.red),
                      SizedBox(width: 8),
                      Expanded(child: Text('이전 알림을 불러오는데 실패했습니다')),
                      TextButton(
                        onPressed: _loadOlderMessages,
                        child: Text('다시 시도'),
                      ),
                    ],
                  ),
                ),
              );
            }

            // 알림 항목 인덱스 계산
            final itemIndex = _isLoadingMore || _loadFailed ? index - 1 : index;
            if (itemIndex < 0 || itemIndex >= filteredNotifications.length) {
              return SizedBox.shrink();
            }

            // 알림 항목
            final notification = filteredNotifications[itemIndex];
            return DiscordNotificationWidget(
              notification: notification,
              onTap: () => _handleNotificationTap(notification),
            );
          },
        ),
      ),
    );
  }

  // 빈 상태 위젯
  Widget _buildEmptyState() {
    final theme = Theme.of(context);
    final isDarkMode = theme.brightness == Brightness.dark;

    // 메인 메시지와 부가 설명 결정
    String mainMessage;
    String subMessage;
    IconData iconData;
    Color iconColor;

    if (_loadFailed) {
      mainMessage = '알림을 불러오는 중 오류가 발생했습니다';
      subMessage = '네트워크 연결을 확인하고 다시 시도해보세요';
      iconData = Icons.error_outline;
      iconColor = Colors.red[300]!;
    } else if (_isOffline) {
      mainMessage = '오프라인 상태입니다';
      subMessage = '인터넷 연결이 없습니다. 연결 상태를 확인해주세요.';
      iconData = Icons.wifi_off;
      iconColor = Colors.amber[300]!;
    } else if (_searchQuery.isNotEmpty || _selectedFilter != null) {
      mainMessage = '검색 결과가 없습니다';
      subMessage = '다른 검색어나 필터를 시도해보세요';
      iconData = Icons.search_off;
      iconColor = isDarkMode ? Colors.grey[300]! : Colors.grey[600]!;
    } else {
      mainMessage = '받은 알림이 없습니다';
      subMessage = '스트리머 알림 설정을 확인해보세요';
      iconData = Icons.notifications_off_outlined;
      iconColor = isDarkMode ? Colors.grey[300]! : Colors.grey[600]!;
    }

    return RefreshIndicator(
      onRefresh: _refreshNotifications,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          SizedBox(
            height: MediaQuery.of(context).size.height * 0.7,
            child: Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    width: 80,
                    height: 80,
                    decoration: BoxDecoration(
                      color: isDarkMode ? Colors.grey[800] : Colors.grey[200],
                      shape: BoxShape.circle,
                    ),
                    child: Icon(iconData, size: 40, color: iconColor),
                  ),
                  SizedBox(height: 24),
                  Text(
                    mainMessage,
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w500,
                      color: iconColor,
                    ),
                  ),
                  SizedBox(height: 8),
                  Text(
                    subMessage,
                    style: TextStyle(
                      fontSize: 14,
                      color: isDarkMode ? Colors.grey[400] : Colors.grey[600],
                    ),
                    textAlign: TextAlign.center,
                  ),
                  SizedBox(height: 24),
                  ElevatedButton.icon(
                    onPressed: _refreshNotifications,
                    icon: Icon(Icons.refresh),
                    label: Text('새로고침'),
                    style: ElevatedButton.styleFrom(
                      padding: EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 8,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  // 알림 필터 다이얼로그
  void _showFilterDialog() {
    showDialog(
      context: context,
      builder:
          (context) => AlertDialog(
            title: Text('알림 필터'),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildFilterOption(null, '모든 알림'),
                  _buildFilterOption(NotificationType.youtube, '유튜브 알림'),
                  _buildFilterOption(NotificationType.cafe, '카페 알림'),
                  _buildFilterOption(NotificationType.streamStart, '뱅온 알림'),
                  _buildFilterOption(NotificationType.streamEnd, '방종 알림'),
                  _buildFilterOption(NotificationType.chat, '채팅 알림'),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: Text('닫기'),
              ),
            ],
          ),
    );
  }

  // 필터 옵션 위젯
  Widget _buildFilterOption(NotificationType? type, String label) {
    return RadioListTile<NotificationType?>(
      title: Text(label),
      value: type,
      groupValue: _selectedFilter,
      onChanged: (value) {
        setState(() {
          _selectedFilter = value;
        });
        Navigator.pop(context);
      },
    );
  }

  // 필터 이름 반환
  String _getFilterName(NotificationType type) {
    switch (type) {
      case NotificationType.youtube:
        return '유튜브 알림';
      case NotificationType.cafe:
        return '카페 알림';
      case NotificationType.streamStart:
        return '뱅온 알림';
      case NotificationType.streamChange:
        return '방제 변경 알림';
      case NotificationType.streamEnd:
        return '방종 알림';
      case NotificationType.chat:
        return '채팅 알림';
      case NotificationType.general:
        return '일반 알림';
    }
  }

  // 알림 탭 처리
  void _handleNotificationTap(NotificationModel notification) {
    // 알림을 읽음으로 표시
    setState(() {
      final index = _notifications.indexWhere((n) => n.id == notification.id);
      if (index != -1) {
        // 읽음 상태 변경 (서버에도 업데이트 필요)
        final updatedNotification = NotificationModel(
          id: notification.id,
          username: notification.username,
          content: notification.content,
          avatarUrl: notification.avatarUrl,
          timestamp: notification.timestamp,
          read: true,
          // 다른 속성들도 복사
          title: notification.title,
          imageUrl: notification.imageUrl,
          thumbnailUrl: notification.thumbnailUrl,
          url: notification.url,
          color: notification.color,
          fields: notification.fields,
          footerText: notification.footerText,
          footerIconUrl: notification.footerIconUrl,
          description: notification.description,
          authorName: notification.authorName,
          authorUrl: notification.authorUrl,
        );

        _notifications[index] = updatedNotification;

        // 로컬에도 저장
        _updateLocalNotifications(_notifications);
      }
    });

    // URL이 있으면 열기
    if (notification.url.isNotEmpty) {
      _launchUrl(notification.url);
    }
  }

  // URL 실행
  void _launchUrl(String url) async {
    if (url.isEmpty) return;

    try {
      final uri = Uri.parse(url);
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      }
    } catch (e) {
      print('URL 실행 중 오류: $e');
    }
  }
}
