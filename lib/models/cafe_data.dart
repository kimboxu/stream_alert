import '../utils/json_helpers.dart';

// 카페 데이터를 관리하는 클래스
// 채널 ID, 채널명, 카페 이름 딕셔너리을 포함
class CafeData {
  final String channelID;     // 채널 고유 ID
  final String channelName;   // 채널 이름
  final Map<String, List<String>> cafeNameDict;  // 카페 이름과 관련 데이터를 매핑한 딕셔너리

  // 생성자
  CafeData({
    required this.channelID,
    required this.channelName,
    required this.cafeNameDict,
  });

  // JSON 데이터로부터 CafeData 객체 생성하는 팩토리 메서드
  factory CafeData.fromJson(Map<String, dynamic> json) {
    return CafeData(
      channelID: json['channelID'] ?? '',  // 채널 ID (없으면 빈 문자열)
      channelName: json['channelName'] ?? '',  // 채널명 (없으면 빈 문자열)
      cafeNameDict: JsonHelper.parseStringListMap(json, 'cafeNameDict'),  // 카페 이름 딕셔너리 파싱
    );
  }
}