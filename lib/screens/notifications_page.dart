// ignore_for_file: library_private_types_in_public_api, unnecessary_import

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:scrollable_positioned_list/scrollable_positioned_list.dart';

import '../models/notification_model.dart';
import '../services/api_service.dart';
import '../services/push_notification_service.dart';
import '../widgets/discord_notification_widget.dart';

enum LoadDirection {
  newer, // 최신 알림 로드 (첫 페이지)
  older, // 과거 알림 로드 (다음 페이지)
}

class NotificationsPage extends StatefulWidget {
  const NotificationsPage({super.key});

  @override
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
  final ItemScrollController _itemScrollController = ItemScrollController();
  final ItemPositionsListener _itemPositionsListener =
      ItemPositionsListener.create();

  bool _isNearBottom = true;
  bool _hasNewMessage = false;
  int _newMessageCount = 0;

  // 최하단으로부터 몇 개의 메시지까지를 하단으로 간주할지 설정
  final int _bottomThreshold = 10;
  final int _autoScrollThreshold = 3; // 자동 스크롤을 위한 하단 근접 임계값
  bool _autoScrollEnabled = false;

  //
  Timer? _debounceTimer;
  final List<Timer> _activeTimers = [];

  // 필터 관련 변수
  NotificationType? _selectedFilter;
  final TextEditingController _searchController = TextEditingController();
  String _searchQuery = '';

  // 오류 관리를 위한 상태 변수
  bool _showErrorMessage = false;
  String _errorMessage = '';

  @override
  bool get wantKeepAlive => true; // 페이지 상태 유지

  @override
  void initState() {
    super.initState();

    // 아이템 위치 리스너 설정
    _itemPositionsListener.itemPositions.addListener(_updateScrollPosition);

    // 오프라인 상태 확인
    _checkConnectivity().then((_) {
      _loadFirstNotifications();
    });

    _setupNotificationReceiver();
  }

  // 알림 수신 메서드
  void _setupNotificationReceiver() {
    PushNotificationService().notificationStream.listen((notification) {
      // 약간의 딜레이를 추가하여 비슷한 시간에 들어오는 메시지들이 한꺼번에 처리되도록 함
      Future.delayed(const Duration(milliseconds: 50), () {
        if (!mounted) return;
        _handleNewNotification(notification);
      });
    });
  }

  void _handleNewNotification(NotificationModel notification) {
    if (!mounted) return;

    setState(() {
      _notifications.add(notification);
      _removeDuplicateNotifications();

      if (!_autoScrollEnabled) {
        _hasNewMessage = true;
        _newMessageCount++;
      }
    });

    debugPrint('새 메시지 수신: 매우 하단 여부: $_autoScrollEnabled');

    // 자동 스크롤 로직
    if (_autoScrollEnabled && _itemScrollController.isAttached && mounted) {
      Future.delayed(const Duration(milliseconds: 100), () {
        _itemScrollController.scrollTo(
          index: 0, // 최신 메시지 위치
          duration: const Duration(milliseconds: 200),
        );
      });
    }
  }

  // 스크롤 위치에 따라 상태 업데이트
  void _updateScrollPosition() {
    if (!mounted || _itemPositionsListener.itemPositions.value.isEmpty) return;

    if (_debounceTimer?.isActive ?? false) {
      _debounceTimer?.cancel(); // 기존 타이머 취소
    }

    _debounceTimer = Timer(const Duration(milliseconds: 100), () {
      if (!mounted) return;

      try {
        // 현재 보이는 아이템 위치들 가져오기
        final positions = _itemPositionsListener.itemPositions.value;

        if (positions.isEmpty) return;

        // 보이는 아이템 중 가장 작은 인덱스 (가장 최근 메시지)
        final int smallestIndex = positions
            .where((ItemPosition position) => position.itemTrailingEdge > 0)
            .map((ItemPosition position) => position.index)
            .reduce((int min, int index) => index < min ? index : min);

        // 메시지 갯수 기준으로 하단 여부 판단
        final bool isNearBottom =
            smallestIndex < _bottomThreshold; // 일반 하단 여부 (_bottomThreshold=10)
        final bool isVeryNearBottom =
            smallestIndex <
            _autoScrollThreshold; // 자동 스크롤용 하단 여부 (_autoScrollThreshold=3)

        debugPrint(
          '현재 인덱스: $smallestIndex, 하단 여부: $isNearBottom, 매우 하단 여부: $isVeryNearBottom',
        );

        // 상태가 변경되었을 때만 setState 호출하여 성능 최적화
        if (isNearBottom != _isNearBottom ||
            isVeryNearBottom != _autoScrollEnabled) {
          setState(() {
            _isNearBottom = isNearBottom;
            _autoScrollEnabled = isVeryNearBottom;

            if (_autoScrollEnabled) {
              _hasNewMessage = false;
              _newMessageCount = 0;
            }
          });
        }

        // 무한 스크롤 로직
        if (!_isLoadingMore && _hasMoreData && mounted) {
          final totalItems = _getTotalItemsWithDividers();

          if (smallestIndex >= totalItems * 0.7) {
            _loadOlderMessages();
          }
        }
      } catch (e) {
        debugPrint('스크롤 위치 읽기 오류: $e');
      }
    });
    // 생성된 타이머를 목록에 추가
    _activeTimers.add(_debounceTimer!);
  }

  // 전체 아이템 수 계산 (날짜 구분선 포함)
  int _getTotalItemsWithDividers() {
    final filteredNotifications = _filteredNotifications;

    if (filteredNotifications.isEmpty) {
      return 0;
    }

    // 날짜 구분선 개수 추정 - 날짜별로 그룹화
    final Set<DateTime> uniqueDates = {};
    for (var notification in filteredNotifications) {
      final date = DateTime(
        notification.timestamp.year,
        notification.timestamp.month,
        notification.timestamp.day,
      );
      uniqueDates.add(date);
    }

    // 알림 개수 + 날짜 구분선 개수 + "더 이상 알림이 없습니다" 메시지(조건부)
    return filteredNotifications.length +
        uniqueDates.length +
        (_hasMoreData ? 0 : 1);
  }

  @override
  void dispose() {
    _cleanupTimers();
    _itemPositionsListener.itemPositions.removeListener(_updateScrollPosition);
    _searchController.dispose();
    super.dispose();
  }

  // 모든 타이머 정리
  void _cleanupTimers() {
    for (final timer in _activeTimers) {
      if (timer.isActive) {
        timer.cancel();
      }
    }
    _activeTimers.clear();
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

      // 시간순 정렬(최근 메시지가 앞으로)
      localNotifications.sort((a, b) => b.timestamp.compareTo(a.timestamp));

      return localNotifications;
    } catch (e) {
      debugPrint('로컬 알림 로드 중 오류: $e');

      return [];
    }
  }

  Future<void> _loadNotifications({
    required LoadDirection direction,
    bool isRefreshing = false,
  }) async {
    // 로딩 상태 설정
    if (_isOffline) return;
    if (direction == LoadDirection.newer) {
      if (isRefreshing) {
        if (_isRefreshing) return;
        setState(() {
          _isRefreshing = true;
        });
      } else {
        if (_isLoading) return;
        setState(() {
          _isLoading = true;
          _loadFailed = false;
        });
      }
    } else {
      // LoadDirection.older
      if (_isLoadingMore) return;
      setState(() {
        _isLoadingMore = true;
        _loadFailed = false;
      });
    }

    try {
      // 요청할 페이지 번호 결정
      int pageToLoad = direction == LoadDirection.newer ? 1 : _currentPage + 1;

      // 서버에서 알림 로드
      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username');
      final discordWebhooksURL = prefs.getString('discordWebhooksURL');

      if (username == null || discordWebhooksURL == null) {
        setState(() {
          _isLoading = false;
          _isRefreshing = false;
          _isLoadingMore = false;
          _loadFailed = true;
        });
        return;
      }

      // 서버 API 호출
      final result = await ApiService.getNotifications(
        username,
        discordWebhooksURL,
        page: pageToLoad,
        limit: _pageSize,
      );

      if (!mounted) return;

      setState(() {
        _isLoading = false;
        _isRefreshing = false;
        _isLoadingMore = false;
      });

      // 결과 처리
      if (result['success']) {
        final List<NotificationModel> newNotifications =
            result['notifications'];
        final bool hasMore = result['hasMore'];

        setState(() {
          // 새 알림이 있는 경우에만 알림 목록 업데이트
          if (newNotifications.isNotEmpty) {
            if (direction == LoadDirection.newer) {
              // 최신 알림은 기존 목록에 추가
              _notifications.addAll(newNotifications);
              _currentPage = 1;
            } else {
              // 과거 알림은 목록 앞에 삽입
              _notifications.insertAll(0, newNotifications);
              _currentPage++;
            }
          }

          _hasMoreData = hasMore;
        });

        // 새 알림이 있는 경우에만 중복 제거
        if (newNotifications.isNotEmpty) {
          // 로그 출력
          if (direction == LoadDirection.older) {
            final oldestNewTime = newNotifications
                .map((n) => n.timestamp)
                .reduce((a, b) => a.isBefore(b) ? a : b);
            debugPrint('새로 가져온 가장 오래된 알림 시간: $oldestNewTime');
          }

          // 중복 제거
          _removeDuplicateNotifications();
        }
      } else {
        // 오류가 발생한 경우
        final String errorType = result['errorType'] ?? 'unknown';
        final String serverError = result['error'] ?? '알림을 불러오는 중 오류가 발생했습니다';

        // 디버그 로깅
        debugPrint('알림 로드 오류: type=$errorType, message=$serverError');

        setState(() {
          _loadFailed = true;

          // 네트워크 오류가 아니고 과거 알림 로드인 경우에만 더 이상 데이터가 없음으로 설정
          if (errorType != 'network' && direction == LoadDirection.older) {
            _hasMoreData = false;
          }
        });

        // 상황에 맞는 사용자 친화적 오류 메시지 결정
        String userMessage;

        if (direction == LoadDirection.newer) {
          // 최신 알림 로드 중 오류
          if (!_isOffline && errorType == 'network') {
            userMessage = '알림을 새로고침하는 중 네트워크 오류가 발생했습니다';
          } else {
            userMessage = '알림을 불러오는 중 오류가 발생했습니다';
          }
        } else {
          // 과거 알림 로드 중 오류
          switch (errorType) {
            case 'network':
              userMessage = '이전 알림을 불러오는 중 네트워크 연결 오류가 발생했습니다';
              break;
            case 'auth':
              userMessage = '인증 정보가 만료되었습니다. 다시 로그인해주세요';
              break;
            case 'server':
              userMessage = '서버에서 오류가 발생했습니다. 잠시 후 다시 시도해주세요';
              break;
            default:
              userMessage = serverError; // 서버에서 제공한 오류 메시지 사용
          }
        }

        _setErrorMessage(userMessage);
      }
    } catch (e) {
      debugPrint('알림 로드 중 예상치 못한 오류: $e');

      // 로딩 상태 해제 및 오류 상태 설정
      setState(() {
        _isLoading = false;
        _isRefreshing = false;
        _isLoadingMore = false;
        _loadFailed = true;
      });

      // 네트워크 연결 확인
      try {
        await _checkConnectivity();
      } catch (_) {}

      // 오류 메시지 표시
      _setErrorMessage('예상치 못한 오류가 발생했습니다: $e');
    }
  }

  //초기 데이터 로드 (로컬+서버)
  Future<void> _loadFirstNotifications() async {
    List<NotificationModel> localNotifications = await _getLocalNotifications();

    if (mounted) {
      setState(() {
        _notifications = localNotifications;
        _isLoading = false;
      });
    }

    // 서버에서 최신 데이터 로드
    await _loadNotifications(direction: LoadDirection.newer);
  }

  Future<void> _loadOlderMessages() async {
    await _loadNotifications(direction: LoadDirection.older);
  }

  Future<void> _refreshNotifications() async {
    await _loadNotifications(
      direction: LoadDirection.newer,
      isRefreshing: true,
    );
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
      debugPrint('알림 로컬 저장 중 오류: $e');
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
      debugPrint(
        '중복 알림 ${_notifications.length - deduplicatedList.length}개 제거됨',
      );

      setState(() {
        _notifications = deduplicatedList;
      });

      // 로컬에 저장
      _updateLocalNotifications(deduplicatedList);
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
    super.build(context);

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
            if (_hasNewMessage && !_autoScrollEnabled)
              AnimatedOpacity(
                opacity: (_hasNewMessage && !_autoScrollEnabled) ? 1.0 : 0.0,
                duration: const Duration(milliseconds: 300),
                curve: Curves.easeInOut,
                child: IgnorePointer(
                  ignoring: !(_hasNewMessage && !_autoScrollEnabled),
                  child: GestureDetector(
                    onTap: () {
                      if (_itemScrollController.isAttached) {
                        _itemScrollController.scrollTo(
                          index: 0, // 최신 메시지 위치
                          duration: const Duration(milliseconds: 300),
                        );
                        setState(() {
                          _hasNewMessage = false;
                          _newMessageCount = 0;
                        });
                      }
                    },
                    child: Container(
                      color: Theme.of(context).primaryColor,
                      padding: const EdgeInsets.symmetric(
                        vertical: 10,
                        horizontal: 16,
                      ),
                      child: Center(
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(
                              _newMessageCount > 99
                                  ? '새 알림 99+개가 있습니다'
                                  : '새 알림 $_newMessageCount개가 있습니다',
                              style: const TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(width: 8),
                            const Icon(
                              Icons.arrow_downward,
                              color: Colors.white,
                            ),
                          ],
                        ),
                      ),
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
                  if (_itemScrollController.isAttached) {
                    _itemScrollController.scrollTo(
                      index: 0, // 최신 메시지(하단)으로 이동
                      duration: Duration(milliseconds: 300),
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
  } // 알림 목록 위젯

  Widget _buildNotificationsList() {
    final filteredNotifications = _filteredNotifications;

    if (filteredNotifications.isEmpty) {
      return _buildEmptyState();
    }

    // 알림 목록에 날짜 구분선 추가
    final List<dynamic> itemsWithDateDividers = [];

    // 알림을 순회하며 날짜 구분선 추가
    for (int i = 0; i < filteredNotifications.length; i++) {
      final notification = filteredNotifications[i];
      final currentDate = DateTime(
        notification.timestamp.year,
        notification.timestamp.month,
        notification.timestamp.day,
      );

      // 알림 추가
      itemsWithDateDividers.add(notification);

      // 다음 알림과 날짜 비교
      final bool isLastItem = i == filteredNotifications.length - 1;

      // 이전 날짜와 현재 날짜가 다르면 구분선 추가
      if (isLastItem ||
          currentDate.day !=
              DateTime(
                filteredNotifications[i + 1].timestamp.year,
                filteredNotifications[i + 1].timestamp.month,
                filteredNotifications[i + 1].timestamp.day,
              ).day) {
        itemsWithDateDividers.add(currentDate); // 날짜 구분선
      }
    }

    if (!_hasMoreData) {
      itemsWithDateDividers.add("NO_MORE_NOTIFICATIONS");
    }

    return RefreshIndicator(
      onRefresh: _refreshNotifications,
      child: Column(
        children: [
          // 상단에 오류 메시지 표시
          if (_showErrorMessage && _errorMessage.isNotEmpty)
            Card(
              margin: EdgeInsets.all(8),
              color: Colors.red[100],
              child: Padding(
                padding: const EdgeInsets.all(12.0),
                child: Column(
                  children: [
                    Row(
                      children: [
                        Icon(Icons.error_outline, color: Colors.red),
                        SizedBox(width: 8),
                        Expanded(child: Text(_errorMessage)),
                      ],
                    ),
                    SizedBox(height: 8),
                    OutlinedButton.icon(
                      onPressed: () {
                        setState(() {
                          _showErrorMessage = false;
                          _errorMessage = '';
                        });
                        _loadOlderMessages();
                      },
                      icon: Icon(Icons.refresh),
                      label: Text('이전 알림 다시 불러오기'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.red[700],
                        side: BorderSide(color: Colors.red[300]!),
                      ),
                    ),
                  ],
                ),
              ),
            ),

          // 데이터 로딩 중 표시
          if (_isLoadingMore && !_loadFailed)
            Padding(
              padding: const EdgeInsets.all(8.0),
              child: Center(child: CircularProgressIndicator()),
            ),

          // 로드 실패 메시지
          if (_loadFailed && !_showErrorMessage)
            Card(
              margin: EdgeInsets.all(8),
              color: Colors.red[100],
              child: Padding(
                padding: const EdgeInsets.all(12.0),
                child: Column(
                  children: [
                    Row(
                      children: [
                        Icon(Icons.error_outline, color: Colors.red),
                        SizedBox(width: 8),
                        Expanded(child: Text('이전 알림을 불러오는데 실패했습니다')),
                      ],
                    ),
                    SizedBox(height: 8),
                    OutlinedButton.icon(
                      onPressed: _loadOlderMessages,
                      icon: Icon(Icons.refresh),
                      label: Text('이전 알림 다시 불러오기'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.red[700],
                        side: BorderSide(color: Colors.red[300]!),
                      ),
                    ),
                    SizedBox(height: 4),
                    Text(
                      '또는 위로 스크롤하여 새로고침',
                      style: TextStyle(fontSize: 12, color: Colors.grey[700]),
                    ),
                  ],
                ),
              ),
            ),

          // 알림 목록
          Expanded(
            child: NotificationListener<ScrollNotification>(
              onNotification: (scrollNotification) {
                // 최상단에서 위로 스크롤하는 경우 더 오래된 데이터 로드
                if (scrollNotification is OverscrollNotification &&
                    scrollNotification.overscroll > 0) {
                  // 양수는 상단으로 오버스크롤

                  // 이미 최상단에 있는 경우
                  final positions = _itemPositionsListener.itemPositions.value;
                  if (positions.isNotEmpty) {
                    // 보이는 아이템 중 가장 큰 인덱스를 최상단으로 간주
                    final int largestIndex = positions
                        .map((ItemPosition position) => position.index)
                        .reduce(
                          (int max, int index) => index > max ? index : max,
                        );

                    if (largestIndex >= 3 &&
                        !_isLoadingMore &&
                        _hasMoreData &&
                        !_isOffline) {
                      // 로드 실패 상태였다면 초기화
                      if (_loadFailed) {
                        setState(() {
                          _loadFailed = false;
                        });
                      }

                      // 오래된 데이터 로드
                      _loadOlderMessages();
                      return true;
                    }
                  }
                }

                return false;
              },
              child: ScrollablePositionedList.builder(
                itemScrollController: _itemScrollController,
                itemPositionsListener: _itemPositionsListener,
                physics: const AlwaysScrollableScrollPhysics(),
                reverse: true, // 최신 메시지를 하단에 표시
                itemCount: itemsWithDateDividers.length,
                itemBuilder: (context, index) {
                  final itemIndex = index;
                  if (itemIndex < 0 ||
                      itemIndex >= itemsWithDateDividers.length) {
                    return SizedBox.shrink();
                  }

                  // 현재 아이템 가져오기
                  final item = itemsWithDateDividers[itemIndex];

                  // "더 이상 알림이 없습니다" 메시지 표시
                  if (item == "NO_MORE_NOTIFICATIONS") {
                    return Container(
                      padding: EdgeInsets.all(16),
                      alignment: Alignment.center,
                      child: Text(
                        '더 이상 알림이 없습니다',
                        style: TextStyle(
                          color: Colors.grey[600],
                          fontStyle: FontStyle.italic,
                        ),
                      ),
                    );
                  }

                  // 날짜 구분선인 경우
                  if (item is DateTime) {
                    return _buildDateDivider(item);
                  }

                  // 알림 항목인 경우
                  final notification = item as NotificationModel;
                  return DiscordNotificationWidget(
                    notification: notification,
                    onTap: () => _handleNotificationTap(notification),
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }

  // 날짜 구분선 위젯
  Widget _buildDateDivider(DateTime date) {
    String dateText = '${date.year}년 ${date.month}월 ${date.day}일';

    return Container(
      padding: EdgeInsets.symmetric(vertical: 8.0),
      margin: EdgeInsets.symmetric(vertical: 8.0, horizontal: 16.0),
      child: Row(
        children: [
          Expanded(child: Divider(color: Colors.grey[400])),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0),
            child: Text(
              dateText,
              style: TextStyle(
                color: Colors.grey[600],
                fontWeight: FontWeight.bold,
                fontSize: 12,
              ),
            ),
          ),
          Expanded(child: Divider(color: Colors.grey[400])),
        ],
      ),
    );
  }

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
      child: ScrollablePositionedList.builder(
        itemScrollController: _itemScrollController,
        itemPositionsListener: _itemPositionsListener,
        physics: const AlwaysScrollableScrollPhysics(),
        itemCount: 1, // 빈 상태는 1개 아이템으로 처리
        itemBuilder: (context, index) {
          return Column(
            children: [
              // 오류가 있는 경우 상단에 표시
              if (_showErrorMessage && _errorMessage.isNotEmpty)
                Card(
                  margin: EdgeInsets.all(8),
                  color: Colors.red[100],
                  child: Padding(
                    padding: const EdgeInsets.all(12.0),
                    child: Column(
                      children: [
                        Row(
                          children: [
                            Icon(Icons.error_outline, color: Colors.red),
                            SizedBox(width: 8),
                            Expanded(child: Text(_errorMessage)),
                          ],
                        ),
                        SizedBox(height: 8),
                        OutlinedButton.icon(
                          onPressed: () {
                            setState(() {
                              _showErrorMessage = false;
                              _errorMessage = '';
                            });
                            _refreshNotifications();
                          },
                          icon: Icon(Icons.refresh),
                          label: Text('이전 알림 다시 불러오기'),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: Colors.red[700],
                            side: BorderSide(color: Colors.red[300]!),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

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
                          color:
                              isDarkMode ? Colors.grey[800] : Colors.grey[200],
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
                          color:
                              isDarkMode ? Colors.grey[400] : Colors.grey[600],
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
          );
        },
      ),
    );
  }

  // 오류 메시지 설정 함수
  void _setErrorMessage(String message) {
    if (!mounted) return;

    setState(() {
      _showErrorMessage = true;
      _errorMessage = message;
    });
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
                  _buildFilterOption(NotificationType.streamChange, '방제 변경 알림'),
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
        _showFilterDialog();
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
        // 읽음 상태 변경
        final updatedNotification = NotificationModel(
          id: notification.id,
          username: notification.username,
          content: notification.content,
          avatarUrl: notification.avatarUrl,
          timestamp: notification.timestamp,
          read: true,
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

        // 로컬에 저장
        _updateLocalNotifications(_notifications);

        // 서버에 읽음 상태 업데이트
        // _markNotificationAsReadOnServer(notification.id);
      }
    });

    // URL이 있으면 열기
    if (notification.url.isNotEmpty) {
      ApiService.launchExternalUrl(notification.url);
    }
  }

  // 서버에 알림 읽음 상태 업데이트하는 메서드
  // Future<void> _markNotificationAsReadOnServer(String notificationId) async {
  //   try {
  //     final prefs = await SharedPreferences.getInstance();
  //     final username = prefs.getString('username');
  //     final discordWebhooksURL = prefs.getString('discordWebhooksURL');

  //     if (username != null && discordWebhooksURL != null) {
  //       // ApiService의 markNotificationsAsRead 함수 호출
  //       await ApiService.markNotificationsAsRead(
  //         username,
  //         discordWebhooksURL,
  //         [notificationId], // 단일 알림 ID를 리스트로 전달
  //       );
  //     }
  //   } catch (e) {
  //
  //       debugPrint('서버에 알림 읽음 상태 업데이트 중 오류: $e');
  //
  //   }
  // }

}
