// ignore_for_file: library_private_types_in_public_api, unnecessary_import, deprecated_member_use

import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:scrollable_positioned_list/scrollable_positioned_list.dart';
import 'package:flutter/scheduler.dart';

import '../models/notification_model.dart';
import '../services/api_service.dart';
import '../services/push_notification_service.dart';
import '../widgets/discord_notification_widget.dart';

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

  // 필터 관련 변수 - 중복 선택을 위해 Set 타입으로 변경
  Set<NotificationType> _selectedFilters = {};
  final TextEditingController _searchController = TextEditingController();
  String _searchQuery = '';

  // 오류 관리를 위한 상태 변수
  bool _showErrorMessage = false;
  String _errorMessage = '';

  late final AppLifecycleListener _lifecycleListener;

  @override
  bool get wantKeepAlive => true; // 페이지 상태 유지

  @override
  void initState() {
    super.initState();

    // 생명주기 리스너 설정
    _lifecycleListener = AppLifecycleListener(onStateChange: _onStateChanged);

    // 아이템 위치 리스너 설정
    _itemPositionsListener.itemPositions.addListener(_updateScrollPosition);

    // 모든 필터 타입을 기본적으로 선택된 상태로 초기화
    _selectedFilters = {
      NotificationType.youtube,
      NotificationType.cafe,
      NotificationType.chzzkVOD,
      NotificationType.streamStart,
      NotificationType.streamChange,
      NotificationType.streamEnd,
      NotificationType.chat,
    };

    // 오프라인 상태 확인
    _checkConnectivity().then((_) {
      _loadFirstNotifications();
    });

    _setupNotificationReceiver();
  }

  // 앱 상태 변경 처리
  void _onStateChanged(AppLifecycleState state) {
    debugPrint('앱 상태 변경: $state');
    if (state == AppLifecycleState.resumed) {
      debugPrint('앱이 포그라운드로 돌아옴');

      _loadFirstNotifications();
    }
  }

  // 알림 수신 메서드
  void _setupNotificationReceiver() {
    // 알림 스트림 리스너
    PushNotificationService().notificationStream.listen((notification) {
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
      _notifications.sort((a, b) => b.timestamp.compareTo(a.timestamp));
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

        // 무한 스크롤 로직 개선
        final filteredNotifications = _filteredNotifications;
        final itemsWithDividers = _getItemsWithDateDividers(
          filteredNotifications,
        );
        final totalItems = itemsWithDividers.length;

        // 1. 보이는 항목이 너무 적을 경우 (10개 미만) 자동으로 더 로드
        // 2. 상단에 접근한 경우 (위에서 30% 이내)에 로드
        // 3. 필터링된 결과가 너무 적을 경우 (5개 미만)에도 더 로드
        bool shouldLoadMore = false;

        // 표시된 항목이 적은 경우 (필터링으로 인해)
        if (filteredNotifications.length < 10 && _hasMoreData) {
          shouldLoadMore = true;
          debugPrint(
            '필터링된 알림이 적어 추가 데이터 로드 (${filteredNotifications.length}개)',
          );
        }

        // 스크롤 위치가 상단에 가까운 경우
        final largestIndex = positions
            .map((ItemPosition position) => position.index)
            .reduce((int max, int index) => index > max ? index : max);

        if (totalItems > 0 && largestIndex / totalItems > 0.7 && _hasMoreData) {
          shouldLoadMore = true;
          debugPrint('스크롤 위치 상단 근접 (${largestIndex / totalItems * 100}%)');
        }

        // 더 로드해야 하는 경우
        if (shouldLoadMore && !_isLoadingMore && !_isLoading && !_loadFailed) {
          _loadOlderMessages();
        }
      } catch (e) {
        debugPrint('스크롤 위치 읽기 오류: $e');
      }
    });
    // 생성된 타이머를 목록에 추가
    _activeTimers.add(_debounceTimer!);
  }

  // 날짜 구분선이 포함된 아이템 목록 계산
  List<dynamic> _getItemsWithDateDividers(
    List<NotificationModel> notifications,
  ) {
    final List<dynamic> itemsWithDateDividers = [];

    // 알림이 없는 경우 빈 목록 반환
    if (notifications.isEmpty) {
      return itemsWithDateDividers;
    }

    // 알림을 순회하며 날짜 구분선 추가
    for (int i = 0; i < notifications.length; i++) {
      final notification = notifications[i];

      // 타임스탬프를 로컬 시간대로 변환
      final localDateTime = notification.timestamp.toLocal();
      final currentDate = DateTime(
        localDateTime.year,
        localDateTime.month,
        localDateTime.day,
      );

      // 알림 추가
      itemsWithDateDividers.add(notification);

      // 다음 알림과 날짜 비교
      final bool isLastItem = i == notifications.length - 1;

      // 이전 날짜와 현재 날짜가 다르면 구분선 추가
      if (isLastItem ||
          currentDate.day !=
              DateTime(
                notifications[i + 1].timestamp.toLocal().year,
                notifications[i + 1].timestamp.toLocal().month,
                notifications[i + 1].timestamp.toLocal().day,
              ).day) {
        itemsWithDateDividers.add(currentDate); // 날짜 구분선
      }
    }

    if (!_hasMoreData) {
      itemsWithDateDividers.add("NO_MORE_NOTIFICATIONS");
    }

    return itemsWithDateDividers;
  }

  @override
  void dispose() {
    _lifecycleListener.dispose();
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

  Future<void> _loadNotifications({required LoadDirection direction}) async {
    // 중복 호출 방지
    if (_isOffline) return;
    if (direction == LoadDirection.newer) {
      if (_isLoading) return;
      setState(() {
        _isLoading = true;
        _loadFailed = false;
      });
    } else {
      if (_isLoadingMore) return;
      setState(() {
        _isLoadingMore = true;
        _loadFailed = false;
      });
    }

    // 서비스 호출
    final result = await PushNotificationService().loadNotifications(
      direction: direction,
      currentPage: _currentPage,
      pageSize: _pageSize,
    );

    if (!mounted) return;

    // 로딩 상태 해제
    //SchedulerBinding.instance.addPostFrameCallback, 현재 프레임이 완료된 후에 상대 업데이트
    SchedulerBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;

      setState(() {
        _isLoading = false;
        _isLoadingMore = false;

        // 결과 처리
        if (result['success']) {
          final List<NotificationModel> newNotifications = result['notifications'];
          final bool hasMore = result['hasMore'];
          final int updatedPage = result['currentPage'];

          if (newNotifications.isNotEmpty) {
            if (direction == LoadDirection.newer) {
              // 최신 알림은 기존 목록에 추가
              _notifications.addAll(newNotifications);
              _currentPage = 1;
            } else {
              // 과거 알림은 목록 앞에 삽입
              _notifications.insertAll(0, newNotifications);
              _currentPage = updatedPage;
            }
          }

          _hasMoreData = hasMore;

          // 중복 제거
          if (newNotifications.isNotEmpty) {
            _removeDuplicateNotifications();
          }
        } else {
          // 오류 처리
          _loadFailed = true;

          // 네트워크 오류인 경우 오프라인 상태 설정
          if (result['errorType'] == 'network') {
            _isOffline = true;
          }

          // 오류 메시지 설정
          _setErrorMessage(result['error']);
        }
      });
    });
  }

  // 초기 데이터 로드 (로컬+서버)
  Future<void> _loadFirstNotifications() async {
    // 로컬 알림 먼저 로드
    List<NotificationModel> localNotifications =
        await PushNotificationService().getLocalNotifications();

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
      PushNotificationService().updateLocalNotifications(deduplicatedList);
    }
  }

  // 알림 필터링
  List<NotificationModel> get _filteredNotifications {
    final filtered =
        _notifications.where((notification) {
          // 유형 필터 적용
          if (_selectedFilters.isEmpty) {
            return false; // 아무 필터도 선택되지 않았을 때 알림을 표시하지 않음
          }

          if (!_selectedFilters.contains(notification.type)) {
            return false; // 선택된 필터에 포함되지 않은 알림 제외
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

    // 항상 시간 순으로 정렬 (최신순)
    filtered.sort((a, b) => b.timestamp.compareTo(a.timestamp));

    return filtered;
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
            onPressed: (_isLoading) ? null : _loadFirstNotifications,
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
            if (_selectedFilters.isNotEmpty)
              Container(
                margin: const EdgeInsets.symmetric(
                  horizontal: 8.0,
                  vertical: 4.0,
                ),
                padding: const EdgeInsets.all(8.0),
                decoration: BoxDecoration(
                  color: Theme.of(context).primaryColor.withOpacity(0.05),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: Theme.of(context).primaryColor.withOpacity(0.2),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(
                          Icons.filter_list,
                          size: 16,
                          color: Theme.of(context).primaryColor,
                        ),
                        SizedBox(width: 4),
                        Text(
                          '필터',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: Theme.of(context).primaryColor,
                          ),
                        ),

                        Expanded(
                          child: Text(
                            ' · ${_filteredNotifications.length}/${_notifications.length}개 표시',
                            style: TextStyle(color: Colors.grey, fontSize: 12),
                          ),
                        ),
                      ],
                    ),
                    SizedBox(height: 8),
                    SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: Row(
                        children:
                            _selectedFilters.map((filterType) {
                              return Padding(
                                padding: const EdgeInsets.only(right: 4.0),
                                child: Chip(
                                  label: Text(_getFilterName(filterType)),
                                  labelStyle: TextStyle(fontSize: 12),
                                  padding: EdgeInsets.symmetric(
                                    horizontal: 6,
                                    vertical: 0,
                                  ),
                                  materialTapTargetSize:
                                      MaterialTapTargetSize.shrinkWrap,
                                  onDeleted: () {
                                    setState(() {
                                      _selectedFilters.remove(filterType);
                                    });
                                  },
                                ),
                              );
                            }).toList(),
                      ),
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
                          _loadFirstNotifications();
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
  }

  // 알림 목록 위젯 수정
  Widget _buildNotificationsList() {
    final filteredNotifications = _filteredNotifications;

    if (filteredNotifications.isEmpty) {
      return _buildEmptyState();
    }

    // 알림 목록에 날짜 구분선 추가
    final itemsWithDateDividers = _getItemsWithDateDividers(
      filteredNotifications,
    );

    // 로딩 더 많은 데이터 로딩 중일 때 마지막 아이템(상단)에 로딩 인디케이터 추가
    if (_isLoadingMore && !_loadFailed) {
      itemsWithDateDividers.add("LOADING_INDICATOR");
    }

    return RefreshIndicator(
      onRefresh: _loadFirstNotifications,
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

                  // 이미 최상단에 있고 로드 가능한 상태인 경우
                  if (!_isLoadingMore && _hasMoreData && !_isOffline) {
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

                  // 로딩 인디케이터 표시
                  if (item == "LOADING_INDICATOR") {
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 16.0),
                      child: Center(
                        child: Column(
                          children: [
                            CircularProgressIndicator(),
                            SizedBox(height: 8),
                            Text(
                              '이전 알림 불러오는 중...',
                              style: TextStyle(
                                color: Colors.grey[600],
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  }

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
    } else if (_searchQuery.isNotEmpty || _selectedFilters.isNotEmpty) {
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
      onRefresh: _loadFirstNotifications,
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
                            _loadFirstNotifications();
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
                        onPressed: _loadFirstNotifications,
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
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      TextButton.icon(
                        onPressed: () {
                          setState(() {
                            _selectedFilters = {
                              NotificationType.youtube,
                              NotificationType.cafe,
                              NotificationType.chzzkVOD,
                              NotificationType.streamStart,
                              NotificationType.streamChange,
                              NotificationType.streamEnd,
                              NotificationType.chat,
                            };
                          });
                          Navigator.pop(context);
                        },
                        icon: Icon(Icons.select_all),
                        label: Text('모두 선택'),
                      ),
                      TextButton.icon(
                        onPressed: () {
                          setState(() {
                            _selectedFilters.clear();
                          });
                          Navigator.pop(context);
                        },
                        icon: Icon(Icons.clear_all),
                        label: Text('모두 해제'),
                      ),
                    ],
                  ),
                  Divider(),
                  // 필터 옵션들
                  _buildFilterOption(NotificationType.youtube, '유튜브 알림'),
                  _buildFilterOption(NotificationType.cafe, '카페 알림'),
                  _buildFilterOption(NotificationType.chzzkVOD, '치지직 VOD 알림'),
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
                child: Text('적용'),
              ),
            ],
          ),
    );
  }

  // 필터 옵션 위젯
  Widget _buildFilterOption(NotificationType type, String label) {
    return CheckboxListTile(
      title: Text(label),
      value: _selectedFilters.contains(type),
      onChanged: (bool? selected) {
        setState(() {
          if (selected == true) {
            _selectedFilters.add(type);
          } else {
            _selectedFilters.remove(type);
          }
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
      case NotificationType.chzzkVOD:
        return '치지직 VOD 알림';
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
          authorIconUrl: notification.authorIconUrl,
          embedData: notification.embedData,
        );

        _notifications[index] = updatedNotification;

        // 로컬에 저장
        PushNotificationService().updateLocalNotifications(_notifications);

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
