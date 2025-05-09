import 'dart:convert';
import 'dart:io';
import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:device_info_plus/device_info_plus.dart'; //디바이스 id 생성용
import 'package:uuid/uuid.dart'; // 고유 ID 생성용 패키지
import '../services/api_service.dart';
import '../models/notification_model.dart';
import '../utils/navigation_helper.dart';

enum LoadDirection {
  newer, // 최신 알림 로드 (첫 페이지)
  older, // 과거 알림 로드 (다음 페이지)
}

// 백그라운드 메시지 핸들러
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();

  // 알림 데이터를 SharedPreferences에 임시 저장
  await _saveNotification(message);

  debugPrint("백그라운드 메시지 수신: ${message.messageId}");
  debugPrint("데이터: ${message.data}");
}

// 알림 임시 저장 함수 (백그라운드에서도 동작)
Future<void> _saveNotification(RemoteMessage message) async {
  try {
    // 중요 필드가 비어있으면 저장하지 않음
    if (message.data['id'] == null ||
        (message.notification?.title == null &&
            message.data['username'] == null)) {
      debugPrint('알림 데이터 부족: ${message.data}');
      return;
    }

    final prefs = await SharedPreferences.getInstance();
    final notifications = prefs.getStringList('notifications') ?? [];

    // 메시지에서 NotificationModel 생성
    final notificationData = {
      'id': message.data['id'],
      'username':
          message.notification?.title ?? message.data['username'] ?? '알림',
      'content': message.notification?.body ?? message.data['content'] ?? '',
      'avatar_url': message.data['avatar_url'] ?? '',
      'timestamp': DateTime.now().toIso8601String(),
      'read': false,
    };

    // embeds 데이터가 있으면 추가
    if (message.data.containsKey('embeds')) {
      try {
        notificationData['embeds'] = json.decode(message.data['embeds']);
      } catch (e) {
        notificationData['embeds'] = message.data['embeds'];
      }
    }

    message.data.forEach((key, value) {
      if (!notificationData.containsKey(key)) {
        notificationData[key] = value;
      }
    });

    // 알림 모델 생성
    final newNotification = NotificationModel.fromJson(notificationData);

    // PushNotificationService 인스턴스 저장 (백그라운드에서도 동작하도록)
    await PushNotificationService()._processAndSaveNotifications(
      notifications,
      newNotification: newNotification,
    );

    // 알림이 백그라운드에서 왔는지 표시하는 플래그 저장
    await prefs.setBool('notification_clicked', true);

    debugPrint('새 알림 저장: ${message.data['id']}');
  } catch (e) {
    debugPrint('알림 저장 중 오류: $e');
  }
}

class PushNotificationService {
  final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();

  final DeviceInfoPlugin _deviceInfo = DeviceInfoPlugin();
  String? _deviceId;

  // 싱글톤 패턴
  static final PushNotificationService _instance =
      PushNotificationService._internal();

  // 상태 관리를 위한 StreamController 확장
  final StreamController<String> _appStateStreamController =
      StreamController<String>.broadcast();
  Stream<String> get appStateStream => _appStateStreamController.stream;

  factory PushNotificationService() {
    return _instance;
  }

  PushNotificationService._internal();

  Future<String> getDeviceId() async {
    if (_deviceId != null) {
      return _deviceId!;
    }

    final prefs = await SharedPreferences.getInstance();

    // 저장된 기기 ID가 있는지 확인
    _deviceId = prefs.getString('device_id');

    // 없으면 새로 생성
    if (_deviceId == null) {
      _deviceId = await _generateDeviceId();
      // 생성한 ID를 저장
      await prefs.setString('device_id', _deviceId!);
    }

    return _deviceId!;
  }

  // 기기 고유 ID 생성 함수
  Future<String> _generateDeviceId() async {
    String deviceId = '';

    try {
      // 플랫폼별 기기 정보 수집
      if (Platform.isAndroid) {
        final androidInfo = await _deviceInfo.androidInfo;
        // 안드로이드는 ANDROID_ID를 기반으로 고유 ID 생성
        deviceId = androidInfo.id;
      } else if (Platform.isIOS) {
        final iosInfo = await _deviceInfo.iosInfo;
        // iOS는 identifierForVendor를 기반으로 고유 ID 생성
        deviceId = iosInfo.identifierForVendor ?? '';
      }

      // 기기 정보가 없거나 비어있으면 UUID 생성
      if (deviceId.isEmpty) {
        deviceId = const Uuid().v4();
      }

      // 해시처리나 접두사 추가
      return 'device_${deviceId.hashCode.abs()}';
    } catch (e) {
      debugPrint('기기 ID 생성 중 오류: $e');

      // 오류 발생 시 랜덤 UUID 반환
      return 'fallback_${const Uuid().v4()}';
    }
  }

  // 알림 초기화
  Future<void> initialize() async {
    try {
      // Firebase 초기화는 main.dart에서 이미 했지만 혹시 모르니 추가
      try {
        await Firebase.initializeApp();
      } catch (e) {
        debugPrint('Firebase 이미 초기화됨: $e');
      }

      // iOS 알림 권한 요청
      if (Platform.isIOS) {
        await _messaging.requestPermission(
          alert: true,
          badge: true,
          sound: true,
        );
      }

      if (Platform.isAndroid) {
        final authStatus = await _messaging.requestPermission(
          alert: true,
          badge: true,
          sound: true,
          provisional: false,
        );

        debugPrint('알림 권한 상태: ${authStatus.authorizationStatus}');
      }

      // 백그라운드 핸들러 설정
      FirebaseMessaging.onBackgroundMessage(
        _firebaseMessagingBackgroundHandler,
      );

      // 안드로이드용 로컬 알림 설정
      const AndroidInitializationSettings androidSettings =
          AndroidInitializationSettings('@mipmap/launcher_icon');
      const DarwinInitializationSettings iosSettings =
          DarwinInitializationSettings();
      const InitializationSettings initSettings = InitializationSettings(
        android: androidSettings,
        iOS: iosSettings,
      );

      await _localNotifications.initialize(
        initSettings,
        onDidReceiveNotificationResponse: (NotificationResponse response) {
          // 알림 클릭 시 처리

          debugPrint('알림 클릭됨: ${response.payload}');

          //받은 알림 창으로 이동
          NavigationHelper().navigateToNotificationsPage();
        },
      );

      // Android 알림 채널 설정
      const AndroidNotificationChannel channel = AndroidNotificationChannel(
        'high_importance_channel',
        '스트리머 알림',
        description: '스트리머 관련 알림을 받습니다.',
        importance: Importance.high,
      );

      await _localNotifications
          .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin
          >()
          ?.createNotificationChannel(channel);

      // 포그라운드 메시지 처리
      FirebaseMessaging.onMessage.listen(_handleForegroundMessage);

      // 앱이 종료된 상태에서 알림 클릭으로 열린 경우 처리
      FirebaseMessaging.instance.getInitialMessage().then((message) {
        if (message != null) {
          debugPrint('앱이 종료된 상태에서 알림 클릭: ${message.data}');

          _appStateStreamController.add('app_opened_from_terminated');

          //앱이 충분히 초기화된 후 내비게이션 수행
          Future.delayed(Duration(milliseconds: 500), () {
            NavigationHelper().navigateToNotificationsPage();
          });
        }
      });

      // 앱이 백그라운드 상태에서 알림 클릭으로 열린 경우 처리
      FirebaseMessaging.onMessageOpenedApp.listen((message) {
        debugPrint('백그라운드 상태에서 알림 클릭: ${message.data}');

        _appStateStreamController.add('app_opened_from_background');

        //받은 알림 창으로 이동
        NavigationHelper().navigateToNotificationsPage();
      });

      // 토큰 갱신 리스너
      _messaging.onTokenRefresh.listen(_updateTokenToServer);

      // 토큰 가져오기
      final fcmToken = await _messaging.getToken();
      if (fcmToken != null) {
        debugPrint('FCM 토큰: $fcmToken');

        await _updateTokenToServer(fcmToken);
      }
    } catch (e) {
      debugPrint('알림 서비스 초기화 중 오류: $e');
    }
  }

  Future<List> _processAndSaveNotifications(
    List<dynamic> notifications, {
    NotificationModel? newNotification,
  }) async {
    try {
      List<NotificationModel> notificationModels = [];

      for (var notification in notifications) {
        if (notification is String) {
          try {
            notificationModels.add(
              NotificationModel.fromJson(jsonDecode(notification)),
            );
          } catch (e) {
            debugPrint('알림 변환 중 오류: $e');
          }
        } else if (notification is NotificationModel) {
          notificationModels.add(notification);
        }
      }

      if (newNotification != null) {
        notificationModels.add(newNotification);
      }

      final Map<String, NotificationModel> uniqueNotifications = {};
      for (var notification in notificationModels) {
        if (!uniqueNotifications.containsKey(notification.id) ||
            notification.timestamp.isAfter(
              uniqueNotifications[notification.id]!.timestamp,
            )) {
          uniqueNotifications[notification.id] = notification;
        }
      }

      final List<NotificationModel> sortedList =
          uniqueNotifications.values.toList()
            ..sort((a, b) => b.timestamp.compareTo(a.timestamp));

      final List<NotificationModel> limitedList =
          sortedList.length > 100 ? sortedList.sublist(0, 100) : sortedList;

      final prefs = await SharedPreferences.getInstance();
      final notificationsJson =
          limitedList
              .map((notification) => jsonEncode(notification.toJson()))
              .toList();

      await prefs.setStringList('notifications', notificationsJson);

      debugPrint('알림 저장 완료: 총 ${limitedList.length}개');
      return limitedList;
    } catch (e) {
      debugPrint('알림 처리 및 저장 중 오류: $e');
      return [];
    }
  }

  // 서버에서 알림 로드
  Future<Map<String, dynamic>> loadNotifications({
    required LoadDirection direction,
    int? pageSize,
    int? currentPage,
  }) async {
    // 결과 맵 초기화
    Map<String, dynamic> result = {
      'success': false,
      'notifications': <NotificationModel>[],
      'hasMore': false,
      'errorType': '',
      'error': '',
      'currentPage': currentPage ?? 1,
    };

    try {
      // 오프라인 상태 확인
      try {
        final connectivityResult = await InternetAddress.lookup('google.com');
        if (connectivityResult.isEmpty ||
            connectivityResult[0].rawAddress.isEmpty) {
          result['errorType'] = 'network';
          result['error'] = '인터넷 연결이 없습니다';
          return result;
        }
      } on SocketException catch (_) {
        result['errorType'] = 'network';
        result['error'] = '인터넷 연결이 없습니다';
        return result;
      }

      // 요청할 페이지 번호 결정
      int pageToLoad =
          direction == LoadDirection.newer ? 1 : (currentPage ?? 1) + 1;
      int limit = pageSize ?? 50;

      // 사용자 정보 가져오기
      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username');
      final discordWebhooksURL = prefs.getString('discordWebhooksURL');

      if (username == null || discordWebhooksURL == null) {
        result['errorType'] = 'auth';
        result['error'] = '사용자 정보가 없습니다';
        return result;
      }

      // 서버 API 호출
      final apiResult = await ApiService.getNotifications(
        username,
        discordWebhooksURL,
        page: pageToLoad,
        limit: limit,
      );

      // 결과 처리
      if (apiResult['success']) {
        final List<NotificationModel> newNotifications =
            apiResult['notifications'];
        final bool hasMore = apiResult['hasMore'];

        result['success'] = true;
        result['notifications'] = newNotifications;
        result['hasMore'] = hasMore;

        // 페이지 번호 업데이트
        if (direction == LoadDirection.newer) {
          result['currentPage'] = 1;
        } else {
          result['currentPage'] = pageToLoad;
        }

        // 가져온 알림이 있다면 로컬에 저장 (최신 데이터 로드 시에만)
        if (newNotifications.isNotEmpty && direction == LoadDirection.newer) {
          await updateLocalNotifications(newNotifications);

          // 읽지 않은 알림 개수 확인
          final unreadCount =
              newNotifications.where((n) => n.read == false).length;
          if (unreadCount > 0) {
            debugPrint('읽지 않은 알림이 $unreadCount개 있습니다');
          }
        }

        debugPrint('서버에서 ${newNotifications.length}개의 알림을 로드했습니다.');
      } else {
        // 오류가 발생한 경우
        final String errorType = apiResult['errorType'] ?? 'unknown';
        final String serverError =
            apiResult['error'] ?? '알림을 불러오는 중 오류가 발생했습니다';

        result['errorType'] = errorType;
        result['error'] = serverError;

        // 네트워크 오류가 아니고 과거 알림 로드인 경우에만 더 이상 데이터가 없음으로 취급
        if (errorType != 'network' && direction == LoadDirection.older) {
          result['hasMore'] = false;
        }

        debugPrint('알림 로드 오류: type=$errorType, message=$serverError');

        // 네트워크 오류가 아닌 경우, 로컬 데이터 반환
        if (errorType != 'network' && direction == LoadDirection.newer) {
          final localNotifications = await getLocalNotifications();
          result['notifications'] = localNotifications;
          result['success'] =
              localNotifications.isNotEmpty; // 로컬 데이터가 있으면 성공으로 간주
        }
      }
    } catch (e) {
      debugPrint('알림 로드 중 예상치 못한 오류: $e');
      result['errorType'] = 'unknown';
      result['error'] = '예상치 못한 오류가 발생했습니다: $e';

      // 오류 발생 시 로컬 데이터 반환 (최신 데이터 로드 시에만)
      if (direction == LoadDirection.newer) {
        final localNotifications = await getLocalNotifications();
        result['notifications'] = localNotifications;
        result['success'] =
            localNotifications.isNotEmpty; // 로컬 데이터가 있으면 성공으로 간주
      }
    }

    return result;
  }

  // 로컬에 알림 저장 및 업데이트
  Future<void> updateLocalNotifications(
    List<NotificationModel> notifications,
  ) async {
    try {
      if (notifications.isEmpty) return;

      final prefs = await SharedPreferences.getInstance();
      final localNotificationsJson = prefs.getStringList('notifications') ?? [];

      //저장
      await _processAndSaveNotifications([
        ...localNotificationsJson,
        ...notifications,
      ]);

      debugPrint('로컬 알림 업데이트 완료');
    } catch (e) {
      debugPrint('알림 로컬 저장 중 오류: $e');
    }
  }

  // 로컬 데이터 로드
  Future<List<NotificationModel>> getLocalNotifications() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.reload();
      final localNotificationsJson = prefs.getStringList('notifications') ?? [];

      if (localNotificationsJson.isEmpty) {
        return [];
      }

      List<NotificationModel> localNotifications =
          localNotificationsJson
              .map((json) => NotificationModel.fromJson(jsonDecode(json)))
              .toList();

      localNotifications.sort((a, b) => b.timestamp.compareTo(a.timestamp));

      return localNotifications;
    } catch (e) {
      debugPrint('로컬 알림 로드 중 오류: $e');

      return [];
    }
  }

  // 토큰 서버에 등록
  Future<void> _updateTokenToServer(String token) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username');
      final discordWebhooksURL = prefs.getString('discordWebhooksURL');

      if (username != null && discordWebhooksURL != null) {
        // 기기 ID 가져오기
        final deviceId = await getDeviceId();

        // 서버에 토큰 등록 (기기 ID 포함)
        await ApiService.registerFcmToken(
          username,
          discordWebhooksURL,
          token,
          deviceId,
        );
      } else {
        debugPrint('토큰 등록을 위한 사용자 정보가 없습니다.');
      }
    } catch (e) {
      debugPrint('토큰 업데이트 오류: $e');
    }
  }

  // FCM 토큰 등록
  Future<void> registerToken() async {
    try {
      // 먼저 토큰 가져오기
      final fcmToken = await _messaging.getToken();
      if (fcmToken != null) {
        debugPrint('FCM 토큰: $fcmToken');

        await _updateTokenToServer(fcmToken);

        // 로컬에 현재 토큰 저장
        await _saveCurrentToken(fcmToken);
      }

      // 토큰 갱신 시 핸들러 등록
      _messaging.onTokenRefresh.listen(_handleTokenRefresh);
    } catch (e) {
      debugPrint('FCM 토큰 등록 중 오류: $e');
    }
  }

  // 토큰 갱신 처리
  Future<void> _handleTokenRefresh(String newToken) async {
    try {
      debugPrint('FCM 토큰 갱신됨: $newToken');

      // 이전 토큰과 새 토큰이 다른지 확인
      final oldToken = await _getCurrentToken();
      if (oldToken != null && oldToken != newToken) {
        // 이전 토큰 제거
        await removeToken();
      }

      // 새 토큰 등록
      await _updateTokenToServer(newToken);
      await _saveCurrentToken(newToken);
    } catch (e) {
      debugPrint('토큰 갱신 처리 중 오류: $e');
    }
  }

  // 현재 토큰 로컬 저장소에 저장
  Future<void> _saveCurrentToken(String token) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('fcm_token', token);
    } catch (e) {
      debugPrint('토큰 저장 중 오류: $e');
    }
  }

  // 현재 토큰 로컬 저장소에서 가져오기
  Future<String?> _getCurrentToken() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString('fcm_token');
    } catch (e) {
      debugPrint('토큰 가져오기 중 오류: $e');

      return null;
    }
  }

  // 토큰 제거
  Future<void> removeToken() async {
    try {
      // 현재 기기의 토큰 가져오기
      final fcmToken = await _getCurrentToken();

      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username');
      final discordWebhooksURL = prefs.getString('discordWebhooksURL');

      // 기기 ID 가져오기
      final deviceId = await getDeviceId();

      // 서버에 토큰 제거 요청
      if (username != null && discordWebhooksURL != null && fcmToken != null) {
        // 특정 토큰과 기기 ID로 제거하는 API 호출
        await ApiService.removeToken(
          username,
          discordWebhooksURL,
          fcmToken,
          deviceId,
        );
      }

      // 로컬 알림 목록 삭제
      await prefs.remove('notifications');
      await prefs.remove('fcm_token');

      debugPrint('FCM 토큰 및 알림 데이터 제거 완료');
    } catch (e) {
      debugPrint('토큰 제거 중 오류: $e');
    }
  }

  final StreamController<NotificationModel> _notificationStreamController =
      StreamController<NotificationModel>.broadcast();
  Stream<NotificationModel> get notificationStream =>
      _notificationStreamController.stream;

  // 포그라운드 메시지 처리
  void _handleForegroundMessage(RemoteMessage message) async {
    debugPrint('데이터: ${message.data}');

    // 알림 저장
    await _saveNotification(message);

    // NotificationModel로 변환
    final notification = _convertMessageToNotification(message);

    // 스트림에 알림 추가
    _notificationStreamController.add(notification);

    // 알림 데이터에서 정보 추출
    // final title = message.notification?.title ?? '(알 수 없음)';
    // var body = message.notification?.body ?? '';

    // 로컬 알림으로 표시
    // _showLocalNotification(title, body, message.data);
  }

  // RemoteMessage를 NotificationModel로 변환하는 메서드
  NotificationModel _convertMessageToNotification(RemoteMessage message) {
    // 기본 데이터 생성
    Map<String, dynamic> notificationData = {
      'id': message.data['id'],
      'username':
          message.notification?.title ?? message.data['username'] ?? '알림',
      'content': message.notification?.body ?? message.data['content'] ?? '',
      'avatar_url': message.data['avatar_url'] ?? '',
      'timestamp': DateTime.now().toIso8601String(),
      'read': false,
    };

    // embeds 데이터가 있으면 추가
    if (message.data.containsKey('embeds')) {
      try {
        if (message.data['embeds'] is String) {
          notificationData['embeds'] = jsonDecode(message.data['embeds']);
        } else {
          notificationData['embeds'] = message.data['embeds'];
        }
      } catch (e) {
        debugPrint('embeds 데이터 파싱 오류: $e');
      }
    }

    // 추가 데이터 병합
    message.data.forEach((key, value) {
      if (!notificationData.containsKey(key)) {
        notificationData[key] = value;
      }
    });

    // NotificationModel로 변환하여 반환
    return NotificationModel.fromJson(notificationData);
  }

  // 로컬 알림 표시
  // Future<void> _showLocalNotification(
  //   String title,
  //   String body,
  //   Map<String, dynamic> data,
  // ) async {
  //   const AndroidNotificationDetails androidDetails =
  //       AndroidNotificationDetails(
  //         'high_importance_channel',
  //         '스트리머 알림',
  //         channelDescription: '스트리머 관련 알림을 받습니다.',
  //         importance: Importance.high,
  //         priority: Priority.high,
  //         showWhen: true,
  //       );

  //   const DarwinNotificationDetails iosDetails = DarwinNotificationDetails(
  //     presentAlert: true,
  //     presentBadge: true,
  //     presentSound: true,
  //   );

  //   const NotificationDetails notificationDetails = NotificationDetails(
  //     android: androidDetails,
  //     iOS: iosDetails,
  //   );

  //   // 페이로드 설정
  //   final String payload = jsonEncode(data);
  //   await _localNotifications.show(
  //     data.containsKey('id')
  //         ? data['id'].hashCode.abs()
  //         : DateTime.now().millisecondsSinceEpoch % 100000, // 유니크한 알림 ID,
  //     title,
  //     body,
  //     notificationDetails,
  //     payload: payload,
  //   );
  // }
}
