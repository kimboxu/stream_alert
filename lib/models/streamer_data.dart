// 스트리머 기본 정보를 관리하는 클래스
class StreamerData {
  final String name;             // 스트리머 이름
  final String platform;         // 플랫폼 (트위치, 치지직, 아프리카 등)
  final String channelID;        // 채널 고유 ID
  final String profileImageUrl;  // 프로필 이미지 URL

  // 생성자
  StreamerData({
    required this.name,
    required this.platform,
    required this.channelID,
    required this.profileImageUrl,
  });
}