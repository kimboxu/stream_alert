import 'package:flutter/material.dart';
import '../models/streamer_data.dart';
import '../models/cafe_data.dart';
import '../models/chzzk_video.dart';
import '../models/youtube_data.dart';
import '../utils/string_helpers.dart';
import '../widgets/profile_image_widget.dart';
import '../widgets/settings_item.dart';

class StreamerSettingsDialog extends StatefulWidget {
  final StreamerData streamer;
  final Map<String, bool> selectedSettings;
  final Function(Map<String, bool>) onSettingsChanged;
  final CafeData? cafeData;
  final ChzzkVideo? chzzkVideo;
  final YoutubeData? youtubeData;
  final Set<String> selectedCafeUsers;
  final Set<String> selectedChzzkVideoUsers;
  final Set<String> selectedyoutubrUsers;
  final Set<String> selectedChzzkChatUsers;
  final Set<String> selectedAfreecaChatUsers;
  final Function(Set<String>) onCafeUsersChanged;
  final Function(Set<String>) onChzzkVideoUsersChanged;
  final Function(Set<String>) onyoutubrUsersChanged;
  final Function(Set<String>) onChzzkChatUsersChanged;
  final Function(Set<String>) onAfreecaChatUsersChanged;
  final List<String> availableChzzkChatUsers;
  final List<String> availableAfreecaChatUsers;

  const StreamerSettingsDialog({
    super.key,
    required this.streamer,
    required this.selectedSettings,
    required this.onSettingsChanged,
    this.cafeData,
    this.chzzkVideo,
    this.youtubeData,
    required this.selectedCafeUsers,
    required this.selectedChzzkVideoUsers,
    required this.selectedyoutubrUsers,
    required this.selectedChzzkChatUsers,
    required this.selectedAfreecaChatUsers,
    required this.onCafeUsersChanged,
    required this.onChzzkVideoUsersChanged,
    required this.onyoutubrUsersChanged,
    required this.onChzzkChatUsersChanged,
    required this.onAfreecaChatUsersChanged,
    required this.availableChzzkChatUsers,
    required this.availableAfreecaChatUsers,
  });

  @override
  // ignore: library_private_types_in_public_api
  _StreamerSettingsDialogState createState() => _StreamerSettingsDialogState();
}

class _StreamerSettingsDialogState extends State<StreamerSettingsDialog> {
  late Map<String, bool> _settings;
  late Set<String> _selectedCafeUsers;
  late Set<String> _selectedChzzkVideoUsers;
  late Set<String> _selectedyoutubrUsers;
  late Set<String> _selectedChzzkChatUsers;
  late Set<String> _selectedAfreecaChatUsers;

  // 검색 관련 컨트롤러들
  final TextEditingController _cafeSearchController = TextEditingController();
  final TextEditingController _chzzkChatSearchController =
      TextEditingController();
  final TextEditingController _afreecaChatSearchController =
      TextEditingController();

  // 검색어
  String _cafeSearchQuery = '';
  String _chzzkChatSearchQuery = '';
  String _afreecaChatSearchQuery = '';

  // 패널 확장 상태
  bool _isCafePanelExpanded = false;
  bool _isChzzkChatPanelExpanded = false;
  bool _isAfreecaChatPanelExpanded = false;

  @override
  void initState() {
    super.initState();
    _settings = Map.from(widget.selectedSettings);
    _selectedCafeUsers = Set.from(widget.selectedCafeUsers);
    _selectedChzzkVideoUsers = Set.from(widget.selectedChzzkVideoUsers);
    _selectedyoutubrUsers = Set.from(widget.selectedyoutubrUsers);
    _selectedChzzkChatUsers = Set.from(widget.selectedChzzkChatUsers);
    _selectedAfreecaChatUsers = Set.from(widget.selectedAfreecaChatUsers);
  }

  @override
  void dispose() {
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
                  widget.streamer.platform == 'afreeca' ? '아프리카TV' : '치지직',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
              ],
            ),
          ),
        ],
      ),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Notification settings
            ...buildNotificationSettings(),

            // Chzzk Video settings
            if (widget.chzzkVideo != null &&
                widget.chzzkVideo!.channelID.isNotEmpty)
              buildChzzkVideoSettings(),

            // YouTube settings
            if (widget.youtubeData != null &&
                widget.youtubeData!.channelName.isNotEmpty)
              buildYoutubeSettings(),

            // Cafe settings
            if (widget.cafeData != null &&
                widget.cafeData!.channelName.isNotEmpty)
              buildExpandableCafeSettings(),

            // Chat filter settings
            buildExpandableChatFilterSettings(),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text('취소'),
        ),
        TextButton(
          onPressed: () {
            widget.onSettingsChanged(_settings);
            widget.onCafeUsersChanged(_selectedCafeUsers);
            widget.onChzzkVideoUsersChanged(_selectedChzzkVideoUsers);
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

  List<Widget> buildNotificationSettings() {
    return [
      Padding(
        padding: const EdgeInsets.only(bottom: 8.0),
        child: Text(
          '알림 설정',
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
        ),
      ),
      ..._settings.keys.map((key) {
        return SettingsCheckboxItem(
          title: StringHelper.getSettingDisplayName(key),
          value: _settings[key]!,
          onChanged: (value) {
            setState(() {
              _settings[key] = value ?? false;
            });
          },
        );
      }),
      Divider(),
    ];
  }

  Widget buildExpandableChatFilterSettings() {
    final bool isChzzk = widget.streamer.platform == 'chzzk';
    final bool isAfreeca = widget.streamer.platform == 'afreeca';

    // If neither platform is applicable, return empty container
    if (!isChzzk && !isAfreeca) return Container();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 8.0, bottom: 8.0),
          child: Text(
            '채팅 필터 설정',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
        ),
        if (isChzzk)
          buildExpandableUsersList(
            "치지직 채팅 필터",
            widget.availableChzzkChatUsers,
            _selectedChzzkChatUsers,
            (userName, selected) {
              setState(() {
                if (selected) {
                  _selectedChzzkChatUsers.add(userName);
                } else {
                  _selectedChzzkChatUsers.remove(userName);
                }
              });
            },
            _chzzkChatSearchController,
            _chzzkChatSearchQuery,
            (query) => setState(() => _chzzkChatSearchQuery = query),
            _isChzzkChatPanelExpanded,
            (isExpanded) =>
                setState(() => _isChzzkChatPanelExpanded = isExpanded),
          ),
        if (isAfreeca)
          buildExpandableUsersList(
            "아프리카 채팅 필터",
            widget.availableAfreecaChatUsers,
            _selectedAfreecaChatUsers,
            (userName, selected) {
              setState(() {
                if (selected) {
                  _selectedAfreecaChatUsers.add(userName);
                } else {
                  _selectedAfreecaChatUsers.remove(userName);
                }
              });
            },
            _afreecaChatSearchController,
            _afreecaChatSearchQuery,
            (query) => setState(() => _afreecaChatSearchQuery = query),
            _isAfreecaChatPanelExpanded,
            (isExpanded) =>
                setState(() => _isAfreecaChatPanelExpanded = isExpanded),
          ),
        Divider(),
      ],
    );
  }

  // buildExpandableUsersList 함수 수정
  Widget buildExpandableUsersList(
    String title,
    List<String> allUsers,
    Set<String> selectedUsers,
    Function(String, bool) onToggle,
    TextEditingController searchController,
    String searchQuery,
    Function(String) onSearchChanged,
    bool isExpanded,
    Function(bool) onExpansionChanged,
  ) {
    if (allUsers.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 8.0, horizontal: 16.0),
        child: Text('이용 가능한 사용자가 없습니다.'),
      );
    }

    // 검색어로 필터링된 사용자 목록
    final List<String> filteredUsers =
        allUsers
            .where(
              (user) => user.toLowerCase().contains(searchQuery.toLowerCase()),
            )
            .toList();

    // 선택된 사용자 수와 필터링된 전체 사용자 수
    final int selectedCount = selectedUsers.length;
    final int totalFilteredCount = filteredUsers.length;
    
    // 모든 항목이 선택되었는지 확인
    final bool areAllSelected = selectedCount >= totalFilteredCount && 
        filteredUsers.every((user) => selectedUsers.contains(user));
    
    // 모든 항목이 선택 해제되었는지 확인
    final bool areAllDeselected = selectedUsers.isEmpty || 
        filteredUsers.every((user) => !selectedUsers.contains(user));

    return Card(
      margin: EdgeInsets.symmetric(vertical: 4.0),
      child: ExpansionTile(
        title: Row(
          children: [
            Text(title, style: TextStyle(fontSize: 14.0)),
            SizedBox(width: 4),
            if (selectedCount > 0)
              Chip(
                label: Text(
                  '$selectedCount명 선택',
                  style: TextStyle(fontSize: 10, color: Colors.white),
                ),
                backgroundColor: Theme.of(context).primaryColor,
                padding: EdgeInsets.zero,
                labelPadding: EdgeInsets.symmetric(horizontal: 4),
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
          ],
        ),
        tilePadding: EdgeInsets.symmetric(
          horizontal: 12.0,
          vertical: 2.0,
        ), // 타일 패딩 축소
        childrenPadding: EdgeInsets.only(bottom: 8.0), // 자식 위젯 패딩 축소
        initiallyExpanded: isExpanded,
        onExpansionChanged: onExpansionChanged,
        children: [
          // 검색 필드
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: 12.0,
              vertical: 8.0,
            ), // 패딩 축소
            child: TextField(
              controller: searchController,
              style: TextStyle(fontSize: 14.0), // 폰트 크기 줄임
              decoration: InputDecoration(
                hintText: '사용자 검색...',
                hintStyle: TextStyle(fontSize: 14.0), // 힌트 텍스트 크기 줄임
                prefixIcon: Icon(Icons.search, size: 18.0), // 아이콘 크기 줄임
                suffixIcon:
                    searchQuery.isNotEmpty
                        ? IconButton(
                          icon: Icon(Icons.clear, size: 18.0), // 아이콘 크기 줄임
                          onPressed: () {
                            searchController.clear();
                            onSearchChanged('');
                          },
                          padding: EdgeInsets.zero, // 패딩 제거
                          constraints: BoxConstraints(
                            minWidth: 32,
                            minHeight: 32,
                          ), // 아이콘 버튼 크기 제한
                        )
                        : null,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8.0), // 모서리 살짝 둥글게
                ),
                contentPadding: EdgeInsets.symmetric(
                  vertical: 4.0,
                  horizontal: 8.0,
                ), // 내부 패딩 축소
                isDense: true, // 밀집된 레이아웃 사용
              ),
              onChanged: onSearchChanged,
            ),
          ),

          // 모두 선택/해제 버튼
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                TextButton.icon(
                  icon: Icon(
                    areAllDeselected ? Icons.check_box : Icons.check_box_outline_blank, 
                    color: areAllDeselected ? Theme.of(context).primaryColor : null,
                  ),
                  label: Text('모두 해제'),
                  onPressed: () {
                    setState(() {
                      selectedUsers.clear();
                    });
                  },
                ),
                TextButton.icon(
                  icon: Icon(
                    areAllSelected ? Icons.check_box : Icons.check_box_outline_blank,
                    color: areAllSelected ? Theme.of(context).primaryColor : null,
                  ),
                  label: Text('모두 선택'),
                  onPressed: () {
                    setState(() {
                      selectedUsers.addAll(filteredUsers);
                    });
                  },
                ),
              ],
            ),
          ),

          // 사용자 목록을 Column으로 변경
          Container(
            constraints: BoxConstraints(
              maxHeight: 200, // 최대 높이 제한
            ),
            child: Scrollbar(
              child: SingleChildScrollView(
                child:
                    filteredUsers.isNotEmpty
                        ? Column(
                          mainAxisSize: MainAxisSize.min,
                          children:
                              filteredUsers.map((user) {
                                final bool isSelected = selectedUsers.contains(
                                  user,
                                );
                                return CheckboxListTile(
                                  title: Text(user),
                                  value: isSelected,
                                  onChanged:
                                      (selected) =>
                                          onToggle(user, selected ?? false),
                                  dense: true,
                                  contentPadding: EdgeInsets.symmetric(
                                    horizontal: 8.0,
                                  ),
                                  controlAffinity:
                                      ListTileControlAffinity
                                          .leading, // 체크박스를 왼쪽에 배치
                                  visualDensity: VisualDensity(
                                    horizontal: -4,
                                    vertical: -4,
                                  ), // 시각적 밀도 축소
                                );
                              }).toList(),
                        )
                        : Padding(
                          padding: const EdgeInsets.all(16.0),
                          child: Text('검색 결과가 없습니다.'),
                        ),
              ),
            ),
          ),
        ],
      ),
    );
  }

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
            
    // 모든 항목이 선택되었는지 확인
    final bool areAllSelected = _selectedCafeUsers.isNotEmpty && 
        filteredCafeUsers.every((user) => _selectedCafeUsers.contains(user));
    
    // 모든 항목이 선택 해제되었는지 확인
    final bool areAllDeselected = _selectedCafeUsers.isEmpty || 
        filteredCafeUsers.every((user) => !_selectedCafeUsers.contains(user));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 8.0, bottom: 8.0),
          child: Text(
            '카페 알림 설정',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
        ),
        Card(
          margin: EdgeInsets.symmetric(vertical: 4.0),
          child: ExpansionTile(
            title: Row(
              children: [
                Text('카페 회원 알림', style: TextStyle(fontSize: 14.0)),
                SizedBox(width: 4),
                if (_selectedCafeUsers.isNotEmpty)
                  Chip(
                    label: Text(
                      '${_selectedCafeUsers.length}명 선택',
                      style: TextStyle(fontSize: 12, color: Colors.white),
                    ),
                    backgroundColor: Theme.of(context).primaryColor,
                    padding: EdgeInsets.zero,
                    labelPadding: EdgeInsets.symmetric(horizontal: 4),
                    materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
              ],
            ),
            tilePadding: EdgeInsets.symmetric(
              horizontal: 12.0,
              vertical: 2.0,
            ), // 타일 패딩 축소
            childrenPadding: EdgeInsets.only(bottom: 8.0), // 자식 위젯 패딩 축소
            initiallyExpanded: _isCafePanelExpanded,
            onExpansionChanged: (isExpanded) {
              setState(() {
                _isCafePanelExpanded = isExpanded;
              });
            },
            children: [
              // 검색 필드
              Padding(
                padding: const EdgeInsets.all(8.0),
                child: TextField(
                  controller: _cafeSearchController,
                  decoration: InputDecoration(
                    hintText: '카페 회원 검색...',
                    prefixIcon: Icon(Icons.search),
                    suffixIcon:
                        _cafeSearchQuery.isNotEmpty
                            ? IconButton(
                              icon: Icon(Icons.clear),
                              onPressed: () {
                                _cafeSearchController.clear();
                                setState(() {
                                  _cafeSearchQuery = '';
                                });
                              },
                            )
                            : null,
                    border: OutlineInputBorder(),
                    contentPadding: EdgeInsets.symmetric(
                      vertical: 8.0,
                      horizontal: 12.0,
                    ),
                  ),
                  onChanged: (value) {
                    setState(() {
                      _cafeSearchQuery = value;
                    });
                  },
                ),
              ),

              // 모두 선택/해제 버튼
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8.0),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    TextButton.icon(
                      icon: Icon(
                        areAllDeselected ? Icons.check_box : Icons.check_box_outline_blank,
                        color: areAllDeselected ? Theme.of(context).primaryColor : null,
                      ),
                      label: Text('모두 해제'),
                      onPressed: () {
                        setState(() {
                          _selectedCafeUsers.clear();
                        });
                      },
                    ),
                    TextButton.icon(
                      icon: Icon(
                        areAllSelected ? Icons.check_box : Icons.check_box_outline_blank,
                        color: areAllSelected ? Theme.of(context).primaryColor : null,
                      ),
                      label: Text('모두 선택'),
                      onPressed: () {
                        setState(() {
                          _selectedCafeUsers.addAll(filteredCafeUsers);
                        });
                      },
                    ),
                  ],
                ),
              ),

              // 사용자 목록
              Container(
                constraints: BoxConstraints(
                  maxHeight: 200, // 최대 높이 제한
                ),
                child: Scrollbar(
                  child: SingleChildScrollView(
                    child:
                        filteredCafeUsers.isNotEmpty
                            ? Column(
                              mainAxisSize: MainAxisSize.min,
                              children:
                                  filteredCafeUsers.map((user) {
                                    final bool isSelected = _selectedCafeUsers
                                        .contains(user);
                                    return CheckboxListTile(
                                      title: Text(user),
                                      value: isSelected,
                                      onChanged: (selected) {
                                        setState(() {
                                          if (selected ?? false) {
                                            _selectedCafeUsers.add(user);
                                          } else {
                                            _selectedCafeUsers.remove(user);
                                          }
                                        });
                                      },
                                      dense: true,
                                      contentPadding: EdgeInsets.symmetric(
                                        horizontal: 16.0,
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
              ),
            ],
          ),
        ),
        Divider(),
      ],
    );
  }

  Widget buildChzzkVideoSettings() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 8.0, bottom: 8.0),
          child: Text(
            '치지직 VOD',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
        ),
        if (widget.chzzkVideo == null || widget.chzzkVideo!.channelID.isEmpty)
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Text('이 스트리머는 치지직 VOD 알림 설정이 불가능합니다.'),
          )
        else
          CheckboxListTile(
            title: Text('${widget.streamer.name} 채널 VOD 알림'),
            value: _selectedChzzkVideoUsers.contains(widget.streamer.name),
            onChanged: (value) {
              setState(() {
                if (value == true) {
                  _selectedChzzkVideoUsers.add(widget.streamer.name);
                } else {
                  _selectedChzzkVideoUsers.remove(widget.streamer.name);
                }
              });
            },
          ),
        Divider(),
      ],
    );
  }

  Widget buildYoutubeSettings() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 8.0, bottom: 8.0),
          child: Text(
            '유튜브 알림',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
        ),
        if (widget.youtubeData == null ||
            widget.youtubeData!.youtubeNameDict.isEmpty)
          Padding(
            padding: const EdgeInsets.all(8.0),
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
        Divider(),
      ],
    );
  }
}