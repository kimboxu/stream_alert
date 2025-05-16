import 'dart:convert';
import 'package:flutter/material.dart';

class JsonHelper {
  // JSON에서 문자열 리스트를 포함하는 맵을 파싱하는 메서드
  static Map<String, List<String>> parseStringListMap(
    Map<String, dynamic> json,
    String key,
  ) {
    Map<String, List<String>> result = {};
    if (json[key] != null) {
      (json[key] as Map<String, dynamic>).forEach((mapKey, value) {
        if (value is List) {
          result[mapKey] = List<String>.from(value);
        } else {
          result[mapKey] = [];
        }
      });
    }
    return result;
  }

  // 선택된 사용자 목록을 JSON 텍스트로 변환하여 컨트롤러에 설정
  static void updateJsonFromSelectedUsers(
    Map<String, Set<String>> selectedUsers,
    TextEditingController controller,
  ) {
    Map<String, List<String>> jsonData = {};
    selectedUsers.forEach((key, users) {
      if (users.isNotEmpty) {
        jsonData[key] = users.toList(); // Set을 List로 변환
      }
    });
    controller.text = json.encode(jsonData); // JSON 문자열로 인코딩
  }

  // 여러 맵에서 선택된 사용자 목록을 통합하여 JSON으로 변환
  static void updateJsonFromMultipleSelectedUsers(
    List<Map<String, Set<String>>> selectedUsersMaps,
    TextEditingController controller,
  ) {
    Map<String, List<String>> jsonData = {};

    // 여러 맵의 데이터를 하나로 병합
    for (var selectedUsers in selectedUsersMaps) {
      selectedUsers.forEach((key, users) {
        if (users.isNotEmpty) {
          jsonData[key] = users.toList();
        }
      });
    }

    controller.text = json.encode(jsonData); // JSON 문자열로 인코딩
  }
}