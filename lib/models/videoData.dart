// 치지직 비디오 정보를 관리하는 클래스
class VideoData {
  final String channelID;  // 채널 고유 ID

  // 생성자
  VideoData({required this.channelID});

  // JSON 데이터로부터 VideoData 객체 생성하는 팩토리 메서드
  factory VideoData.fromJson(Map<String, dynamic> json) {
    return VideoData(channelID: json['channelID'] ?? '');  // 채널 ID (없으면 빈 문자열)
  }
}