// 유튜브 채널 데이터를 관리하는 클래스
class YoutubeData {
  final String channelID;                        // 유튜브 채널 ID
  final String channelName;                      // 유튜브 채널명 
  final Map<String, List<String>> youtubeNameDict;  // 채널명과 채널 ID를 매핑한 딕셔너리

  // 생성자
  YoutubeData({
    required this.channelID,
    required this.channelName,
    required this.youtubeNameDict,
  });

  // JSON 데이터로부터 YoutubeData 객체 생성하는 팩토리 메서드
  factory YoutubeData.fromJson(Map<String, dynamic> json) {
    Map<String, List<String>> youtubeDict = {};

    String channelID = json['channelID'] ?? '';
    String channelName = json['channelName'] ?? '';

    // 유효한 채널 정보가 있으면 딕셔너리에 추가
    if (channelID.isNotEmpty && channelName.isNotEmpty) {
      youtubeDict[channelName] = [channelID];
    }

    return YoutubeData(
      channelID: channelID,
      channelName: json['channelName'] ?? '',  // 채널명 (없으면 빈 문자열)
      youtubeNameDict: youtubeDict,  // 생성한 딕셔너리
    );
  }
}