import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import '../utils/cache_helper.dart';

class ProfileImageWidget extends StatelessWidget {
  final String url; // 프로필 이미지 URL
  final double size; // 이미지 크기
  final bool isSelected; // 선택 상태 표시 여부
  
  const ProfileImageWidget({
    super.key,
    required this.url,
    this.size = 80, // 기본 크기 80픽셀
    this.isSelected = false, // 기본값은 선택되지 않은 상태
  });
  
  @override
  Widget build(BuildContext context) {
    // 원형 프로필 이미지 컨테이너
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          // 선택된 경우 테마 색상의 테두리 표시
          color: isSelected ? Theme.of(context).primaryColor : Colors.transparent,
          width: isSelected ? 2.0 : 0.0,
        ),
      ),
      child: ClipOval(
        child: FutureBuilder<Uint8List?>(
          // CacheHelper를 사용해 캐싱된 이미지 로드
          future: CacheHelper.getCachedImage(url),
          builder: (context, snapshot) {
            // 로딩 중인 경우 프로그레스 인디케이터 표시
            if (snapshot.connectionState == ConnectionState.waiting) {
              return Container(
                color: Colors.grey[200],
                child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
              );
            } 
            // 오류 발생하거나 데이터가 없는 경우 기본 아이콘 표시
            else if (snapshot.hasError || snapshot.data == null) {
              return Container(
                color: Colors.grey[300],
                child: Icon(Icons.person, size: size/2, color: Colors.grey[600]),
              );
            } 
            // 이미지 데이터가 있는 경우 표시
            else {
              return Image.memory(
                snapshot.data!,
                fit: BoxFit.cover,
                filterQuality: FilterQuality.medium, // 적절한 이미지 품질 설정
              );
            }
          },
        ),
      ),
    );
  }
}