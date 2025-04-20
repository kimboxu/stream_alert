import 'package:flutter/foundation.dart';
// ignore: depend_on_referenced_packages
import 'package:http/http.dart' as http;
import 'package:image/image.dart' as img;

class ImageUtils {
  static Future<Uint8List?> fetchAndProcessImage(String url) async {
    try {
      if (kDebugMode) {
        print('Trying to fetch image from $url');
      }

      final response = await http.get(
        Uri.parse(url),
        headers: {
          'User-Agent':
              'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115 Safari/537.36',
        },
      );

      if (kDebugMode) {
        print('Status Code: ${response.statusCode}');
      }

      if (response.statusCode != 200) {
        throw Exception('Failed to load image');
      }

      final bytes = response.bodyBytes;
      final image = img.decodeImage(bytes);

      if (image == null) {
        throw Exception('Unable to decode image');
      }

      // Create white background (image 4.x method)
      final withBackground = img.Image(
        width: image.width,
        height: image.height,
      );
      img.fill(withBackground, color: img.ColorUint8.rgb(255, 255, 255));
      img.compositeImage(withBackground, image);

      return Uint8List.fromList(img.encodeJpg(withBackground));
    } catch (e) {
      if (kDebugMode) {
        print('Error loading image: $e');
      }
      return null;
    }
  }
}