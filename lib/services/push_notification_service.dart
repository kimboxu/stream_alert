import 'dart:convert';
import 'dart:io';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';
import '../models/notification_model.dart';

// 백그라운드 메시지 핸들러
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();

  // 알림 데이터를 SharedPreferences에 임시 저장
  await _saveNotification(message);

  if (kDebugMode) {
    print("백그라운드 메시지 수신: ${message.messageId}");
    print("데이터: ${message.data}");
  }
}

// 알림 임시 저장 함수 (백그라운드에서도 동작)
Future<void> _saveNotification(RemoteMessage message) async {
  try {
    final prefs = await SharedPreferences.getInstance();

    // 기존 알림 목록 가져오기
    final notifications = prefs.getStringList('notifications') ?? [];

    // 새 알림 데이터 생성
    final notificationData = {
      'id': message.messageId ?? DateTime.now().millisecondsSinceEpoch.toString(),
      'username': message.notification?.title ?? message.data['username'] ?? '알림',
      'content': message.notification?.body ?? message.data['content'] ?? '새 메시지가 있습니다',
      'avatar_url': message.data['avatar_url'] ?? '',
      'timestamp': DateTime.now().toIso8601String(),
      'read': false,
    };

    // embeds 데이터가 있으면 추가
    if (message.data.containsKey('embeds')) {
      try {
        notificationData['embeds'] = json.decode(message.data['embeds']);
      } catch (e) {
        // 문자열이 아닌 경우 그대로 사용
        notificationData['embeds'] = message.data['embeds'];
      }
    }

    // 그 외 추가 데이터 병합
    message.data.forEach((key, value) {
      if (!notificationData.containsKey(key)) {
        notificationData[key] = value;
      }
    });

    // 알림 목록에 추가
    notifications.add(jsonEncode(notificationData));

    // 최대 100개까지만 저장 (오래된 알림은 삭제)
    if (notifications.length > 100) {
      notifications.removeRange(0, notifications.length - 100);
    }

    // 저장
    await prefs.setStringList('notifications', notifications);
  } catch (e) {
    if (kDebugMode) {
      print('알림 저장 중 오류: $e');
    }
  }
}
class PushNotificationService {
  final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  final FlutterLocalNotificationsPlugin _localNotifications = FlutterLocalNotificationsPlugin();

  // 싱글톤 패턴
  static final PushNotificationService _instance = PushNotificationService._internal();

  factory PushNotificationService() {
    return _instance;
  }

  PushNotificationService._internal();

  // 알림 초기화
  Future<void> initialize() async {
    try {
      // Firebase 초기화는 main.dart에서 이미 했을 수 있음
      try {
        await Firebase.initializeApp();
      } catch (e) {
        if (kDebugMode) {
          print('Firebase 이미 초기화됨: $e');
        }
      }

      // iOS 알림 권한 요청
      if (Platform.isIOS) {
        await _messaging.requestPermission(
          alert: true,
          badge: true,
          sound: true,
        );
      }

      // 백그라운드 핸들러 설정
      FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);

      // 안드로이드용 로컬 알림 설정
      const AndroidInitializationSettings androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
      const DarwinInitializationSettings iosSettings = DarwinInitializationSettings();
      const InitializationSettings initSettings = InitializationSettings(
        android: androidSettings,
        iOS: iosSettings,
      );

      await _localNotifications.initialize(
        initSettings,
        onDidReceiveNotificationResponse: (NotificationResponse response) {
          // 알림 클릭 시 처리
          if (kDebugMode) {
            print('알림 클릭됨: ${response.payload}');
          }
          // 여기에 알림 클릭 시 특정 화면으로 이동하는 로직 추가 가능
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
          .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
          ?.createNotificationChannel(channel);

      // 포그라운드 메시지 처리
      FirebaseMessaging.onMessage.listen(_handleForegroundMessage);

      // 앱이 종료된 상태에서 알림 클릭으로 열린 경우 처리
      FirebaseMessaging.instance.getInitialMessage().then((message) {
        if (message != null) {
          if (kDebugMode) {
            print('앱이 종료된 상태에서 알림 클릭: ${message.data}');
          }
          _saveNotification(message);
        }
      });

      // 앱이 백그라운드 상태에서 알림 클릭으로 열린 경우 처리
      FirebaseMessaging.onMessageOpenedApp.listen((message) {
        if (kDebugMode) {
          print('백그라운드 상태에서 알림 클릭: ${message.data}');
        }
        _saveNotification(message);
      });

      // 토큰 갱신 리스너
      _messaging.onTokenRefresh.listen(_updateTokenToServer);

      // 토큰 가져오기
      final fcmToken = await _messaging.getToken();
      if (fcmToken != null) {
        if (kDebugMode) {
          print('FCM 토큰: $fcmToken');
        }
        await _updateTokenToServer(fcmToken);
      }
    } catch (e) {
      if (kDebugMode) {
        print('알림 서비스 초기화 중 오류: $e');
      }
    }
  }

  // 서버에서 알림 가져오기 (로그인 시 및 주기적으로 호출)
  Future<List<NotificationModel>> loadNotificationsFromServer() async {
    final prefs = await SharedPreferences.getInstance();
    final username = prefs.getString('username');
    final discordWebhooksURL = prefs.getString('discordWebhooksURL');
    
    List<NotificationModel> notifications = [];

    if (username != null && discordWebhooksURL != null) {
      try {
        // 서버에서 알림 가져오기
        notifications = await ApiService.getNotifications(username, discordWebhooksURL);
        
        if (notifications.isNotEmpty) {
          // 가져온 알림을 로컬에 저장
          final notificationsJson = notifications.map((notification) => 
            jsonEncode(notification.toJson())).toList();
          
          await prefs.setStringList('notifications', notificationsJson);
          
          // 읽지 않은 알림 개수 확인
          final unreadCount = notifications.where((n) => n.read == false).length;
          if (unreadCount > 0) {
            // 읽지 않은 알림이 있으면 로컬 알림으로 표시 (선택적)
            // await _showLocalNotification('읽지 않은 알림', '읽지 않은 알림이 $unreadCount개 있습니다.', {});
          }
          
          if (kDebugMode) {
            print('서버에서 ${notifications.length}개의 알림을 로드했습니다.');
          }
        }
        
        return notifications;
      } catch (e) {
        if (kDebugMode) {
          print('서버에서 알림 가져오기 오류: $e');
        }
      }
    }
    
    // 로컬에 저장된 알림 반환
    final localNotificationsJson = prefs.getStringList('notifications') ?? [];
    final localNotifications = localNotificationsJson
        .map((json) => NotificationModel.fromJson(jsonDecode(json)))
        .toList();
    
    // 시간 순으로 정렬
    localNotifications.sort((a, b) => a.timestamp.compareTo(b.timestamp));
    
    return localNotifications;
  }

  // 토큰 서버에 등록
  Future<void> _updateTokenToServer(String token) async {
    try {
      // SharedPreferences에서 사용자 정보 가져오기
      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username');
      final discordWebhooksURL = prefs.getString('discordWebhooksURL');

      if (username != null && discordWebhooksURL != null) {
        // 서버에 토큰 등록
        await ApiService.registerFcmToken(username, discordWebhooksURL, token);
      } else {
        if (kDebugMode) {
          print('토큰 등록을 위한 사용자 정보가 없습니다.');
        }
      }
    } catch (e) {
      if (kDebugMode) {
        print('토큰 업데이트 오류: $e');
      }
    }
  }

  Future<void> registerToken() async {
    final fcmToken = await _messaging.getToken();
    if (fcmToken != null) {
      await _updateTokenToServer(fcmToken);
    }
  }

  // 로그아웃 시 토큰 제거
  Future<void> removeToken() async {
    try {
      // 서버에 토큰 제거 요청
      final prefs = await SharedPreferences.getInstance();
      final username = prefs.getString('username');
      final discordWebhooksURL = prefs.getString('discordWebhooksURL');
      
      if (username != null && discordWebhooksURL != null) {
        // 서버에 토큰 제거 요청 메서드 호출 (구현 필요)
        // await ApiService.removeToken(username, discordWebhooksURL);
      }
      
      // 로컬 알림 목록 삭제
      await prefs.remove('notifications');
      
      if (kDebugMode) {
        print('FCM 토큰 및 알림 데이터 제거 완료');
      }
    } catch (e) {
      if (kDebugMode) {
        print('토큰 제거 중 오류: $e');
      }
    }
  }

  // 포그라운드 메시지 처리
void _handleForegroundMessage(RemoteMessage message) async {
  if (kDebugMode) {
    print('포그라운드 메시지 수신: ${message.notification?.title}');
    print('데이터: ${message.data}');
  }

  // 알림 저장
  await _saveNotification(message);

  // 알림 데이터에서 정보 추출
  final title = message.notification?.title ?? message.data['username'] ?? '알림';
  final body = message.notification?.body ?? message.data['content'] ?? '';

  // 로컬 알림으로 표시 (간단한 방식)
  _showLocalNotification(title, body, message.data);
}

  // 로컬 알림 표시
  Future<void> _showLocalNotification(
    String title,
    String body,
    Map<String, dynamic> data,
  ) async {
    const AndroidNotificationDetails androidDetails = AndroidNotificationDetails(
      'high_importance_channel',
      '스트리머 알림',
      channelDescription: '스트리머 관련 알림을 받습니다.',
      importance: Importance.high,
      priority: Priority.high,
      showWhen: true,
    );

    const DarwinNotificationDetails iosDetails = DarwinNotificationDetails(
      presentAlert: true,
      presentBadge: true,
      presentSound: true,
    );

    const NotificationDetails notificationDetails = NotificationDetails(
      android: androidDetails,
      iOS: iosDetails,
    );

    // 페이로드 설정
    final String payload = jsonEncode(data);

    await _localNotifications.show(
      DateTime.now().millisecondsSinceEpoch % 100000, // 유니크한 알림 ID
      title,
      body,
      notificationDetails,
      payload: payload,
    );
  }
}