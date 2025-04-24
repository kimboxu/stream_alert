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
  bool _isNotificationPanelExpanded = true; // 처음에는 알림 설정 패널만 열어둠
  bool _isChzzkVodPanelExpanded = false;
  bool _isYoutubePanelExpanded = false;
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
            // 알림 설정 (ExpansionTile로 변경)
            buildExpandableNotificationSettings(),

            // 치지직 VOD 설정 (ExpansionTile로 변경)
            if (widget.chzzkVideo != null &&
                widget.chzzkVideo!.channelID.isNotEmpty)
              buildExpandableChzzkVideoSettings(),

            // 유튜브 알림 설정 (ExpansionTile로 변경)
            if (widget.youtubeData != null &&
                widget.youtubeData!.channelName.isNotEmpty)
              buildExpandableYoutubeSettings(),

            // 카페 설정
            if (widget.cafeData != null &&
                widget.cafeData!.channelName.isNotEmpty)
              buildExpandableCafeSettings(),

            // 채팅 필터 설정
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

  // 알림 설정 섹션을 확장 가능한 패널로 변환
  Widget buildExpandableNotificationSettings() {
    // 선택된 알림 설정 개수 계산
    int selectedCount = _settings.entries.where((entry) => entry.value).length;

    return Card(
      margin: EdgeInsets.symmetric(vertical: 4.0),
      child: ExpansionTile(
        title: Row(
          children: [
            Text(
              '알림 설정',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
            SizedBox(width: 8),
            if (selectedCount > 0)
              Chip(
                label: Text(
                  '$selectedCount개 선택됨',
                  style: TextStyle(fontSize: 10, color: Colors.white),
                ),
                backgroundColor: Theme.of(context).primaryColor,
                padding: EdgeInsets.zero,
                labelPadding: EdgeInsets.symmetric(horizontal: 4),
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
          ],
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

  // 치지직 VOD 설정을 확장 가능한 패널로 변환
  Widget buildExpandableChzzkVideoSettings() {
    // 선택되었는지 확인
    final bool isSelected = _selectedChzzkVideoUsers.contains(
      widget.streamer.name,
    );

    return Card(
      margin: EdgeInsets.symmetric(vertical: 4.0),
      child: ExpansionTile(
        title: Row(
          children: [
            Text(
              '치지직 VOD',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
            SizedBox(width: 8),
            if (isSelected)
              Chip(
                label: Text(
                  '활성화됨',
                  style: TextStyle(fontSize: 10, color: Colors.white),
                ),
                backgroundColor: Theme.of(context).primaryColor,
                padding: EdgeInsets.zero,
                labelPadding: EdgeInsets.symmetric(horizontal: 4),
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
          ],
        ),
        initiallyExpanded: _isChzzkVodPanelExpanded,
        onExpansionChanged: (isExpanded) {
          setState(() {
            _isChzzkVodPanelExpanded = isExpanded;
          });
        },
        children: [
          if (widget.chzzkVideo == null || widget.chzzkVideo!.channelID.isEmpty)
            Padding(
              padding: const EdgeInsets.all(16.0),
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
        ],
      ),
    );
  }

  // 유튜브 알림 설정을 확장 가능한 패널로 변환
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
        title: Row(
          children: [
            Text(
              '유튜브 알림',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
            SizedBox(width: 8),
            if (selectedCount > 0)
              Chip(
                label: Text(
                  '$selectedCount개 선택됨',
                  style: TextStyle(fontSize: 10, color: Colors.white),
                ),
                backgroundColor: Theme.of(context).primaryColor,
                padding: EdgeInsets.zero,
                labelPadding: EdgeInsets.symmetric(horizontal: 4),
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
          ],
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
    final bool areAllSelected =
        _selectedCafeUsers.isNotEmpty &&
        filteredCafeUsers.every((user) => _selectedCafeUsers.contains(user));

    // 모든 항목이 선택 해제되었는지 확인
    final bool areAllDeselected =
        _selectedCafeUsers.isEmpty ||
        filteredCafeUsers.every((user) => !_selectedCafeUsers.contains(user));

    // 선택된 사용자 수
    final int selectedCount = _selectedCafeUsers.length;

    return Card(
      margin: EdgeInsets.symmetric(vertical: 4.0),
      child: ExpansionTile(
        title: Wrap(
          spacing: 8.0,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            // 아이콘 추가
            Icon(
              Icons.article_outlined,
              size: 18.0,
              color: Theme.of(context).primaryColor,
            ),
            // 제목
            Text(
              '카페 알림 설정',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
          ],
        ),
        // 부제목으로 선택된 사용자 수 표시
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
                    areAllDeselected
                        ? Icons.check_box
                        : Icons.check_box_outline_blank,
                    color:
                        areAllDeselected
                            ? Theme.of(context).primaryColor
                            : null,
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
                    areAllSelected
                        ? Icons.check_box
                        : Icons.check_box_outline_blank,
                    color:
                        areAllSelected ? Theme.of(context).primaryColor : null,
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
    );
  }

  Widget buildExpandableChatFilterSettings() {
    final bool isChzzk = widget.streamer.platform == 'chzzk';
    final bool isAfreeca = widget.streamer.platform == 'afreeca';

    // If neither platform is applicable, return empty container
    if (!isChzzk && !isAfreeca) return Container();

    // 선택된 사용자 수 계산
    int selectedCount = 0;
    if (isChzzk) {
      selectedCount = _selectedChzzkChatUsers.length;
    } else if (isAfreeca) {
      selectedCount = _selectedAfreecaChatUsers.length;
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Card(
          margin: EdgeInsets.symmetric(vertical: 4.0),
          child: ExpansionTile(
            title: Wrap(
              spacing: 8.0,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                // 아이콘 추가
                Icon(
                  Icons.chat_bubble_outline,
                  size: 18.0,
                  color: Theme.of(context).primaryColor,
                ),
                // 제목
                Text(
                  '채팅 필터',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
              ],
            ),
            // 부제목으로 선택된 사용자 수 표시 (제목 옆에 칩으로 표시하는 대신)
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
            initiallyExpanded:
                isChzzk
                    ? _isChzzkChatPanelExpanded
                    : _isAfreecaChatPanelExpanded,
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
              if (isChzzk)
                buildUsersList(
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
                ),
              if (isAfreeca)
                buildUsersList(
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
                ),
            ],
          ),
        ),
      ],
    );
  }

  // 사용자 목록 빌더 - 중복 코드 단순화
  Widget buildUsersList(
    List<String> allUsers,
    Set<String> selectedUsers,
    Function(String, bool) onToggle,
    TextEditingController searchController,
    String searchQuery,
    Function(String) onSearchChanged,
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
    final bool areAllSelected =
        selectedCount >= totalFilteredCount &&
        filteredUsers.every((user) => selectedUsers.contains(user));

    // 모든 항목이 선택 해제되었는지 확인
    final bool areAllDeselected =
        selectedUsers.isEmpty ||
        filteredUsers.every((user) => !selectedUsers.contains(user));

    return Column(
      children: [
        // 검색 필드
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8.0),
          child: TextField(
            controller: searchController,
            style: TextStyle(fontSize: 14.0),
            decoration: InputDecoration(
              hintText: '사용자 검색...',
              hintStyle: TextStyle(fontSize: 14.0),
              prefixIcon: Icon(Icons.search, size: 18.0),
              suffixIcon:
                  searchQuery.isNotEmpty
                      ? IconButton(
                        icon: Icon(Icons.clear, size: 18.0),
                        onPressed: () {
                          searchController.clear();
                          onSearchChanged('');
                        },
                        padding: EdgeInsets.zero,
                        constraints: BoxConstraints(
                          minWidth: 32,
                          minHeight: 32,
                        ),
                      )
                      : null,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8.0),
              ),
              contentPadding: EdgeInsets.symmetric(
                vertical: 4.0,
                horizontal: 8.0,
              ),
              isDense: true,
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
                  areAllDeselected
                      ? Icons.check_box
                      : Icons.check_box_outline_blank,
                  color:
                      areAllDeselected ? Theme.of(context).primaryColor : null,
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
                  areAllSelected
                      ? Icons.check_box
                      : Icons.check_box_outline_blank,
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

        // 사용자 목록
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
                                    ListTileControlAffinity.leading,
                                visualDensity: VisualDensity(
                                  horizontal: -4,
                                  vertical: -4,
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
    );
  }
}
