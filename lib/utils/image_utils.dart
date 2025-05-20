// ignore_for_file: depend_on_referenced_packages

import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:image/image.dart' as img;

class ImageUtils {
  // HTTP 클라이언트 재사용을 위한 인스턴스 (성능 최적화)
  static final http.Client _client = http.Client();

  // 최대 이미지 크기 제한 (메모리 사용량 관리)
  static const int maxWidth = 1200;
  static const int maxHeight = 1200;

  // 네트워크에서 이미지를 가져와 처리하는 메서드
  static Future<Uint8List?> fetchAndProcessImage(String url) async {
    try {
      debugPrint('Fetching image from $url');

      if (kIsWeb) {
      }
      // 타임아웃 설정으로 네트워크 지연 방지
      final response = await _client.get(
            Uri.parse(url),
            headers: {
              'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115 Safari/537.36',
            },
          ).timeout(const Duration(seconds: 10));

      if (response.statusCode != 200) {
        throw Exception('Failed to load image: ${response.statusCode}');
      }

      return compute(_processImageBytes, response.bodyBytes);
    } catch (e) {
      debugPrint('Error loading image: $e');
      return null;
    }
  }

  // 별도 isolate에서 실행되는 이미지 처리 함수
  static Uint8List? _processImageBytes(Uint8List bytes) {
    try {
      final image = img.decodeImage(bytes);

      if (image == null) {
        throw Exception('Unable to decode image');
      }

      // 이미지 크기가 너무 크면 리사이징
      img.Image processedImage = image;
      if (image.width > maxWidth || image.height > maxHeight) {
        processedImage = img.copyResize(
          image,
          width: min(image.width, maxWidth),
          height: min(image.height, maxHeight),
          interpolation: img.Interpolation.average, // 품질과 속도의 균형
        );
      }

      // 투명도가 있는 이미지 처리 (배경 추가)
      if (_hasTransparency(processedImage)) {
        final withBackground = img.Image(
          width: processedImage.width,
          height: processedImage.height,
        );
        img.fill(withBackground, color: img.ColorUint8.rgb(255, 255, 255)); // 흰색 배경
        img.compositeImage(withBackground, processedImage);

        // JPG 형식으로 변환하여 용량 감소
        return Uint8List.fromList(img.encodeJpg(withBackground, quality: 85));
      } else {
        return Uint8List.fromList(img.encodeJpg(processedImage, quality: 85));
      }
    } catch (e) {
      debugPrint('Error processing image: $e');
      return null;
    }
  }

  // 이미지에 투명도가 있는지 효율적으로 확인하는 메서드
  static bool _hasTransparency(img.Image image) {
    // 작은 이미지는 모든 픽셀 검사
    if (image.width * image.height < 10000) {
      for (int y = 0; y < image.height; y++) {
        for (int x = 0; x < image.width; x++) {
          final pixel = image.getPixel(x, y);
          if (pixel.a < 255) {
            return true;
          }
        }
      }
      return false;
    }

    // 큰 이미지는 샘플링 방식으로 효율적 검사
    final sampleSize = max(100, (image.width * image.height) ~/ 100);
    final random = Random();

    // 무작위 픽셀 샘플링
    for (int i = 0; i < sampleSize; i++) {
      final x = random.nextInt(image.width);
      final y = random.nextInt(image.height);
      final pixel = image.getPixel(x, y);
      if (pixel.a < 255) {
        return true;
      }
    }

    // 테두리 픽셀 추가 검사 (투명도가 테두리에 많이 있음)
    for (int x = 0; x < image.width; x += image.width ~/ 20) {
      for (int y = 0; y < image.height; y += image.height ~/ 20) {
        final pixel = image.getPixel(x, y);
        if (pixel.a < 255) {
          return true;
        }
      }
    }

    return false;
  }

  // HTTP 클라이언트 자원 해제
  static void dispose() {
    _client.close();
  }
}