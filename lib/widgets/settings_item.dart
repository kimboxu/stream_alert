import 'package:flutter/material.dart';

class SettingsCheckboxItem extends StatelessWidget {
  final String title; // 설정 항목 제목
  final bool value; // 체크박스 현재 값
  final Function(bool?) onChanged; // 값 변경 시 호출될 콜백 함수
  
  const SettingsCheckboxItem({
    super.key,
    required this.title,
    required this.value,
    required this.onChanged,
  });
  
  @override
  Widget build(BuildContext context) {
    return CheckboxListTile(
      title: Text(title), // 설정 항목 제목 표시
      value: value, // 현재 상태 값
      onChanged: onChanged, // 상태 변경 콜백
      dense: true, // 더 조밀한 디자인
    );
  }
}