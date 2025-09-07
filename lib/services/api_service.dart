// ignore_for_file: depend_on_referenced_packages

import 'dart:io';
import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

import 'package:shared_preferences/shared_preferences.dart';
import '../models/streamer_data.dart';
import '../models/cafe_data.dart';
import '../models/chzzk_video.dart';
import '../models/youtube_data.dart';
import '../models/notification_model.dart';
import '../utils/cache_helper.dart';
import '../utils/url_helper.dart';

class ApiService {
  // static const String baseUrl = 'http://49.142.11.175:5000'; // 디버깅 용도
  // static const String baseUrl = 'http://192.168.0.7:5000/'; // 디버깅 용도
  static const String baseUrl = 'https://discordbotsetting.duckdns.org/'; // 오라클 서버 주소

  // 이미지 URL을 프록시 URL로 변환하는 함수
  static processImageUrl(String url) {
    if (!kIsWeb || url.isEmpty) {
      return url;
    }

    if (url.contains('i.imgur.com')) {
      return url;
    }

    // 네이버 이미지인 경우 특별 처리
    if (url.contains('pstatic.net') || url.contains('naver.com')) {
      return '$baseUrl/proxy-image?url=${Uri.encodeComponent(url)}&source=naver';
    }

    // 서버측 프록시를 통해 이미지 로드
    return '$baseUrl/proxy-image?url=${Uri.encodeComponent(url)}';
  }

  // FCM 토큰 등록 메서드
  static Future<bool> registerFcmToken(
    String username,
    String discordWebhooksURL,
    String fcmToken,
    String deviceId,
  ) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/register_fcm_token'),
        body: {
          'username': username,
          'discordWebhooksURL': discordWebhooksURL,
          'fcm_token': fcmToken,
          'device_id': deviceId,
        },
      );

      if (response.statusCode == 200) {
        debugPrint('FCM 토큰 등록 성공');

        return true;
      } else {
        debugPrint('FCM 토큰 등록 실패: ${response.statusCode}, ${response.body}');

        return false;
      }
    } catch (e) {
      debugPrint('FCM 토큰 등록 중 오류: $e');

      return false;
    }
  }

  // FCM 토큰 제거 메서드 (로그아웃 시 호출)
  static Future<bool> removeToken(
    String username,
    String discordWebhooksURL,
    String fcmToken,
    String deviceId,
  ) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/remove_fcm_token'),
        body: {
          'username': username,
          'discordWebhooksURL': discordWebhooksURL,
          'fcm_token': fcmToken,
          'device_id': deviceId,
        },
      );

      if (response.statusCode == 200) {
        debugPrint('FCM 토큰 제거 성공');

        return true;
      } else {
        debugPrint('FCM 토큰 제거 실패: ${response.statusCode}');

        return false;
      }
    } catch (e) {
      debugPrint('FCM 토큰 제거 중 오류: $e');

      return false;
    }
  }

  // 서버에서 알림 가져오기
  static Future<Map<String, dynamic>> getNotifications(
    String username,
    String discordWebhooksURL, {
    int page = 1,
    int limit = 50,
    int retryCount = 3, // 재시도 횟수
  }) async {
    int attempts = 0;

    // 재시도 로직 - 네트워크 오류나 서버 장애 시 여러 번 시도
    while (attempts < retryCount) {
      attempts++;
      try {
        final normalizedWebhookUrl = UrlHelper.normalizeDiscordWebhookUrl(
          discordWebhooksURL,
        );

        if (attempts > 1) {
          debugPrint('알림 가져오기 시도 $attempts/$retryCount');
        }

        final client = http.Client();

        try {
          // 알림 요청 API 호출
          final response = await client
              .get(
                Uri.parse(
                  '$baseUrl/get_notifications?username=$username&discordWebhooksURL=$normalizedWebhookUrl&page=$page&limit=$limit',
                ),
              )
              .timeout(Duration(seconds: 15)); // 타임아웃 설정

          // 요청 성공 시 결과 반환
          if (response.statusCode == 200) {
            final Map<String, dynamic> data = json.decode(response.body);

            if (data['status'] == 'success') {
              // JSON 배열을 NotificationModel 객체 목록으로 변환
              final notifications =
                  (data['notifications'] as List? ?? [])
                      .map(
                        (item) => NotificationModel.fromJson(
                          Map<String, dynamic>.from(item),
                        ),
                      )
                      .toList();

              // 시간순 정렬
              notifications.sort((a, b) => b.timestamp.compareTo(a.timestamp));

              return {
                'success': true,
                'notifications': notifications,
                'hasMore':
                    data['has_more'] ??
                    notifications.isNotEmpty, // 서버에서 더 많은 데이터가 있는지 여부
              };
            } else if (data['status'] == 'empty') {
              // 데이터가 없는 경우 (페이지가 비어있음)
              return {
                'success': true,
                'notifications': <NotificationModel>[],
                'hasMore': false,
              };
            } else {
              // 기타 상태

              debugPrint(
                '알림 가져오기 실패: 상태 - ${data['status']}, 메시지 - ${data['message'] ?? "알 수 없는 오류"}',
              );

              // 마지막 시도가 아닌 경우 재시도
              if (attempts < retryCount) {
                await Future.delayed(Duration(seconds: 1 * attempts)); // 지수 백오프
                continue;
              }

              return {
                'success': false,
                'error': '서버 오류: ${data['message'] ?? "알 수 없는 오류"}',
                'errorType': 'server',
              };
            }
          } else if (response.statusCode == 404) {
            // 404는 데이터가 없는 경우로 처리
            return {
              'success': true,
              'notifications': <NotificationModel>[],
              'hasMore': false,
            };
          } else {
            debugPrint(
              '알림 가져오기 실패 (시도 $attempts/$retryCount): ${response.statusCode}, ${response.body}',
            );

            // 마지막 시도가 아닌 경우 재시도
            if (attempts < retryCount) {
              await Future.delayed(Duration(seconds: 1 * attempts)); // 지수 백오프
              continue;
            }

            return {
              'success': false,
              'error': '서버 응답 오류: ${response.statusCode}',
              'errorType': 'server',
              'attemptsCount': attempts,
            };
          }
        } finally {
          client.close(); // 항상 클라이언트 연결 닫기
        }
      } on TimeoutException {
        debugPrint('알림 가져오기 타임아웃 (시도 $attempts/$retryCount)');

        // 마지막 시도가 아닌 경우 재시도
        if (attempts < retryCount) {
          await Future.delayed(Duration(seconds: 1 * attempts)); // 지수 백오프
          continue;
        }

        return {
          'success': false,
          'error': '서버 응답 시간 초과',
          'errorType': 'network',
          'attemptsCount': attempts,
        };
      } on SocketException {
        debugPrint('알림 가져오기 중 네트워크 오류 (시도 $attempts/$retryCount)');

        // 마지막 시도가 아닌 경우 재시도
        if (attempts < retryCount) {
          await Future.delayed(Duration(seconds: 1 * attempts)); // 지수 백오프
          continue;
        }

        return {
          'success': false,
          'error': '네트워크 연결 오류',
          'errorType': 'network',
          'attemptsCount': attempts,
        };
      } on http.ClientException catch (e) {
        debugPrint('HTTP 클라이언트 오류 (시도 $attempts/$retryCount): $e');

        // 마지막 시도가 아닌 경우 재시도
        if (attempts < retryCount) {
          await Future.delayed(Duration(seconds: 1 * attempts)); // 지수 백오프
          continue;
        }

        return {
          'success': false,
          'error': '네트워크 연결이 끊어졌습니다',
          'errorType': 'network',
          'errorDetails': e.toString(),
          'attemptsCount': attempts,
        };
      } catch (e) {
        debugPrint('알림 가져오기 중 기타 오류 (시도 $attempts/$retryCount): $e');

        // 마지막 시도가 아닌 경우 재시도
        if (attempts < retryCount) {
          await Future.delayed(Duration(seconds: 1 * attempts)); // 지수 백오프
          continue;
        }

        return {
          'success': false,
          'error': '알림 가져오기 중 오류: $e',
          'errorType': 'unknown',
          'attemptsCount': attempts,
        };
      }
    }

    // 모든 시도가 실패한 경우
    return {
      'success': false,
      'error': '여러 번 시도했으나 알림을 가져올 수 없습니다',
      'errorType': 'network',
      'attemptsCount': attempts,
    };
  }

  // 알림 읽음 표시 메서드
  static Future<bool> markNotificationsAsRead(
    String username,
    String discordWebhooksURL,
    List<String> notificationIds,
  ) async {
    try {
      final normalizedWebhookUrl = UrlHelper.normalizeDiscordWebhookUrl(
        discordWebhooksURL,
      );

      final response = await http.post(
        Uri.parse('$baseUrl/mark_notifications_read'),
        body: {
          'username': username,
          'discordWebhooksURL': normalizedWebhookUrl,
          'notification_ids': json.encode(notificationIds),
        },
      );

      return response.statusCode == 200;
    } catch (e) {
      debugPrint('알림 읽음 표시 중 오류: $e');

      return false;
    }
  }

  // 알림 전체 삭제 메서드
  static Future<bool> clearAllNotifications(
    String username,
    String discordWebhooksURL,
  ) async {
    try {
      final normalizedWebhookUrl = UrlHelper.normalizeDiscordWebhookUrl(
        discordWebhooksURL,
      );

      final response = await http.post(
        Uri.parse('$baseUrl/clear_notifications'),
        body: {
          'username': username,
          'discordWebhooksURL': normalizedWebhookUrl,
        },
      );

      return response.statusCode == 200;
    } catch (e) {
      debugPrint('알림 삭제 중 오류: $e');

      return false;
    }
  }

  // 사용자 설정 가져오기
  static Future<Map<String, dynamic>> getUserSettings(
    String username,
    String discordWebhooksURL,
  ) async {
    final response = await http.get(
      Uri.parse(
        '$baseUrl/get_user_settings?username=$username&discordWebhooksURL=$discordWebhooksURL',
      ),
    );

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('설정을 불러오는데 실패했습니다: ${response.statusCode}');
    }
  }

  // 스트리머 목록 가져오기
  static Future<Map<String, dynamic>> getStreamers({
    int maxRetries = 3,
    bool useCache = true,
    bool forceRefresh = false,
  }) async {
    if (useCache && !forceRefresh) {
      final cachedData = await CacheHelper.getCachedStreamerData();
      if (cachedData != null) {
        return cachedData;
      }
    }

    int attempt = 0;
    Exception? lastException;

    while (attempt < maxRetries) {
      try {
        if (attempt > 0) {
          debugPrint('스트리머 데이터 가져오기 시도 ${attempt + 1}/$maxRetries');
        }

        final response = await http
            .get(
              Uri.parse('$baseUrl/get_streamers'),
              headers: {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'},
            )
            .timeout(
              Duration(seconds: 10),
              onTimeout: () {
                throw TimeoutException('서버 응답 시간이 너무 깁니다.');
              },
            );

        if (response.statusCode == 200) {
          final data = json.decode(response.body);

          // 응답 검증
          if (data == null ||
              (!data.containsKey('afreecaStreamers') &&
                  !data.containsKey('chzzkStreamers') &&
                  !data.containsKey('cafeStreamers') &&
                  !data.containsKey('chzzkVideoStreamers') &&
                  !data.containsKey('youtubeStreamers') &&
                  !data.containsKey('chzzkChatFilter') &&
                  !data.containsKey('afreecaChatFilter'))) {
            throw Exception('서버 응답이 유효하지 않습니다.');
          }

          // 캐시에 저장
          if (useCache) {
            CacheHelper.cacheStreamerData(data);
          }

          return data;
        } else {
          throw Exception('스트리머 정보를 불러오는데 실패했습니다: ${response.statusCode}');
        }
      } catch (e) {
        attempt++;
        lastException = e is Exception ? e : Exception(e.toString());

        debugPrint('스트리머 데이터 가져오기 실패 (시도 $attempt): $e');

        if (attempt < maxRetries) {
          // 지수 백오프 전략 적용
          await Future.delayed(Duration(seconds: 1 * (1 << (attempt - 1))));
        }
      }
    }

    // 모든 시도가 실패한 경우
    if (useCache) {
      // 마지막 시도 - 캐시 확인
      try {
        final prefs = await SharedPreferences.getInstance();
        final cachedString = prefs.getString('cached_streamer_data');

        if (cachedString != null && cachedString.isNotEmpty) {
          final cachedData = json.decode(cachedString);

          debugPrint('네트워크 실패, 만료된 캐시 사용');

          return cachedData['data'];
        }
      } catch (e) {
        debugPrint('만료된 캐시 접근 실패: $e');
      }
    }

    throw lastException ?? Exception('스트리머 정보를 가져오는 데 실패했습니다.');
  }

  // 사용자 설정 저장
  static Future<bool> saveUserSettings(Map<String, dynamic> data) async {
    final response = await http.post(
      Uri.parse('$baseUrl/save_user_settings'),
      body: data,
    );

    return response.statusCode == 200;
  }

  // 스트리머 데이터 파싱
  static List<StreamerData> parseStreamers(Map<String, dynamic> data) {
    List<StreamerData> streamers = [];

    try {
      // 아프리카TV 스트리머 파싱
      List<dynamic> afreecaStreamers = data['afreecaStreamers'] ?? [];
      for (var streamer in afreecaStreamers) {
        if (streamer is Map &&
            streamer.containsKey('channelName') &&
            streamer.containsKey('channelID')) {
          streamers.add(
            StreamerData(
              name: streamer['channelName'] ?? '(알 수 없음)',
              platform: 'afreeca',
              channelID: streamer['channelID'] ?? '',
              profileImageUrl: streamer['profile_image'] ?? '',
            ),
          );
        }
      }

      // 치지직 스트리머 파싱
      List<dynamic> chzzkStreamers = data['chzzkStreamers'] ?? [];
      for (var streamer in chzzkStreamers) {
        if (streamer is Map &&
            streamer.containsKey('channelName') &&
            streamer.containsKey('channelID')) {
          streamers.add(
            StreamerData(
              name: streamer['channelName'] ?? '(알 수 없음)',
              platform: 'chzzk',
              channelID: streamer['channelID'] ?? '',
              profileImageUrl: streamer['profile_image'] ?? '',
            ),
          );
        }
      }
    } catch (e) {
      debugPrint('스트리머 데이터 파싱 중 오류: $e');
    }

    return streamers;
  }

  // 카페 데이터 파싱
  static List<CafeData> parseCafeData(Map<String, dynamic> data) {
    List<CafeData> cafeDataList = [];
    List<dynamic> cafeStreamers = data['cafeStreamers'] ?? [];

    for (var cafeStreamer in cafeStreamers) {
      try {
        CafeData cafe = CafeData.fromJson(cafeStreamer);
        cafeDataList.add(cafe);
      } catch (e) {
        debugPrint('Error parsing cafe data: $e');
      }
    }

    return cafeDataList;
  }

  // 치지직 VOD 데이터 파싱
  static List<ChzzkVideo> parseChzzkVideo(Map<String, dynamic> data) {
    List<ChzzkVideo> chzzkVideoList = [];
    List<dynamic> chzzkVideoStreamers = data['chzzkVideoStreamers'] ?? [];

    for (var chzzkVideoStreamer in chzzkVideoStreamers) {
      try {
        ChzzkVideo chzzkVideo = ChzzkVideo.fromJson(chzzkVideoStreamer);
        chzzkVideoList.add(chzzkVideo);
      } catch (e) {
        debugPrint('Error parsing chzzk video data: $e');
      }
    }

    return chzzkVideoList;
  }

  // 유튜브 데이터 파싱
  static List<YoutubeData> parseYoutubeData(Map<String, dynamic> data) {
    List<YoutubeData> result = [];
    List<dynamic> youtubeStreamers = data['youtubeStreamers'] ?? [];

    Map<String, List<Map<String, dynamic>>> channelIdToYoutubeData = {};

    for (var youtubeStreamer in youtubeStreamers) {
      String channelID = youtubeStreamer['channelID'] ?? '';

      if (channelID.isNotEmpty) {
        if (!channelIdToYoutubeData.containsKey(channelID)) {
          channelIdToYoutubeData[channelID] = [];
        }
        channelIdToYoutubeData[channelID]!.add(youtubeStreamer);
      }
    }

    channelIdToYoutubeData.forEach((channelID, channelDataList) {
      try {
        String channelName = channelDataList.first['channelName'] ?? '';

        Map<String, List<String>> youtubeDict = {};
        youtubeDict[channelID] = [];

        for (var data in channelDataList) {
          String dataChannelName = data['channelName'] ?? '';
          if (dataChannelName.isNotEmpty) {
            youtubeDict[channelID]!.add(dataChannelName);
          }
        }

        YoutubeData youtube = YoutubeData(
          channelID: channelID,
          channelName: channelName,
          youtubeNameDict: youtubeDict,
        );

        result.add(youtube);
      } catch (e) {
        debugPrint(
          'Error processing YouTube data for channelID $channelID: $e',
        );
      }
    });

    return result;
  }

  // 로그인 API 호출
  static Future<Map<String, dynamic>> login(
    String username,
    String discordWebhooksURL,
  ) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/login'),
        body: {'username': username, 'discordWebhooksURL': discordWebhooksURL},
      );

      if (response.statusCode == 200) {
        return json.decode(response.body);
      } else {
        Map<String, dynamic> errorData = json.decode(response.body);
        throw Exception(errorData['message'] ?? '로그인 실패!');
      }
    } catch (e) {
      debugPrint('로그인 오류: $e');

      throw Exception('로그인 중 오류가 발생했습니다: $e');
    }
  }

  // 회원가입 API 호출
  static Future<Map<String, dynamic>> register(
    String username,
    String discordWebhooksURL,
  ) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/register'),
        body: {'username': username, 'discordWebhooksURL': discordWebhooksURL},
      );

      if (response.statusCode == 200) {
        return json.decode(response.body);
      } else {
        Map<String, dynamic> errorData = json.decode(response.body);
        throw Exception(errorData['message'] ?? '회원가입 실패!');
      }
    } catch (e) {
      debugPrint('회원가입 오류: $e');

      throw Exception('회원가입 중 오류가 발생했습니다: $e');
    }
  }

  // 사용자 이름 변경 API 호출
  static Future<bool> updateUsername(
    String oldUsername,
    String discordWebhooksURL,
    String newUsername,
  ) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/update_username'),
        body: {
          'oldUsername': oldUsername,
          'discordWebhooksURL': discordWebhooksURL,
          'newUsername': newUsername,
        },
      );

      if (response.statusCode == 200) {
        return true;
      } else {
        debugPrint('사용자 이름 변경 실패: ${response.statusCode}, ${response.body}');

        return false;
      }
    } catch (e) {
      debugPrint('사용자 이름 변경 중 오류: $e');

      return false;
    }
  }

  // 외부 URL 실행(하이퍼 링크)
  static Future<bool> launchExternalUrl(String url) async {
    if (url.isEmpty) return false;

    try {
      final uri = Uri.parse(url);
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
        return true;
      }
      return false;
    } catch (e) {
      debugPrint('URL 실행 중 오류: $e');
      return false;
    }
  }
}
