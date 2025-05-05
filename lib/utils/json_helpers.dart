import 'dart:convert';
import 'package:flutter/material.dart';

//key 값 추출
class JsonHelper {
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

  static void updateJsonFromSelectedUsers(
    Map<String, Set<String>> selectedUsers,
    TextEditingController controller,
  ) {
    Map<String, List<String>> jsonData = {};
    selectedUsers.forEach((key, users) {
      if (users.isNotEmpty) {
        jsonData[key] = users.toList();
      }
    });
    controller.text = json.encode(jsonData);
  }

  static void updateJsonFromMultipleSelectedUsers(
    List<Map<String, Set<String>>> selectedUsersMaps,
    TextEditingController controller,
  ) {
    Map<String, List<String>> jsonData = {};

    for (var selectedUsers in selectedUsersMaps) {
      selectedUsers.forEach((key, users) {
        if (users.isNotEmpty) {
          jsonData[key] = users.toList();
        }
      });
    }

    controller.text = json.encode(jsonData);
  }
}
