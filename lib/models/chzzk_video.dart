class ChzzkVideo {
  final String channelID;

  ChzzkVideo({required this.channelID});

  factory ChzzkVideo.fromJson(Map<String, dynamic> json) {
    return ChzzkVideo(channelID: json['channelID'] ?? '');
  }
}