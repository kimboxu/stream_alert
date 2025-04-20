class StringHelper {
  static String getSettingDisplayName(String key) {
    switch (key) {
      case '뱅온 알림':
        return '뱅온 알림';
      case '방제 변경 알림':
        return '방제 변경 알림';
      case '방종 알림':
        return '방종 알림';
      case '유튜브 알림':
        return '유튜브 알림';
      case '치지직 VOD':
        return '치지직 VOD 알림';
      case 'chzzkChatFilter':
        return '치지직 채팅 필터';
      case 'afreeca_chatFilter':
        return '아프리카 채팅 필터';
      case 'cafe_user_json':
        return '카페 알림 설정';
      default:
        return key;
    }
  }

  static Set<String> parseSelectedStrings(String settingsValue) {
    Set<String> result = {};
    if (settingsValue.isNotEmpty) {
      List<String> items = settingsValue.split(', ');
      result.addAll(items);
    }
    return result;
  }
}