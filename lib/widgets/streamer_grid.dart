import 'package:flutter/material.dart';
import '../models/streamer_data.dart';
import 'profile_image_widget.dart';

class StreamerGrid extends StatelessWidget {
  final List<StreamerData> streamers; // 표시할 스트리머 목록
  final Map<String, Set<String>> selectedStreamers; // 선택된 스트리머 정보
  final Function(StreamerData) onStreamerTap; // 스트리머 선택 시 콜백
  final Map<String, Set<String>> selectedVideoDataUsers; // VOD 알림 설정
  final Map<String, Set<String>> selectedYoutubeUsers; // 유튜브 알림 설정
  final Map<String, Set<String>> selectedCafeUsers; // 카페 알림 설정
  final Map<String, Set<String>> selectedChzzkChatUsers; // 치지직 채팅 필터
  final Map<String, Set<String>> selectedAfreecaChatUsers; // 아프리카 채팅 필터

  // UI 관련 상수 정의
  static const double _borderWidth = 1.0;
  static const double _selectedBorderWidth = 2.0;
  static const double _borderRadius = 8.0;
  static const double _itemSpacing = 10.0;
  static const double _textVerticalSpacing = 8.0;
  static const double _selectionIndicatorSize = 12.0;
  static const int _gridColumns = 3;
  static const double _childAspectRatio = 0.75;

  // 플랫폼 이름 매핑 (코드->표시명)
  static const Map<String, String> _platformNames = {
    'afreeca': '아프리카TV',
    'chzzk': '치지직',
  };

  const StreamerGrid({
    super.key,
    required this.streamers,
    required this.selectedStreamers,
    required this.onStreamerTap,
    this.selectedVideoDataUsers = const {},
    this.selectedYoutubeUsers = const {},
    this.selectedCafeUsers = const {},
    this.selectedChzzkChatUsers = const {},
    this.selectedAfreecaChatUsers = const {},
  });

  @override
  Widget build(BuildContext context) {
    // 고정된 그리드 레이아웃 구성
    return GridView.builder(
      shrinkWrap: true, // 부모 위젯의 높이에 맞춤
      physics: const NeverScrollableScrollPhysics(), // 스크롤 비활성화
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: _gridColumns, // 한 행에 표시할 아이템 수
        childAspectRatio: _childAspectRatio, // 아이템 가로/세로 비율
        crossAxisSpacing: _itemSpacing, // 가로 간격
        mainAxisSpacing: _itemSpacing, // 세로 간격
      ),
      itemCount: streamers.length, // 아이템 수
      itemBuilder: (context, index) {
        final streamer = streamers[index];

        // 성능 최적화: 선택 검사 로직 (모든 설정 포함)
        final isSelected = _isStreamerSelected(streamer);

        // 개별 스트리머 아이템 구성
        return _buildStreamerItem(context, streamer, isSelected);
      },
    );
  }

  // 스트리머 선택 여부 확인하는 메서드 (모든 설정 포함)
  bool _isStreamerSelected(StreamerData streamer) {
    // 1. 기본 알림 설정 확인 (뱅온, 방제 변경, 방종, 하이라이트, 핫클립)
    bool hasBasicNotification = selectedStreamers.values.any(
      (set) => set.contains(streamer.name),
    );

    if (hasBasicNotification) {
      return true;
    }

    final channelID = streamer.channelID;

    // 2. VOD 알림 설정 확인
    if (selectedVideoDataUsers.containsKey(channelID) &&
        selectedVideoDataUsers[channelID]!.isNotEmpty) {
      return true;
    }

    // 3. 유튜브 알림 설정 확인
    if (selectedYoutubeUsers.containsKey(channelID) &&
        selectedYoutubeUsers[channelID]!.isNotEmpty) {
      return true;
    }

    // 4. 카페 알림 설정 확인
    if (selectedCafeUsers.containsKey(channelID) &&
        selectedCafeUsers[channelID]!.isNotEmpty) {
      return true;
    }

    // 5. 치지직 채팅 필터 설정 확인
    if (selectedChzzkChatUsers.containsKey(channelID) &&
        selectedChzzkChatUsers[channelID]!.isNotEmpty) {
      return true;
    }

    // 6. 아프리카 채팅 필터 설정 확인
    if (selectedAfreecaChatUsers.containsKey(channelID) &&
        selectedAfreecaChatUsers[channelID]!.isNotEmpty) {
      return true;
    }

    return false;
  }

  // 스트리머 아이템 UI 생성하는 메서드
  Widget _buildStreamerItem(
    BuildContext context,
    StreamerData streamer,
    bool isSelected,
  ) {
    return GestureDetector(
      onTap: () => onStreamerTap(streamer),
      child: Container(
        decoration: BoxDecoration(
          border: Border.all(
            color:
                isSelected
                    ? Theme.of(context).primaryColor
                    : Colors.grey.shade300,
            width: isSelected ? _selectedBorderWidth : _borderWidth,
          ),
          borderRadius: BorderRadius.circular(_borderRadius),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ProfileImageWidget(
              url: streamer.profileImageUrl,
              isSelected: isSelected,
            ),
            SizedBox(height: _textVerticalSpacing),
            Text(
              streamer.name,
              textAlign: TextAlign.center,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
              ),
            ),
            Text(
              _getPlatformName(streamer.platform),
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
            if (isSelected)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Container(
                  width: _selectionIndicatorSize,
                  height: _selectionIndicatorSize,
                  decoration: BoxDecoration(
                    color: Theme.of(context).primaryColor,
                    shape: BoxShape.circle,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  // 플랫폼 코드를 표시명으로 변환하는 메서드
  String _getPlatformName(String platform) {
    return _platformNames[platform.toLowerCase()] ?? platform;
  }
}
