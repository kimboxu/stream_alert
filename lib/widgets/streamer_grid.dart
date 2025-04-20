import 'package:flutter/material.dart';
import '../models/streamer_data.dart';
import 'profile_image_widget.dart';

class StreamerGrid extends StatelessWidget {
  final List<StreamerData> streamers;
  final Map<String, Set<String>> selectedStreamers;
  final Function(StreamerData) onStreamerTap;
  
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
      physics: NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 3,
        childAspectRatio: 0.75,
        crossAxisSpacing: 10,
        mainAxisSpacing: 10,
      ),
      itemCount: streamers.length,
      itemBuilder: (context, index) {
        final streamer = streamers[index];
        
        // Check if this streamer is selected in at least one notification type
        bool isSelected = selectedStreamers.values.any(
          (set) => set.contains(streamer.name),
        );
        
        return GestureDetector(
          onTap: () => onStreamerTap(streamer),
          child: Container(
            decoration: BoxDecoration(
              border: Border.all(
                color:
                    isSelected
                        ? Theme.of(context).primaryColor
                        : Colors.grey.shade300,
                width: isSelected ? 2.0 : 1.0,
              ),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                ProfileImageWidget(
                  url: streamer.profileImageUrl,
                  isSelected: isSelected,
                ),
                SizedBox(height: 8),
                Text(
                  streamer.name,
                  textAlign: TextAlign.center,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontWeight:
                        isSelected ? FontWeight.bold : FontWeight.normal,
                  ),
                ),
                Text(
                  streamer.platform == 'afreeca' ? '아프리카TV' : '치지직',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
                if (isSelected)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Container(
                      width: 12,
                      height: 12,
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
      },
    );
  }
}