import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter/foundation.dart';
import '../utils/image_utils.dart';

class CacheHelper {
  static const String _streamerDataKey = 'cached_streamer_data'; // 스트리머 데이터 캐시 키
  static const String _imagesCachePrefix = 'cached_image_'; // 이미지 캐시 키 접두사
  static const Duration _cacheValidity = Duration(hours: 12); // 캐시 유효 기간 (12시간)

  // 메모리 캐시 (앱 실행 중에만 유지)
  static final Map<String, Uint8List> _memoryImageCache = {};

  // 스트리머 데이터 캐싱 - 서버에서 가져온 데이터를 로컬에 저장
  static Future<void> cacheStreamerData(Map<String, dynamic> data) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      // 타임스탬프를 포함하여 저장 (캐시 만료 확인용)
      final cacheData = {
        'timestamp': DateTime.now().millisecondsSinceEpoch,
        'data': data,
      };
      await prefs.setString(_streamerDataKey, json.encode(cacheData));

      debugPrint('스트리머 데이터가 캐시에 저장되었습니다.');
    } catch (e) {
      debugPrint('캐시 저장 실패: $e');
    }
  }

  // 캐시된 스트리머 데이터 불러오기\
  static Future<Map<String, dynamic>?> getCachedStreamerData() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final cachedString = prefs.getString(_streamerDataKey);

      // 캐시 데이터가 없는 경우
      if (cachedString == null || cachedString.isEmpty) {
        return null;
      }

      final cachedData = json.decode(cachedString);
      final timestamp = cachedData['timestamp'] as int;
      final cachedTime = DateTime.fromMillisecondsSinceEpoch(timestamp);

      // 캐시 만료 여부 확인 (12시간 이상 지난 경우)
      if (DateTime.now().difference(cachedTime) > _cacheValidity) {
        debugPrint('캐시가 만료되었습니다.');
        return null;
      }

      debugPrint('캐시된 스트리머 데이터를 사용합니다.');
      return cachedData['data'];
    } catch (e) {
      debugPrint('캐시 불러오기 실패: $e');
      return null;
    }
  }

  // 이미지 캐싱 메서드
  static Future<Uint8List?> getCachedImage(String url) async {
    if (url.isEmpty) return null;

    // 메모리 캐시 확인
    if (_memoryImageCache.containsKey(url)) {
      return _memoryImageCache[url];
    }

    try {
      // 디스크 캐시 확인
      final prefs = await SharedPreferences.getInstance();
      final cacheKey = _imagesCachePrefix + _hashUrl(url); // URL 해시화
      final cachedData = prefs.getString(cacheKey);

      if (cachedData != null) {
        // 캐시된 이미지 데이터 디코딩
        final imageData = await ImageUtils.fetchAndProcessImage(url, preserveTransparency: false);
        // 메모리 캐시에 추가
        if (imageData != null) {
          _memoryImageCache[url] = imageData;
          debugPrint('이미지 캐시 히트: $url');
          return imageData;
        }
      }

      // 캐시에 없으면 네트워크에서 가져와 이미지 처리
      final processedImage = await ImageUtils.fetchAndProcessImage(url, preserveTransparency: false);

      if (processedImage != null) {
        // 처리된 이미지를 메모리와 디스크에 캐싱
        _memoryImageCache[url] = processedImage;
        // 디스크에도 저장
        await prefs.setString(cacheKey, base64Encode(processedImage));
        debugPrint('이미지 처리 및 캐싱 완료: $url');
        return processedImage;
      }
    } catch (e) {
      debugPrint('이미지 처리/캐싱 오류: $url - $e');
    }

    return null;
  }

  // 여러 이미지를 미리 로드하는 메서드 (성능 최적화)
  static Future<void> preloadImages(List<String> urls) async {
    debugPrint('${urls.length}개의 이미지 미리 로드 시작');
    int successCount = 0;

    for (final url in urls) {
      if (url.isNotEmpty) {
        try {
          final image = await getCachedImage(url);
          if (image != null) {
            successCount++;
          }
        } catch (e) {
          debugPrint('이미지 미리 로드 실패: $url - $e');
        }
      }
    }

    debugPrint('이미지 미리 로드 완료: $successCount/${urls.length}개 성공');
  }

  // URL을 캐시 키로 변환하는 해싱 메서드
  static String _hashUrl(String url) {
    // 간단한 해싱
    var hash = 0;
    for (var i = 0; i < url.length; i++) {
      hash = (hash * 31 + url.codeUnitAt(i)) & 0xFFFFFFFF;
    }
    return hash.toString();
  }

  // 모든 캐시를 지우는 메서드
  static Future<void> clearCache() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_streamerDataKey);

      // 메모리 이미지 캐시 제거
      _memoryImageCache.clear();

      // 이미지 캐시 키 목록 가져와 제거
      final keys = prefs.getKeys();
      for (final key in keys) {
        if (key.startsWith(_imagesCachePrefix)) {
          await prefs.remove(key);
        }
      }

      debugPrint('모든 캐시가 삭제되었습니다.');
    } catch (e) {
      debugPrint('캐시 삭제 실패: $e');
    }
  }
}