// lib/screens/notifications_page.dart
import 'dart:async';
import 'dart:io';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/notification_model.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import '../services/api_service.dart';

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
  bool _isLoadingHistory = false; // 이전 메시지 로드중 플래그
  bool _isRefreshing = false;
  bool _loadFailed = false;
  bool _autoScrollEnabled = false;
  bool _isNearBottom = true;
  int _currentPage = 1;
// 데이터 동시 로드 방지 락
  int _retryCount = 0;
  bool _hasNewMessage = false; // 새 메시지가 도착했는지 여부
  int _newMessageCount = 0; // 새 메시지 개수
  final int _maxRetries = 3;
  final int _pageSize = 100;
  late ScrollController _scrollController;
  StreamSubscription<RemoteMessage>? _messageSubscription;
  Timer? _debounceTimer;
  final List<Timer> _activeTimers = [];

  // 스크롤 관련 변수 추가
// 스크롤 업데이트 간 최소 차이 (픽셀)
// 스크롤 처리 중인지 여부

// 마지막 데이터 로드 시간
// 로드 쿨다운 상태

  // 오프라인 상태 확인을 위한 플래그
  bool _isOffline = false;

  @override
  bool get wantKeepAlive => true; // 페이지 상태 유지

  @override
  void initState() {
    super.initState();
    _scrollController = ScrollController();
    _scrollController.addListener(_scrollListener);

    // 오프라인 상태 확인
    _checkConnectivity().then((_) {
      _loadFirstNotifications();
    });

    _setupMessageListener();

    // 노티피케이션을 받더라도 자동 스크롤 방지 설정
    _autoScrollEnabled = false;

    // 5초마다 중복 제거 실행 (페이지가 활성화된 경우에만)
    Timer.periodic(Duration(seconds: 5), (timer) {
      if (mounted &&
          !_isLoading &&
          !_isLoadingMore &&
          !_isLoadingHistory &&
          !_isRefreshing) {
        _removeDuplicateNotifications();
      }
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

      // 3. 서버에서 최신 데이터 로드 (백그라운드)
      _loadServerNotifications(true);
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

  // 로컬 데이터만 불러오기
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

      // 시간 순으로 정렬
      localNotifications.sort((a, b) => a.timestamp.compareTo(b.timestamp));

      return localNotifications;
    } catch (e) {
      if (kDebugMode) {
        print('로컬 알림 로드 중 오류: $e');
      }
      return [];
    }
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
              // 하단 가까이 있을 때만 자동 스크롤 활성화
              _autoScrollEnabled = _isNearBottom;
            });
          }

          // 무한 스크롤 로직 - 스크롤 위치가 일정 지점을 넘어가면 더 많은 데이터 로드
          if (!_isLoadingMore &&
              !_isLoadingHistory &&
              _hasMoreData &&
              mounted) {
            if (currentScroll >= maxScroll * 0.6) {
              // 60% 지점에서 데이터 로드 시작
              _loadOlderMessages();
            }
          }
        }
      } catch (e) {
        // 스크롤 위치 읽기 오류 처리
        if (kDebugMode) {
          print('스크롤 위치 읽기 오류: $e');
        }

        // 오류 발생 시 스크롤 관련 상태 리셋
        _isLoadingMore = false;
        _isLoadingHistory = false;
      }
    });
    // 생성된 타이머를 목록에 추가
    _activeTimers.add(_debounceTimer!);
  }

  // 주기적 타이머 생성 시에도 목록에 추가

  // 데이터 로드 함수 개선
  Future<void> _loadOlderMessages() async {
    // 이미 로딩 중이거나 오프라인이면 실행하지 않음
    if (_isLoadingMore || _isOffline || _isLoadingHistory) return;

    // 데이터 로드 락 설정 - 동시 로드 방지

    // 로딩 상태 설정 시에도 try-catch 적용
    try {
      setState(() {
        _isLoadingMore = true;
        _loadFailed = false;
      });
    } catch (e) {
      if (kDebugMode) {
        print('로딩 상태 설정 중 오류: $e');
      }
      return; // 위젯이 이미 마운트 해제된 경우 중단
    }

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

        try {
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
              _currentPage++; // 페이지 증가
              _retryCount = 0; // 성공 시 재시도 카운트 초기화
              _isLoadingMore = false;
            });

            // 백그라운드에서 로컬 저장 처리
            _updateLocalNotifications(_notifications);
          }
        } catch (stateError) {
          // setState 호출 중 오류 처리
          if (kDebugMode) {
            print('상태 업데이트 중 오류: $stateError');
          }
        }
      } else {
        // 사용자 정보가 없는 경우
        _safeSetState(() {
          _isLoadingMore = false;
          _loadFailed = true;
        });
      }
    } catch (e) {
      // API 호출 오류 처리
      if (kDebugMode) {
        print('더 많은 알림 로드 중 오류: $e');
      }

      _safeSetState(() {
        _isLoadingMore = false;
        _loadFailed = true;
        _retryCount++;
      });

      // 네트워크 연결 확인
      try {
        await _checkConnectivity();
      } catch (_) {}

      // 재시도 횟수가 최대를 초과하지 않았고 오프라인이 아니면 스낵바 표시
      if (_retryCount < _maxRetries && !_isOffline && mounted) {
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
    } finally {
      // 항상 실행되는 코드
      if (mounted) {
        try {
          setState(() {
            _isLoadingMore = false;
          });
        } catch (e) {
          if (kDebugMode) {
            print('로딩 상태 초기화 중 오류: $e');
          }
        }
      }

      // 데이터 로드 락 해제 (추가 필요)
    }
  }

  // 중복 알림 제거 메서드
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
          ..sort((a, b) => a.timestamp.compareTo(b.timestamp));

    if (_notifications.length != deduplicatedList.length) {
      if (kDebugMode) {
        print('중복 알림 ${_notifications.length - deduplicatedList.length}개 제거됨');
      }

      _safeSetState(() {
        _notifications = deduplicatedList;
      });

      // 로컬에 저장
      _updateLocalNotifications(deduplicatedList);
    }
  }

  // 안전한 setState 호출 헬퍼 메서드
  void _safeSetState(Function() stateUpdate) {
    if (mounted) {
      try {
        setState(stateUpdate);
      } catch (e) {
        if (kDebugMode) {
          print('setState 실행 중 오류: $e');
        }
      }
    }
  }

  // 스크롤 컨트롤러 재설정 메서드

  // 모든 상태 변수 초기화 메서드

  // 오류 발생 후 복구 메서드

  // 최상단에서 당길 때 더 오래된 메시지 로드 (디스코드 스타일)
  Future<void> _loadHistoricalMessages() async {
    // 이미 로딩 중이거나 오프라인이면 실행하지 않음
    if (_isLoadingHistory || _isOffline) return;

    setState(() {
      _isLoadingHistory = true;
    });

    try {
      // 현재 있는 가장 오래된 메시지의 시간 찾기
      DateTime? oldestTimestamp;
      if (_notifications.isNotEmpty) {
        // 정렬된 알림 목록에서 첫 번째(가장 오래된) 메시지의 시간
        oldestTimestamp = _notifications.first.timestamp;

        if (kDebugMode) {
          print('가장 오래된 메시지 시간: $oldestTimestamp');
        }
      }

      // 사용자 정보 가져오기
      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username');
      final discordWebhooksURL = prefs.getString('discordWebhooksURL');

      // 사용자 정보가 없으면 중단
      if (username == null || discordWebhooksURL == null) {
        setState(() {
          _isLoadingHistory = false;
        });
        return;
      }

      // 서버에서 다음 페이지 데이터 로드
      final historicalNotifications = await ApiService.getNotifications(
        username,
        discordWebhooksURL,
        page: _currentPage + 1, // 현재 페이지의 다음 페이지 요청
        limit: _pageSize,
      );

      if (!mounted) return;

      // 더 이상 데이터가 없으면 알림
      if (historicalNotifications.isEmpty) {
        setState(() {
          _hasMoreData = false;
          _isLoadingHistory = false;
        });

        // 데이터가 없으면 사용자에게 알림
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('더 이상 불러올 알림이 없습니다'),
            duration: Duration(seconds: 2),
          ),
        );
        return;
      }

      // 현재 로컬 데이터와 중복 확인
      Set<String> existingIds = _notifications.map((n) => n.id).toSet();
      List<NotificationModel> newItems =
          historicalNotifications
              .where((item) => !existingIds.contains(item.id))
              .toList();

      // 모든 항목이 중복인 경우 다음 페이지 시도
      if (newItems.isEmpty) {
        _currentPage++; // 다음 페이지로 증가
        setState(() {
          _isLoadingHistory = false;
        });

        // 재귀적으로 다시 시도 (다음 페이지)
        _loadHistoricalMessages();
        return;
      }

      // 새 항목 추가
      setState(() {
        // 새 항목을 목록 맨 앞에 추가 (가장 오래된 메시지)
        _notifications.insertAll(0, newItems);
        _currentPage++;
        _isLoadingHistory = false;

        // 로컬에 저장
        _updateLocalNotifications(_notifications);
      });

      // 성공 메시지 표시
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${newItems.length}개의 이전 알림을 불러왔습니다'),
          duration: Duration(seconds: 2),
        ),
      );
    } catch (e) {
      // 오류 처리
      if (kDebugMode) {
        print('이전 알림 로드 중 오류: $e');
      }

      if (mounted) {
        setState(() {
          _isLoadingHistory = false;
        });

        // 오류 메시지 표시
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('이전 알림을 불러오는 중 오류가 발생했습니다'),
            action: SnackBarAction(
              label: '다시 시도',
              onPressed: _loadHistoricalMessages,
            ),
            duration: Duration(seconds: 3),
          ),
        );
      }
    }
  }

  // 새 메시지 알림을 표시하는 코드 수정
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

      if (mounted) {
        setState(() {
          if (existingIndex != -1) {
            // 기존 알림이 있으면 업데이트
            _notifications[existingIndex] = newNotification;
          } else {
            // 새 알림 추가 - 최신 메시지를 목록 끝에 추가
            _notifications.add(newNotification);
            // 정렬
            _notifications.sort((a, b) => a.timestamp.compareTo(b.timestamp));
          }

          // 로컬에도 저장
          _updateLocalNotifications(_notifications);
        });
      }

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
          _hasNewMessage = true; // 새 메시지 플래그 활성화 (추가 필요한 변수)
          _newMessageCount++; // 새 메시지 카운트 증가 (추가 필요한 변수)
        });
      }
    } catch (e) {
      if (kDebugMode) {
        print('새 알림 추가 중 오류: $e');
      }
    }
  }

  @override
  void dispose() {
    // 타이머 정리 추가
    _cleanupTimers();

    // 기존 리소스 정리
    _debounceTimer?.cancel();
    _messageSubscription?.cancel();
    _scrollController.removeListener(_scrollListener);
    _scrollController.dispose();
    super.dispose();
  }

  // 모든 타이머 정리
  void _cleanupTimers() {
    // 디바운스 타이머 정리
    _debounceTimer?.cancel();

    // 활성 타이머 목록에 있는 모든 타이머 취소
    for (final timer in _activeTimers) {
      if (timer.isActive) {
        timer.cancel();
      }
    }

    // 목록 비우기
    _activeTimers.clear();
  }

  void _setupMessageListener() {
    _messageSubscription = FirebaseMessaging.onMessage.listen((
      RemoteMessage message,
    ) {
      // 새 메시지를 알림 목록에 추가
      _addNewNotification(message);
    });
  }

  // 서버에서 데이터를 가져온 후 중복 체크하는 부분 개선
  Future<void> _loadServerNotifications(bool isInitial) async {
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
        _safeSetState(() {
          // 새 알림 추가하고 시간순 정렬
          _notifications.addAll(newNotifications);
          _notifications.sort((a, b) => a.timestamp.compareTo(b.timestamp));
          _currentPage = 1;
          _hasMoreData = true;
          _retryCount = 0;
        });

        // 로컬에 저장
        _updateLocalNotifications(_notifications);
      }
    } catch (e) {
      if (kDebugMode) {
        print('서버 알림 로드 중 오류: $e');
      }
    }
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

  // 앱바 메뉴에서 새로고침 버튼 클릭 시 최신 메시지 로드
  Future<void> _loadNewerMessages() async {
    // 이미 새로고침 중이거나 오프라인이면 실행하지 않음
    if (_isRefreshing || _isOffline) return;

    setState(() {
      _isRefreshing = true;
    });

    try {
      // 사용자 정보 가져오기
      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username');
      final discordWebhooksURL = prefs.getString('discordWebhooksURL');

      // 사용자 정보가 없으면 중단
      if (username == null || discordWebhooksURL == null) {
        setState(() {
          _isRefreshing = false;
        });
        return;
      }

      // 첫 페이지 (최신 메시지) 로드
      final newNotifications = await ApiService.getNotifications(
        username,
        discordWebhooksURL,
        page: 1,
        limit: _pageSize,
      );

      if (!mounted) return;

      // 데이터가 없으면 중단
      if (newNotifications.isEmpty) {
        setState(() {
          _isRefreshing = false;
        });
        return;
      }

      // 현재 로컬 데이터와 중복 확인하고 병합
      Set<String> existingIds = _notifications.map((n) => n.id).toSet();
      List<NotificationModel> newItems =
          newNotifications
              .where((item) => !existingIds.contains(item.id))
              .toList();

      // 새로운 알림이 있는 경우
      if (newItems.isNotEmpty) {
        setState(() {
          // 새 알림을 끝에 추가 (최신 메시지)
          _notifications.addAll(newItems);
          // 시간순 정렬
          _notifications.sort((a, b) => a.timestamp.compareTo(b.timestamp));
          _isRefreshing = false;

          // 로컬에 저장
          _updateLocalNotifications(_notifications);
        });

        // 새 메시지가 있다고 알림
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('${newItems.length}개의 새 알림이 추가되었습니다'),
            duration: Duration(seconds: 2),
            action: SnackBarAction(
              label: '확인',
              onPressed: () {
                // 최하단(최신 메시지)으로 스크롤
                if (_scrollController.hasClients) {
                  _scrollController.animateTo(
                    0,
                    duration: Duration(milliseconds: 300),
                    curve: Curves.easeOut,
                  );
                }
              },
            ),
          ),
        );
      } else {
        // 새 메시지가 없는 경우
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('새로운 알림이 없습니다'),
            duration: Duration(seconds: 2),
          ),
        );

        setState(() {
          _isRefreshing = false;
        });
      }
    } catch (e) {
      // 오류 처리
      if (kDebugMode) {
        print('최신 알림 로드 중 오류: $e');
      }

      if (mounted) {
        setState(() {
          _isRefreshing = false;
        });

        // 오류 메시지 표시
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('최신 알림을 불러오는 중 오류가 발생했습니다'),
            action: SnackBarAction(
              label: '다시 시도',
              onPressed: _loadNewerMessages,
            ),
            duration: Duration(seconds: 3),
          ),
        );
      }
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
    super.build(context); // AutomaticKeepAliveClientMixin 요구사항

    return Scaffold(
      appBar: AppBar(
        title: Text('받은 알림'),
        actions: [
          IconButton(
            icon: Icon(Icons.refresh),
            onPressed:
                (_isRefreshing || _isLoading) ? null : _loadNewerMessages,
            tooltip: '알림 새로고침',
          ),
        ],
      ),
      body: SafeArea(
        child:
            _isLoading
                ? const Center(child: CircularProgressIndicator())
                : Stack(
                  children: [
                    // 오프라인 배너
                    if (_isOffline)
                      Positioned(
                        top: 0,
                        left: 0,
                        right: 0,
                        child: Material(
                          color: Colors.amber[700],
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              vertical: 8,
                              horizontal: 16,
                            ),
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
                                      _loadNewerMessages();
                                    }
                                  },
                                  style: TextButton.styleFrom(
                                    backgroundColor: Colors.amber[900],
                                  ),
                                  child: Text(
                                    '재연결',
                                    style: TextStyle(color: Colors.white),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),

                    // 알림 목록 또는 빈 화면
                    _notifications.isEmpty
                        ? _buildEmptyNotifications()
                        : _buildNotificationsList(),

                    // 로드 실패 시 다시 시도 버튼 (상단에 표시)
                    if (_loadFailed &&
                        _hasMoreData &&
                        !_isLoading &&
                        !_isRefreshing &&
                        !_isOffline &&
                        !_isLoadingHistory)
                      Positioned(
                        top: _isOffline ? 56 : 0, // 오프라인 배너가 있으면 그 아래에 표시
                        left: 0,
                        right: 0,
                        child: Material(
                          color: Colors.red[100],
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              vertical: 8,
                              horizontal: 16,
                            ),
                            child: Row(
                              children: [
                                Icon(Icons.error_outline, color: Colors.red),
                                SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    '알림을 불러오는 중 오류가 발생했습니다',
                                    style: TextStyle(color: Colors.red[900]),
                                  ),
                                ),
                                TextButton(
                                  onPressed: () => _loadOlderMessages(),
                                  style: TextButton.styleFrom(
                                    foregroundColor: Colors.red[900],
                                    backgroundColor: Colors.red[50],
                                  ),
                                  child: Text('다시 시도'),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),

                    // 새 메시지 알림 배너 (상단에 표시)
                    if (_hasNewMessage && !_isNearBottom)
                      Positioned(
                        top:
                            _isOffline
                                ? 56
                                : (_loadFailed
                                    ? 48
                                    : 0), // 오프라인 배너나 에러 배너가 있으면 그 아래에 표시
                        left: 0,
                        right: 0,
                        child: GestureDetector(
                          onTap: () {
                            // 최하단으로 스크롤
                            if (_scrollController.hasClients) {
                              _scrollController.animateTo(
                                0, // 최신 메시지 위치
                                duration: Duration(milliseconds: 300),
                                curve: Curves.easeOut,
                              );
                              // 새 메시지 플래그 초기화
                              setState(() {
                                _hasNewMessage = false;
                                _newMessageCount = 0;
                              });
                            }
                          },
                          child: Container(
                            color: Color(0xFF5865F2), // 디스코드 색상
                            padding: EdgeInsets.symmetric(
                              vertical: 10,
                              horizontal: 16,
                            ),
                            child: Center(
                              child: Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Text(
                                    _newMessageCount > 0
                                        ? '이후로 읽지 않은 메시지가 $_newMessageCount개 있어요'
                                        : '아래로 읽지 않은 메시지가 있어요',
                                    style: TextStyle(
                                      color: Colors.white,
                                      fontWeight: FontWeight.w600,
                                      fontSize: 14,
                                    ),
                                  ),
                                  SizedBox(width: 8),
                                  Container(
                                    padding: EdgeInsets.symmetric(
                                      horizontal: 10,
                                      vertical: 4,
                                    ),
                                    decoration: BoxDecoration(
                                      color: Colors.white,
                                      borderRadius: BorderRadius.circular(16),
                                    ),
                                    child: Text(
                                      '최근으로 이동하기',
                                      style: TextStyle(
                                        color: Color(0xFF5865F2),
                                        fontWeight: FontWeight.bold,
                                        fontSize: 13,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),

                    // 최근으로 이동하기 버튼 (하단에 표시) - 100개 이상 메시지를 지나쳤을 때
                    if (!_isNearBottom &&
                        _scrollController.hasClients &&
                        _scrollController.position.pixels >
                            500) // 500은 대략적인 값으로, 실제 100개 메시지에 맞게 조정 필요
                      Positioned(
                        left: 0,
                        right: 0,
                        bottom: 16,
                        child: Center(
                          child: Material(
                            elevation: 4,
                            shadowColor: Colors.black26,
                            color: Colors.transparent,
                            borderRadius: BorderRadius.circular(24),
                            child: InkWell(
                              onTap: () {
                                if (_scrollController.hasClients) {
                                  // 역방향 리스트뷰에서는 최하단(최신 메시지)이 scrollExtent가 0에 가깝습니다
                                  _scrollController.animateTo(
                                    0, // 최신 메시지(하단)으로 이동
                                    duration: Duration(milliseconds: 300),
                                    curve: Curves.easeOut,
                                  );
                                  // 최하단으로 이동했으므로 버튼 숨기기
                                  setState(() {
                                    _isNearBottom = true;
                                    _hasNewMessage = false;
                                    _newMessageCount = 0;
                                  });
                                }
                              },
                              borderRadius: BorderRadius.circular(24),
                              child: Container(
                                padding: EdgeInsets.symmetric(
                                  horizontal: 20,
                                  vertical: 8,
                                ),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF5865F2), // 디스코드 색상
                                  borderRadius: BorderRadius.circular(24),
                                  boxShadow: [
                                    BoxShadow(
                                      color: Color.fromARGB(
                                        (0.2 * 255).round(),
                                        0,
                                        0,
                                        0,
                                      ),
                                      blurRadius: 4,
                                      offset: Offset(0, 2),
                                    ),
                                  ],
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Text(
                                      '오래된 메시지를 보고 있어요',
                                      style: TextStyle(
                                        color: Colors.white,
                                        fontWeight: FontWeight.w500,
                                        fontSize: 14,
                                      ),
                                    ),
                                    SizedBox(width: 8),
                                    Container(
                                      padding: EdgeInsets.symmetric(
                                        horizontal: 10,
                                        vertical: 4,
                                      ),
                                      decoration: BoxDecoration(
                                        color: Colors.white,
                                        borderRadius: BorderRadius.circular(16),
                                      ),
                                      child: Text(
                                        '최근으로 이동하기',
                                        style: TextStyle(
                                          color: const Color(0xFF5865F2),
                                          fontWeight: FontWeight.bold,
                                          fontSize: 13,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),

                    // 상단 로딩 인디케이터 (이전 메시지 로드)
                    if (_isLoadingMore)
                      Positioned(
                        top: _isOffline ? 56 : 0, // 오프라인 배너가 있으면 그 아래에 표시
                        left: 0,
                        right: 0,
                        child: LinearProgressIndicator(),
                      ),

                    // 하단 로딩 인디케이터 (새 메시지 로드)
                    if (_isLoadingHistory)
                      Positioned(
                        bottom: 0,
                        left: 0,
                        right: 0,
                        child: LinearProgressIndicator(),
                      ),
                  ],
                ),
      ),
    );
  }

  Widget _buildEmptyNotifications() {
    final theme = Theme.of(context);
    final isDarkMode = theme.brightness == Brightness.dark;

    // 오프라인 상태와 데이터 로드 실패 상태 모두에 대응
    final Widget content =
        _loadFailed
            ? ListView(
              physics: const AlwaysScrollableScrollPhysics(), // 당겨서 새로고침 가능하게
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
                            color:
                                _isOffline
                                    ? (isDarkMode
                                        ? Colors.amber[900]
                                        : Colors.amber[100])
                                    : (isDarkMode
                                        ? Colors.red[900]
                                        : Colors.red[100]),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            _isOffline ? Icons.wifi_off : Icons.error_outline,
                            size: 40,
                            color:
                                _isOffline
                                    ? (isDarkMode
                                        ? Colors.amber[300]
                                        : Colors.amber[900])
                                    : (isDarkMode
                                        ? Colors.red[300]
                                        : Colors.red[900]),
                          ),
                        ),
                        SizedBox(height: 24),
                        Text(
                          _isOffline ? '오프라인 상태입니다' : '알림을 불러오는 중 오류가 발생했습니다',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w500,
                            color:
                                _isOffline
                                    ? (isDarkMode
                                        ? Colors.amber[300]
                                        : Colors.amber[900])
                                    : (isDarkMode
                                        ? Colors.red[300]
                                        : Colors.red[900]),
                          ),
                        ),
                        SizedBox(height: 8),
                        Text(
                          _isOffline
                              ? '인터넷 연결이 없습니다. 연결 상태를 확인해주세요.'
                              : '네트워크 연결을 확인하고 다시 시도해보세요',
                          style: TextStyle(
                            fontSize: 14,
                            color:
                                isDarkMode
                                    ? Colors.grey[400]
                                    : Colors.grey[600],
                          ),
                          textAlign: TextAlign.center,
                        ),
                        SizedBox(height: 24),
                        ElevatedButton.icon(
                          onPressed:
                              _isOffline
                                  ? () async {
                                    await _checkConnectivity();
                                    if (!_isOffline) {
                                      _loadNewerMessages();
                                    }
                                  }
                                  : _loadNewerMessages,
                          icon: Icon(
                            _isOffline ? Icons.wifi_find : Icons.refresh,
                          ),
                          label: Text(_isOffline ? '연결 확인' : '새로고침'),
                          style: ElevatedButton.styleFrom(
                            padding: EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 8,
                            ),
                            backgroundColor:
                                _isOffline
                                    ? (isDarkMode
                                        ? Colors.amber[800]
                                        : Colors.amber[600])
                                    : (isDarkMode
                                        ? Colors.red[800]
                                        : Colors.red[600]),
                            foregroundColor: Colors.white,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            )
            : RefreshIndicator(
              onRefresh:
                  _loadHistoricalMessages, // 위로 당겨서 오래된 메시지 로드 (디스코드 스타일)
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
                              color:
                                  isDarkMode
                                      ? Colors.grey[800]
                                      : Colors.grey[200],
                              shape: BoxShape.circle,
                            ),
                            child: Icon(
                              Icons.notifications_off_outlined,
                              size: 40,
                              color:
                                  isDarkMode
                                      ? Colors.grey[500]
                                      : Colors.grey[400],
                            ),
                          ),
                          SizedBox(height: 24),
                          Text(
                            '받은 알림이 없습니다',
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w500,
                              color:
                                  isDarkMode
                                      ? Colors.grey[300]
                                      : Colors.grey[700],
                            ),
                          ),
                          SizedBox(height: 8),
                          Text(
                            '스트리머 알림 설정을 확인해보세요',
                            style: TextStyle(
                              fontSize: 14,
                              color:
                                  isDarkMode
                                      ? Colors.grey[500]
                                      : Colors.grey[600],
                            ),
                          ),
                          SizedBox(height: 24),
                          ElevatedButton.icon(
                            onPressed: _loadNewerMessages,
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

    return content;
  }

  // 스크롤 알림 처리
  bool _handleScrollNotification(ScrollNotification notification) {
    // 스크롤이 최상단에 도달하고 더 위로 당길 때 이전 데이터 로드
    if (notification is OverscrollNotification &&
        notification.overscroll < 0 && // 음수는 위로 당기는 것
        _scrollController.position.pixels >=
            _scrollController.position.maxScrollExtent - 20) {
      // 더 오래된 메시지 로드 - 중복 호출 방지
      if (!_isLoadingMore &&
          !_isLoadingHistory &&
          _hasMoreData &&
          !_loadFailed &&
          !_isOffline) {
        _loadOlderMessages();
      } else if (_loadFailed &&
          !_isLoadingMore &&
          !_isOffline &&
          !_isLoadingHistory) {
        // 실패한 경우에도 다시 시도 가능 (오프라인이 아닐 때)
        _loadOlderMessages();
      }
      return true; // 이벤트 소비
    }
    return false; // 다른 알림은 계속 처리
  }

  Widget _buildNotificationsList() {
    return NotificationListener<ScrollNotification>(
      onNotification: _handleScrollNotification,
      child: RefreshIndicator(
        onRefresh: _loadHistoricalMessages, // 수정: 위로 당기면 오래된 메시지 로드 (디스코드 스타일)
        color: Theme.of(context).primaryColor,
        child: _buildNotificationsListContent(),
      ),
    );
  }

  Widget _buildNotificationsListContent() {
    // 메모리 최적화를 위해 ListView.builder 대신 날짜별 그룹화 리스트 사용
    try {
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

        // 해당 날짜의 알림 추가 (해당 날짜 내에서는 시간 순으로 정렬)
        List<NotificationModel> dayNotifications = groupedNotifications[date]!;
        dayNotifications.sort((a, b) => a.timestamp.compareTo(b.timestamp));

        // 알림 메시지 추가 (메모리 효율성을 위해 최대 항목 수 제한)
        for (var notification in dayNotifications) {
          allWidgets.add(_buildNotificationItem(notification));
        }
      }

      return ListView(
        controller: _scrollController,
        physics: const AlwaysScrollableScrollPhysics(), // 스크롤 물리 활성화
        reverse: true, // 리스트를 뒤집어 최신 메시지가 하단에 오도록 함
        children: allWidgets.reversed.toList(), // 위젯 목록도 뒤집어 순서 유지
      );
    } catch (e) {
      // 렌더링 중 오류 처리
      if (kDebugMode) {
        print('알림 목록 렌더링 중 오류: $e');
      }

      // 기본 오류 표시
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, size: 48, color: Colors.red),
            SizedBox(height: 16),
            Text('알림을 표시하는 중 오류가 발생했습니다'),
            SizedBox(height: 8),
            ElevatedButton(onPressed: _loadNewerMessages, child: Text('새로고침')),
          ],
        ),
      );
    }
  }

  // 날짜 구분선 위젯
  Widget _buildDateDivider(String dateStr) {
    final theme = Theme.of(context);
    final isDarkMode = theme.brightness == Brightness.dark;

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
      padding: EdgeInsets.symmetric(vertical: 12),
      margin: EdgeInsets.symmetric(horizontal: 12),
      child: Row(
        children: [
          Expanded(
            child: Divider(
              color: isDarkMode ? Colors.grey[700] : Colors.grey[300],
              thickness: 0.5,
            ),
          ),
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 16),
            padding: EdgeInsets.symmetric(horizontal: 10, vertical: 3),
            decoration: BoxDecoration(
              color: isDarkMode ? Color(0xFF353535) : Colors.grey[200],
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              displayText,
              style: TextStyle(
                color: isDarkMode ? Colors.grey[400] : Colors.grey[600],
                fontSize: 12,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          Expanded(
            child: Divider(
              color: isDarkMode ? Colors.grey[700] : Colors.grey[300],
              thickness: 0.5,
            ),
          ),
        ],
      ),
    );
  }

  // 알림 항목 위젯
  Widget _buildNotificationItem(NotificationModel notification) {
    final theme = Theme.of(context);
    final isDarkMode = theme.brightness == Brightness.dark;

    // 카드 배경색 및 테두리 설정
    final cardBgColor = isDarkMode ? Color(0xFF2D2D2D) : Colors.white;
    final borderColor =
        notification.color != 0
            ? Color(notification.color)
            : isDarkMode
            ? Colors.grey[800]!
            : Colors.grey[300]!;

    // 리치 알림(embeds가 있는 경우)
    if (notification.isRichNotification) {
      return Container(
        margin: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: cardBgColor,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: borderColor,
            width: notification.color != 0 ? 2 : 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withAlpha(13), // 0.05 × 255 = 약 13
              blurRadius: 3,
              offset: Offset(0, 1),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 상단바 (사용자명과 아바타)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
              child: Row(
                children: [
                  // 아바타
                  CircleAvatar(
                    backgroundImage:
                        notification.avatarUrl.isNotEmpty
                            ? NetworkImage(notification.avatarUrl)
                            : null,
                    radius: 14,
                    backgroundColor:
                        isDarkMode ? Colors.grey[800] : Colors.grey[200],
                    child:
                        notification.avatarUrl.isEmpty
                            ? Icon(
                              Icons.person,
                              size: 16,
                              color:
                                  isDarkMode
                                      ? Colors.white70
                                      : Colors.grey[700],
                            )
                            : null,
                  ),
                  SizedBox(width: 8),

                  // 사용자명
                  Expanded(
                    child: Text(
                      notification.username,
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 14,
                        color: isDarkMode ? Colors.white : Colors.black87,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),

                  // 타임스탬프
                  Text(
                    _formatTimestamp(notification.timestamp),
                    style: TextStyle(
                      color: isDarkMode ? Colors.grey[400] : Colors.grey[600],
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),

            // 내용이 있는 경우
            if (notification.content.isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 6, 12, 6),
                child: Text(
                  notification.content,
                  style: TextStyle(
                    fontSize: 14,
                    color: isDarkMode ? Colors.white70 : Colors.black87,
                  ),
                ),
              ),

            // 제목이 있는 경우
            if (notification.title.isNotEmpty)
              Container(
                padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                decoration: BoxDecoration(
                  border: Border(
                    left: BorderSide(
                      color:
                          notification.color != 0
                              ? Color(notification.color)
                              : theme.primaryColor,
                      width: 3,
                    ),
                  ),
                ),
                child: Text(
                  notification.title,
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                    color: isDarkMode ? Colors.white : Colors.black87,
                  ),
                ),
              ),

            // 필드가 있는 경우 (Discord의 필드처럼 표시)
            if (notification.fields != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 6, 12, 6),
                child: _buildFields(notification.fields!),
              ),

            // 이미지가 있는 경우
            if (notification.imageUrl.isNotEmpty)
              Container(
                constraints: BoxConstraints(maxHeight: 200),
                width: double.infinity,
                child: ClipRRect(
                  borderRadius: BorderRadius.only(
                    bottomLeft: Radius.circular(8),
                    bottomRight: Radius.circular(8),
                  ),
                  child: Image.network(
                    notification.imageUrl,
                    fit: BoxFit.cover,
                    errorBuilder:
                        (context, error, stackTrace) => Container(
                          height: 100,
                          color:
                              isDarkMode ? Colors.grey[800] : Colors.grey[200],
                          child: Center(
                            child: Icon(
                              Icons.broken_image,
                              color:
                                  isDarkMode
                                      ? Colors.white30
                                      : Colors.grey[400],
                            ),
                          ),
                        ),
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
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(10),
                          child: Image.network(
                            notification.footerIconUrl,
                            width: 16,
                            height: 16,
                            errorBuilder:
                                (context, error, stackTrace) =>
                                    SizedBox(width: 16, height: 16),
                          ),
                        ),
                      ),
                    Text(
                      notification.footerText,
                      style: TextStyle(
                        color: isDarkMode ? Colors.grey[400] : Colors.grey[600],
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),

            // 바닥 패딩
            SizedBox(height: 4),
          ],
        ),
      );
    } else {
      // 기본 알림 표시 방식
      return Container(
        margin: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: cardBgColor,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: isDarkMode ? Colors.grey[800]! : Colors.grey[300]!,
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withAlpha(13),
              blurRadius: 3,
              offset: Offset(0, 1),
            ),
          ],
        ),
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
                backgroundColor:
                    isDarkMode ? Colors.grey[800] : Colors.grey[200],
                child:
                    notification.avatarUrl.isEmpty
                        ? Icon(
                          Icons.person,
                          color: isDarkMode ? Colors.white70 : Colors.grey[700],
                        )
                        : null,
              ),
              SizedBox(width: 12),
              // 알림 내용 - Expanded 위젯으로 감싸 넘침 방지
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // 사용자 이름을 Flexible로 감싸 공간을 효율적으로 사용
                        Expanded(
                          child: Text(
                            notification.username,
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 15,
                              color: isDarkMode ? Colors.white : Colors.black87,
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
                            color:
                                isDarkMode
                                    ? Colors.grey[400]
                                    : Colors.grey[600],
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                    SizedBox(height: 4),
                    // 메시지 내용도 넘침 방지
                    Text(
                      notification.content,
                      style: TextStyle(
                        fontSize: 14,
                        color: isDarkMode ? Colors.white70 : Colors.black87,
                      ),
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

  // 필드 처리를 위한 메서드
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
