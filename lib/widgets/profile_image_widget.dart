import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import '../utils/cache_helper.dart';

class ProfileImageWidget extends StatelessWidget {
  final String url;
  final double size;
  final bool isSelected;
  
  const ProfileImageWidget({
    super.key,
    required this.url,
    this.size = 80,
    this.isSelected = false,
  });
  
  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: isSelected ? Theme.of(context).primaryColor : Colors.transparent,
          width: isSelected ? 2.0 : 0.0,
        ),
      ),
      child: ClipOval(
        child: FutureBuilder<Uint8List?>(
          // CacheHelper에서 캐싱된 이미지 가져오기
          future: CacheHelper.getCachedImage(url),
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return Container(
                color: Colors.grey[200],
                child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
              );
            } else if (snapshot.hasError || snapshot.data == null) {
              return Container(
                color: Colors.grey[300],
                child: Icon(Icons.person, size: size/2, color: Colors.grey[600]),
              );
            } else {
              return Image.memory(
                snapshot.data!,
                fit: BoxFit.cover,
                filterQuality: FilterQuality.medium,
              );
            }
          },
        ),
      ),
    );
  }
}