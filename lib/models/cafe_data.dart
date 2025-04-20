import '../utils/json_helpers.dart';

class CafeData {
  final String channelID;
  final String channelName;
  final Map<String, List<String>> cafeNameDict;

  CafeData({
    required this.channelID,
    required this.channelName,
    required this.cafeNameDict,
  });

  factory CafeData.fromJson(Map<String, dynamic> json) {
    return CafeData(
      channelID: json['channelID'] ?? '',
      channelName: json['channelName'] ?? '',
      cafeNameDict: JsonHelper.parseStringListMap(json, 'cafeNameDict'),
    );
  }
}