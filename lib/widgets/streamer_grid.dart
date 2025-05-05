import 'package:flutter/material.dart';
import '../models/streamer_data.dart';
import 'profile_image_widget.dart';

class StreamerGrid extends StatelessWidget {
  final List<StreamerData> streamers;
  final Map<String, Set<String>> selectedStreamers;
  final Function(StreamerData) onStreamerTap;

  // UI 관련 상수 정의
  static const double _borderWidth = 1.0;
  static const double _selectedBorderWidth = 2.0;
  static const double _borderRadius = 8.0;
  static const double _itemSpacing = 10.0;
  static const double _textVerticalSpacing = 8.0;
  static const double _selectionIndicatorSize = 12.0;
  static const int _gridColumns = 3;
  static const double _childAspectRatio = 0.75;

  // 플랫폼 이름 매핑
  static const Map<String, String> _platformNames = {
    'afreeca': '아프리카TV',
    'chzzk': '치지직',
  };

  const StreamerGrid({
    super.key,
    required this.streamers,
    required this.selectedStreamers,
    required this.onStreamerTap,
  });

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: _gridColumns,
        childAspectRatio: _childAspectRatio,
        crossAxisSpacing: _itemSpacing,
        mainAxisSpacing: _itemSpacing,
      ),
      itemCount: streamers.length,
      itemBuilder: (context, index) {
        final streamer = streamers[index];

        // 성능 최적화: 선택 검사 로직 개선
        final isSelected = _isStreamerSelected(streamer.name);

        return _buildStreamerItem(context, streamer, isSelected);
      },
    );
  }

  // 스트리머 선택 여부 확인하는 메서드
  bool _isStreamerSelected(String streamerName) {
    return selectedStreamers.values.any((set) => set.contains(streamerName));
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

  // 플랫폼 이름 가져오는 메서드
  String _getPlatformName(String platform) {
    return _platformNames[platform.toLowerCase()] ?? platform;
  }
}
