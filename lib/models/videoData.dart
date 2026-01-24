// 치지직/아프리카 비디오 정보를 관리하는 클래스
class VideoData {
  final String channelID;    // 채널 고유 ID
  final String platform;     // 플랫폼 (chzzk, afreeca)

  // 생성자
  VideoData({
    required this.channelID,
    required this.platform,
  });

  // JSON 데이터로부터 VideoData 객체 생성하는 팩토리 메서드
  factory VideoData.fromJson(
    Map<String, dynamic> json, {
    required String platform,
  }) {
    return VideoData(
      channelID: json['channelID'] ?? '',
      platform: platform,
    );
  }
}