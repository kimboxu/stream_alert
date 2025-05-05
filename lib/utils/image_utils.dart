
import 'dart:math';
import 'package:flutter/foundation.dart';
// ignore: depend_on_referenced_packages
import 'package:http/http.dart' as http;
import 'package:image/image.dart' as img;

class ImageUtils {
  // HTTP 클라이언트 재사용을 위한 인스턴스
  static final http.Client _client = http.Client();
  
  // 최대 이미지 크기 제한 (너무 큰 이미지 처리 방지)
  static const int maxWidth = 1200;
  static const int maxHeight = 1200;
  
  // 이미지 캐시가 별도로 관리되므로 여기서는 처리에만 집중
  static Future<Uint8List?> fetchAndProcessImage(String url) async {
    try {
        debugPrint('Fetching image from $url');


      // 타임아웃 추가로 네트워크 지연 제한
      final response = await _client.get(
        Uri.parse(url),
        headers: {
          'User-Agent':
              'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115 Safari/537.36',
        },
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode != 200) {
        throw Exception('Failed to load image: ${response.statusCode}');
      }

      // compute 함수를 사용하여 별도 isolate에서 처리
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
          interpolation: img.Interpolation.average,
        );
      }
      
      // 투명도가 있는지 빠르게 검사
      if (_hasTransparency(processedImage)) {
        final withBackground = img.Image(
          width: processedImage.width,
          height: processedImage.height,
        );
        img.fill(withBackground, color: img.ColorUint8.rgb(255, 255, 255));
        img.compositeImage(withBackground, processedImage);
        
        // 품질 조정으로 처리 속도 향상
        return Uint8List.fromList(img.encodeJpg(withBackground, quality: 85));
      } else {
        return Uint8List.fromList(img.encodeJpg(processedImage, quality: 85));
      }
    } catch (e) {
        debugPrint('Error processing image: $e');

      return null;
    }
  }
  
  // 이미지에 투명도가 있는지 빠르게 확인 (샘플링 방식)
  static bool _hasTransparency(img.Image image) {
    // 작은 이미지는 전체 스캔
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
    
    // 큰 이미지는 전체 픽셀의 약 1%만 검사
    final sampleSize = max(100, (image.width * image.height) ~/ 100);
    final random = Random();
    
    for (int i = 0; i < sampleSize; i++) {
      final x = random.nextInt(image.width);
      final y = random.nextInt(image.height);
      final pixel = image.getPixel(x, y);
      if (pixel.a < 255) {
        return true;
      }
    }
    
    // 테두리 픽셀도 체크
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
  
  static void dispose() {
    _client.close();
  }
}