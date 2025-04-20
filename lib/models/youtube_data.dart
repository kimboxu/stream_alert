class YoutubeData {
  final String channelID;
  final String channelName;
  final Map<String, List<String>> youtubeNameDict;

  YoutubeData({
    required this.channelID,
    required this.channelName,
    required this.youtubeNameDict,
  });

  factory YoutubeData.fromJson(Map<String, dynamic> json) {
    Map<String, List<String>> youtubeDict = {};

    String channelID = json['channelID'] ?? '';
    String channelName = json['channelName'] ?? '';

    if (channelID.isNotEmpty && channelName.isNotEmpty) {
      youtubeDict[channelName] = [channelID];
    }

    return YoutubeData(
      channelID: channelID,
      channelName: json['channelName'] ?? '',
      youtubeNameDict: youtubeDict,
    );
  }
}