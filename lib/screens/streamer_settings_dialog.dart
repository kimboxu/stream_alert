// ignore_for_file: library_private_types_in_public_api

import 'package:flutter/material.dart';
import '../models/streamer_data.dart';
import '../models/cafe_data.dart';
import '../models/videoData.dart';
import '../models/youtube_data.dart';
import '../utils/string_helpers.dart';
import '../widgets/profile_image_widget.dart';
import '../widgets/settings_item.dart';

class StreamerSettingsDialog extends StatefulWidget {
  // 스트리머 기본 정보
  final StreamerData streamer;

  // 선택된 알림 설정
  final Map<String, bool> selectedSettings;
  final Function(Map<String, bool>) onSettingsChanged;

  // 부가 데이터 모델
  final CafeData? cafeData;
  final VideoData? videoData;
  final YoutubeData? youtubeData;

  // 선택된 사용자 목록
  final Set<String> selectedCafeUsers;
  final Set<String> selectedVideoDataUsers;
  final Set<String> selectedyoutubrUsers;
  final Set<String> selectedChzzkChatUsers;
  final Set<String> selectedAfreecaChatUsers;

  // 콜백 함수
  final Function(Set<String>) onCafeUsersChanged;
  final Function(Set<String>) onVideoDataUsersChanged;
  final Function(Set<String>) onyoutubrUsersChanged;
  final Function(Set<String>) onChzzkChatUsersChanged;
  final Function(Set<String>) onAfreecaChatUsersChanged;

  // 사용 가능한 채팅 사용자 목록
  final List<String> availableChzzkChatUsers;
  final List<String> availableAfreecaChatUsers;

  const StreamerSettingsDialog({
    super.key,
    required this.streamer,
    required this.selectedSettings,
    required this.onSettingsChanged,
    this.cafeData,
    this.videoData,
    this.youtubeData,
    required this.selectedCafeUsers,
    required this.selectedVideoDataUsers,
    required this.selectedyoutubrUsers,
    required this.selectedChzzkChatUsers,
    required this.selectedAfreecaChatUsers,
    required this.onCafeUsersChanged,
    required this.onVideoDataUsersChanged,
    required this.onyoutubrUsersChanged,
    required this.onChzzkChatUsersChanged,
    required this.onAfreecaChatUsersChanged,
    required this.availableChzzkChatUsers,
    required this.availableAfreecaChatUsers,
  });

  @override
  _StreamerSettingsDialogState createState() => _StreamerSettingsDialogState();
}

class _StreamerSettingsDialogState extends State<StreamerSettingsDialog> {
  // 설정 상태 변수
  late Map<String, bool> _settings;
  late Set<String> _selectedCafeUsers;
  late Set<String> _selectedVideoDataUsers;
  late Set<String> _selectedyoutubrUsers;
  late Set<String> _selectedChzzkChatUsers;
  late Set<String> _selectedAfreecaChatUsers;

  // 검색 관련 컨트롤러
  final TextEditingController _cafeSearchController = TextEditingController();
  final TextEditingController _chzzkChatSearchController =
      TextEditingController();
  final TextEditingController _afreecaChatSearchController =
      TextEditingController();

  // 검색어
  String _cafeSearchQuery = '';
  String _chzzkChatSearchQuery = '';
  String _afreecaChatSearchQuery = '';

  // 패널 확장 상태 - 처음에는 알림 설정 패널만 열어둠
  bool _isNotificationPanelExpanded = true;
  bool _isvodAlarmPanelExpanded = false;
  bool _isYoutubePanelExpanded = false;
  bool _isCafePanelExpanded = false;
  bool _isChzzkChatPanelExpanded = false;
  bool _isAfreecaChatPanelExpanded = false;

  // 플랫폼 이름 매핑
  static const Map<String, String> _platformNames = {
    'afreeca': '아프리카TV',
    'chzzk': '치지직',
  };

  // 패널 최대 너비
  final double _maxPanelWidth = 400.0;

  // 각 패널의 아이콘 설정
  final Map<String, IconData> _panelIcons = {
    'notification': Icons.notifications_none,
    'vodAlarm': Icons.video_library_outlined,
    'youtube': Icons.play_circle_outline,
    'cafe': Icons.article_outlined,
    'chat': Icons.chat_bubble_outline,
  };

  @override
  void initState() {
    super.initState();
    // 전달받은 상태 복사
    _settings = Map.from(widget.selectedSettings);
    _selectedCafeUsers = Set.from(widget.selectedCafeUsers);
    _selectedVideoDataUsers = Set.from(widget.selectedVideoDataUsers);
    _selectedyoutubrUsers = Set.from(widget.selectedyoutubrUsers);
    _selectedChzzkChatUsers = Set.from(widget.selectedChzzkChatUsers);
    _selectedAfreecaChatUsers = Set.from(widget.selectedAfreecaChatUsers);
  }

  @override
  void dispose() {
    // 컨트롤러 정리
    _cafeSearchController.dispose();
    _chzzkChatSearchController.dispose();
    _afreecaChatSearchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Row(
        children: [
          // 스트리머 프로필 이미지
          CircleAvatar(
            radius: 20,
            child: ProfileImageWidget(
              url: widget.streamer.profileImageUrl,
              size: 40,
            ),
          ),
          SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(widget.streamer.name),
                Text(
                  _getPlatformName(widget.streamer.platform),
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
              ],
            ),
          ),
        ],
      ),
      content: SizedBox(
        width: _maxPanelWidth,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 알림 설정 패널
              buildExpandableNotificationSettings(),

              // VOD 알림 설정 패널
              if (widget.videoData != null &&
                  widget.videoData!.channelID.isNotEmpty)
                buildExpandableVideoDataSettings(),

              // 유튜브 알림 설정 패널
              if (widget.youtubeData != null &&
                  widget.youtubeData!.channelName.isNotEmpty)
                buildExpandableYoutubeSettings(),

              // 카페 설정 패널
              if (widget.cafeData != null &&
                  widget.cafeData!.channelName.isNotEmpty)
                buildExpandableCafeSettings(),

              // 채팅 필터 설정 패널
              buildExpandableChatFilterSettings(),
            ],
          ),
        ),
      ),
      actions: [
        // 취소 버튼
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text('취소'),
        ),
        // 저장 버튼
        TextButton(
          onPressed: () {
            // 설정된 값을 콜백으로 전달
            widget.onSettingsChanged(_settings);
            widget.onCafeUsersChanged(_selectedCafeUsers);
            widget.onVideoDataUsersChanged(_selectedVideoDataUsers);
            widget.onyoutubrUsersChanged(_selectedyoutubrUsers);

            // 채팅 필터 설정 저장 - 스트리머 이름 대신 채널 ID 사용
            if (widget.streamer.platform == 'chzzk') {
              widget.onChzzkChatUsersChanged(_selectedChzzkChatUsers);
            } else if (widget.streamer.platform == 'afreeca') {
              widget.onAfreecaChatUsersChanged(_selectedAfreecaChatUsers);
            }

            Navigator.of(context).pop();
          },
          child: Text('저장'),
        ),
      ],
    );
  }

  // 패널 타이틀 빌더
  Widget buildPanelTitle({
    required String title,
    required IconData icon,
    Widget? chip,
    Widget? subtitle,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 18.0, color: Theme.of(context).primaryColor),
            SizedBox(width: 8),
            Text(
              title,
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
            if (chip != null) SizedBox(width: 8),
            if (chip != null) chip,
          ],
        ),
        if (subtitle != null)
          Padding(padding: const EdgeInsets.only(top: 4.0), child: subtitle),
      ],
    );
  }

  // 카운트 표시 칩 빌더
  Widget buildCountChip(int count, String label) {
    return Chip(
      label: Text(
        '$count$label',
        style: TextStyle(fontSize: 10, color: Colors.white),
      ),
      backgroundColor: Theme.of(context).primaryColor,
      padding: EdgeInsets.zero,
      labelPadding: EdgeInsets.symmetric(horizontal: 4),
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
    );
  }

// 알림 설정 확장 패널
  Widget buildExpandableNotificationSettings() {
    // 선택된 알림 설정 개수 계산
    int selectedCount = _settings.entries.where((entry) => entry.value).length;

    return Card(
      margin: EdgeInsets.symmetric(vertical: 4.0),
      child: ExpansionTile(
        title: buildPanelTitle(
          title: '알림 설정',
          icon: _panelIcons['notification']!,
          chip:
              selectedCount > 0 ? buildCountChip(selectedCount, '개 선택됨') : null,
        ),
        initiallyExpanded: _isNotificationPanelExpanded,
        onExpansionChanged: (isExpanded) {
          setState(() {
            _isNotificationPanelExpanded = isExpanded;
          });
        },
        children:
            _settings.keys.map((key) {
              return SettingsCheckboxItem(
                title: StringHelper.getSettingDisplayName(key),
                value: _settings[key]!,
                onChanged: (value) {
                  setState(() {
                    _settings[key] = value ?? false;
                  });
                },
              );
            }).toList(),
      ),
    );
  }

// VOD 알림 설정 확장 패널
  Widget buildExpandableVideoDataSettings() {
    // 선택되었는지 확인
    final bool isSelected = _selectedVideoDataUsers.contains(
      widget.streamer.name,
    );

    return Card(
      margin: EdgeInsets.symmetric(vertical: 4.0),
      child: ExpansionTile(
        title: buildPanelTitle(
          title: 'VOD 알림',
          icon: _panelIcons['vodAlarm']!,
          chip: isSelected ? buildCountChip(1, '개 활성화됨') : null,
        ),
        initiallyExpanded: _isvodAlarmPanelExpanded,
        onExpansionChanged: (isExpanded) {
          setState(() {
            _isvodAlarmPanelExpanded = isExpanded;
          });
        },
        children: [
          if (widget.videoData == null || widget.videoData!.channelID.isEmpty)
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Text('이 스트리머는 VOD 알림 설정이 불가능합니다.'),
            )
          else
            CheckboxListTile(
              title: Text('${widget.streamer.name} 채널 VOD 알림'),
              value: _selectedVideoDataUsers.contains(widget.streamer.name),
              onChanged: (value) {
                setState(() {
                  if (value == true) {
                    _selectedVideoDataUsers.add(widget.streamer.name);
                  } else {
                    _selectedVideoDataUsers.remove(widget.streamer.name);
                  }
                });
              },
            ),
        ],
      ),
    );
  }

// 유튜브 알림 설정 확장 패널
  Widget buildExpandableYoutubeSettings() {
    // 선택된 유튜브 채널 개수 계산
    int selectedCount = 0;
    if (widget.youtubeData != null &&
        widget.youtubeData!.youtubeNameDict.isNotEmpty) {
      for (var entry in widget.youtubeData!.youtubeNameDict.entries) {
        for (var channelName in entry.value) {
          if (_selectedyoutubrUsers.contains(channelName)) {
            selectedCount++;
          }
        }
      }
    }

    return Card(
      margin: EdgeInsets.symmetric(vertical: 4.0),
      child: ExpansionTile(
        title: buildPanelTitle(
          title: '유튜브 알림',
          icon: _panelIcons['youtube']!,
          chip:
              selectedCount > 0 ? buildCountChip(selectedCount, '개 선택됨') : null,
        ),
        initiallyExpanded: _isYoutubePanelExpanded,
        onExpansionChanged: (isExpanded) {
          setState(() {
            _isYoutubePanelExpanded = isExpanded;
          });
        },
        children: [
          if (widget.youtubeData == null ||
              widget.youtubeData!.youtubeNameDict.isEmpty)
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Text('이 스트리머는 유튜브 알림 설정이 불가능합니다.'),
            )
          else
            ...widget.youtubeData!.youtubeNameDict.entries.expand((entry) {
              return entry.value.map((channelName) {
                bool isSelected = _selectedyoutubrUsers.contains(channelName);
                return CheckboxListTile(
                  title: Text(channelName),
                  value: isSelected,
                  onChanged: (value) {
                    setState(() {
                      if (value == true) {
                        _selectedyoutubrUsers.add(channelName);
                      } else {
                        _selectedyoutubrUsers.remove(channelName);
                      }
                    });
                  },
                );
              });
            }),
        ],
      ),
    );
  }

// 카페 설정 확장 패널
  Widget buildExpandableCafeSettings() {
    if (widget.cafeData == null || widget.cafeData!.cafeNameDict.isEmpty) {
      return Padding(
        padding: const EdgeInsets.only(top: 8.0, bottom: 8.0),
        child: Text('이 스트리머는 카페 알림 설정이 불가능합니다.'),
      );
    }

    final List<String> allCafeUsers =
        widget.cafeData!.cafeNameDict.keys.toList();
    final List<String> filteredCafeUsers =
        allCafeUsers
            .where(
              (user) =>
                  user.toLowerCase().contains(_cafeSearchQuery.toLowerCase()),
            )
            .toList();

    // 선택된 사용자 수
    final int selectedCount = _selectedCafeUsers.length;

    return Card(
      margin: EdgeInsets.symmetric(vertical: 4.0),
      child: ExpansionTile(
        title: buildPanelTitle(
          title: '카페 알림 설정',
          icon: _panelIcons['cafe']!,
          subtitle:
              selectedCount > 0
                  ? Text(
                    '선택된 사용자: $selectedCount명',
                    style: TextStyle(
                      fontSize: 12,
                      color: Theme.of(context).primaryColor,
                    ),
                  )
                  : null,
        ),
        initiallyExpanded: _isCafePanelExpanded,
        onExpansionChanged: (isExpanded) {
          setState(() {
            _isCafePanelExpanded = isExpanded;
          });
        },
        children: [
          buildSearchField(
            controller: _cafeSearchController,
            hintText: '카페 회원 검색...',
            searchQuery: _cafeSearchQuery,
            onChanged: (value) {
              setState(() {
                _cafeSearchQuery = value;
              });
            },
          ),

          // 모두 선택/해제 버튼
          buildSelectionButtons(
            onSelectAll: () {
              setState(() {
                _selectedCafeUsers.addAll(filteredCafeUsers);
              });
            },
            onDeselectAll: () {
              setState(() {
                _selectedCafeUsers.clear();
              });
            },
            areAllSelected:
                _selectedCafeUsers.isNotEmpty &&
                filteredCafeUsers.every(
                  (user) => _selectedCafeUsers.contains(user),
                ),
            areAllDeselected:
                _selectedCafeUsers.isEmpty ||
                filteredCafeUsers.every(
                  (user) => !_selectedCafeUsers.contains(user),
                ),
          ),

          // 사용자 목록
          buildScrollableUserList(
            users: filteredCafeUsers,
            selectedUsers: _selectedCafeUsers,
            onToggle: (userName, selected) {
              setState(() {
                if (selected) {
                  _selectedCafeUsers.add(userName);
                } else {
                  _selectedCafeUsers.remove(userName);
                }
              });
            },
          ),
        ],
      ),
    );
  }

// 채팅 필터 설정 확장 패널
  Widget buildExpandableChatFilterSettings() {
    final bool isChzzk = widget.streamer.platform == 'chzzk';
    final bool isAfreeca = widget.streamer.platform == 'afreeca';

    if (!isChzzk && !isAfreeca) return Container();

    // 선택된 사용자 수 계산
    int selectedCount = 0;
    List<String> availableUsers = [];
    Set<String> selectedUsers = {};
    TextEditingController searchController = TextEditingController();
    String searchQuery = '';

    if (isChzzk) {
      selectedCount = _selectedChzzkChatUsers.length;
      availableUsers = widget.availableChzzkChatUsers;
      selectedUsers = _selectedChzzkChatUsers;
      searchController = _chzzkChatSearchController;
      searchQuery = _chzzkChatSearchQuery;
    } else if (isAfreeca) {
      selectedCount = _selectedAfreecaChatUsers.length;
      availableUsers = widget.availableAfreecaChatUsers;
      selectedUsers = _selectedAfreecaChatUsers;
      searchController = _afreecaChatSearchController;
      searchQuery = _afreecaChatSearchQuery;
    }

    // 검색어로 필터링된 사용자 목록
    final List<String> filteredUsers =
        availableUsers
            .where(
              (user) => user.toLowerCase().contains(searchQuery.toLowerCase()),
            )
            .toList();

    return Card(
      margin: EdgeInsets.symmetric(vertical: 4.0),
      child: ExpansionTile(
        title: buildPanelTitle(
          title: '채팅 필터',
          icon: _panelIcons['chat']!,
          subtitle:
              selectedCount > 0
                  ? Text(
                    '선택된 사용자: $selectedCount명',
                    style: TextStyle(
                      fontSize: 12,
                      color: Theme.of(context).primaryColor,
                    ),
                  )
                  : null,
        ),
        initiallyExpanded:
            isChzzk ? _isChzzkChatPanelExpanded : _isAfreecaChatPanelExpanded,
        onExpansionChanged: (isExpanded) {
          setState(() {
            if (isChzzk) {
              _isChzzkChatPanelExpanded = isExpanded;
            } else if (isAfreeca) {
              _isAfreecaChatPanelExpanded = isExpanded;
            }
          });
        },
        children: [
          // 검색 필드
          buildSearchField(
            controller: searchController,
            hintText: '사용자 검색...',
            searchQuery: searchQuery,
            onChanged: (value) {
              setState(() {
                if (isChzzk) {
                  _chzzkChatSearchQuery = value;
                } else {
                  _afreecaChatSearchQuery = value;
                }
              });
            },
          ),

          // 모두 선택/해제 버튼
          buildSelectionButtons(
            onSelectAll: () {
              setState(() {
                selectedUsers.addAll(filteredUsers);
              });
            },
            onDeselectAll: () {
              setState(() {
                selectedUsers.clear();
              });
            },
            areAllSelected:
                selectedUsers.isNotEmpty &&
                filteredUsers.every((user) => selectedUsers.contains(user)),
            areAllDeselected:
                selectedUsers.isEmpty ||
                filteredUsers.every((user) => !selectedUsers.contains(user)),
          ),

          // 사용자 목록
          buildScrollableUserList(
            users: filteredUsers,
            selectedUsers: selectedUsers,
            onToggle: (userName, selected) {
              setState(() {
                if (selected) {
                  selectedUsers.add(userName);
                } else {
                  selectedUsers.remove(userName);
                }
              });
            },
          ),
        ],
      ),
    );
  }

  // 검색 필드 위젯
  Widget buildSearchField({
    required TextEditingController controller,
    required String hintText,
    required String searchQuery,
    required Function(String) onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8.0),
      child: TextField(
        controller: controller,
        style: TextStyle(fontSize: 14.0),
        decoration: InputDecoration(
          hintText: hintText,
          hintStyle: TextStyle(fontSize: 14.0),
          prefixIcon: Icon(Icons.search, size: 18.0),
          suffixIcon:
              searchQuery.isNotEmpty
                  ? IconButton(
                    icon: Icon(Icons.clear, size: 18.0),
                    onPressed: () {
                      controller.clear();
                      onChanged('');
                    },
                    padding: EdgeInsets.zero,
                    constraints: BoxConstraints(minWidth: 32, minHeight: 32),
                  )
                  : null,
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(8.0)),
          contentPadding: EdgeInsets.symmetric(vertical: 8.0, horizontal: 12.0),
          isDense: true,
        ),
        onChanged: onChanged,
      ),
    );
  }

  // 선택 버튼 위젯
  Widget buildSelectionButtons({
    required VoidCallback onSelectAll,
    required VoidCallback onDeselectAll,
    required bool areAllSelected,
    required bool areAllDeselected,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8.0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          TextButton.icon(
            icon: Icon(
              areAllDeselected
                  ? Icons.check_box
                  : Icons.check_box_outline_blank,
              color: areAllDeselected ? Theme.of(context).primaryColor : null,
            ),
            label: Text('모두 해제'),
            onPressed: onDeselectAll,
            style: TextButton.styleFrom(
              padding: EdgeInsets.symmetric(horizontal: 8.0, vertical: 4.0),
            ),
          ),
          TextButton.icon(
            icon: Icon(
              areAllSelected ? Icons.check_box : Icons.check_box_outline_blank,
              color: areAllSelected ? Theme.of(context).primaryColor : null,
            ),
            label: Text('모두 선택'),
            onPressed: onSelectAll,
            style: TextButton.styleFrom(
              padding: EdgeInsets.symmetric(horizontal: 8.0, vertical: 4.0),
            ),
          ),
        ],
      ),
    );
  }

  // 스크롤 가능한 사용자 목록 위젯
  Widget buildScrollableUserList({
    required List<String> users,
    required Set<String> selectedUsers,
    required Function(String, bool) onToggle,
  }) {
    return Container(
      constraints: BoxConstraints(maxHeight: 200),
      child: Scrollbar(
        child: SingleChildScrollView(
          child:
              users.isNotEmpty
                  ? Column(
                    mainAxisSize: MainAxisSize.min,
                    children:
                        users.map((user) {
                          final bool isSelected = selectedUsers.contains(user);
                          return CheckboxListTile(
                            title: Text(user),
                            value: isSelected,
                            onChanged:
                                (selected) => onToggle(user, selected ?? false),
                            dense: true,
                            contentPadding: EdgeInsets.symmetric(
                              horizontal: 8.0,
                            ),
                            controlAffinity: ListTileControlAffinity.leading,
                            visualDensity: VisualDensity(
                              horizontal: -2,
                              vertical: -2,
                            ),
                          );
                        }).toList(),
                  )
                  : Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Text('검색 결과가 없습니다.'),
                  ),
        ),
      ),
    );
  }

  // 플랫폼 이름 가져오는 메서드
  String _getPlatformName(String platform) {
    return _platformNames[platform.toLowerCase()] ?? platform;
  }
}
