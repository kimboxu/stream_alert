import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import asyncio
from base import log_error, get_timestamp_from_stream_id

class HighlightChatSaver:
    """방송 종료 시 완성된 하이라이트 채팅 데이터를 저장하는 클래스"""
    
    def __init__(self, channel_name: str, base_dir: str = None):
        # 프로젝트 구조에 맞는 디렉토리 설정
        if base_dir is None:
            current_file = Path(__file__)
            if current_file.parent.name == 'py':
                project_root = current_file.parent.parent  # stream_alert/
            else:
                project_root = current_file.parent
            base_dir = project_root / "data"
        
        self.base_dir = Path(base_dir)
        self.highlight_dir = self.base_dir / "highlight_chats"
        self.highlight_stream_dir = self.highlight_dir / channel_name
        
        # 디렉토리 생성
        self.highlight_dir.mkdir(parents=True, exist_ok=True)
        self.highlight_stream_dir.mkdir(parents=True, exist_ok=True)
        
        # print(f"{datetime.now()} 하이라이트 채팅 저장기 초기화: {self.highlight_dir}")
    
    def _extract_readable_time_from_id(self, stream_id: str) -> str:
        """stream_id에서 읽기 쉬운 시간 형식으로 추출"""
        try:
            timestamp = get_timestamp_from_stream_id(stream_id)
            return timestamp.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(f"{datetime.now()} stream_id 시간 변환 실패 ({stream_id}): {str(e)}")
            return stream_id

    def _load_existing_file(self, file_path: Path) -> Optional[Dict]:
        """기존 파일이 있다면 로드"""
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return None
        except Exception as e:
            print(f"{datetime.now()} 기존 파일 로드 실패 ({file_path}): {str(e)}")
            return None

    def _merge_timeline_comments(self, existing_comments: List[Dict], new_comments: List[Dict]) -> List[Dict]:
        """기존 댓글과 새 댓글을 병합하되 중복 제거"""
        if not existing_comments:
            return new_comments
        
        if not new_comments:
            return existing_comments

        # 댓글의 고유성을 판단하기 위한 키 생성 함수
        def get_comment_key(comment: Dict) -> str:
            # comment_after_openDate와 text를 조합하여 고유 키 생성
            time_key = comment.get('comment_after_openDate', '')
            text_key = comment.get('text', '')
            return f"{time_key}_{text_key}"

        # 기존 댓글들의 키 세트 생성
        existing_keys = {get_comment_key(comment) for comment in existing_comments}
        
        # 새 댓글 중 중복되지 않는 것만 추가
        merged_comments = existing_comments.copy()
        for new_comment in new_comments:
            comment_key = get_comment_key(new_comment)
            if comment_key not in existing_keys:
                merged_comments.append(new_comment)
                existing_keys.add(comment_key)

        # 시간순으로 정렬
        try:
            merged_comments.sort(key=lambda x: x.get('comment_after_openDate', ''))
        except Exception as e:
            print(f"{datetime.now()} 댓글 정렬 실패: {str(e)}")

        return merged_comments

    async def save_completed_stream_highlight(self, channel_id: str, channel_name: str, 
                                            stream_id: str, highlight_data) -> str:
        """완성된 특정 스트림의 하이라이트 채팅 데이터를 파일로 저장"""
        try:
            # print(f"{datetime.now()} [저장 시작] 채널: {channel_name}, 스트림: {stream_id}")
            
            # 방송 시작 시간 추출
            start_time = "_".join(stream_id.split('_')[1:])
            readable_time = self._extract_readable_time_from_id(stream_id)
            # print(f"{datetime.now()} [시간 추출] 시작: {readable_time} -> 파일용: {start_time}")
            
            # 파일명 생성: highlight_chat_{채널명}_{시작시간}.json
            filename = f"highlight_chat_{channel_name}_{start_time}.json"
            file_path = self.highlight_stream_dir / filename
            # print(f"{datetime.now()} [파일 경로] {file_path}")
            
            # 기존 파일 확인 및 로드
            existing_data = self._load_existing_file(file_path)
            
            # highlight_data를 딕셔너리로 변환
            new_stream_data = self._convert_highlight_data_to_dict(highlight_data)
            # print(f"{datetime.now()} [새 데이터 변환] timeline_comments: {len(new_stream_data.get('timeline_comments', []))}개")
            
            if existing_data:
                # print(f"{datetime.now()} [기존 파일 발견] 기존 댓글: {len(existing_data.get('timeline_comments', []))}개")
                
                # 기존 데이터와 새 데이터 병합
                merged_comments = self._merge_timeline_comments(
                    existing_data.get('timeline_comments', []),
                    new_stream_data.get('timeline_comments', [])
                )
                
                # 저장할 데이터 준비 (기존 데이터 기반으로 업데이트)
                save_data = existing_data.copy()
                save_data.update({
                    "timeline_comments": merged_comments,
                    "last_updated": datetime.now().isoformat(),
                    "update_count": existing_data.get("update_count", 0) + 1,
                    # 스트림이 종료된 경우에만 종료 정보 업데이트
                    "stream_end_id": new_stream_data.get("stream_end_id", existing_data.get("stream_end_id", "")),
                    "stream_end_time": (self._get_stream_end_time(highlight_data) 
                                      if new_stream_data.get("stream_end_id") 
                                      else existing_data.get("stream_end_time", "")),
                    "last_title": new_stream_data.get("last_title", existing_data.get("last_title", "")),
                })
                
                # print(f"{datetime.now()} [데이터 병합] 병합 후 댓글: {len(merged_comments)}개 (업데이트 횟수: {save_data['update_count']})")
                
            else:
                # 새 파일 생성
                save_data = {
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "stream_start_id": stream_id,
                    "stream_end_id": new_stream_data.get("stream_end_id", ""),
                    "stream_start_time": readable_time,
                    "stream_end_time": self._get_stream_end_time(highlight_data),
                    "last_title": new_stream_data.get("last_title", ""),
                    "saved_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "update_count": 1,
                    "timeline_comments": new_stream_data.get("timeline_comments", []),
                }
                
                # print(f"{datetime.now()} [새 파일 생성] 댓글: {len(save_data['timeline_comments'])}개")
            
            # 통계 재계산
            save_data["statistics"] = self._calculate_statistics(save_data)
            
            # print(f"{datetime.now()} [데이터 준비 완료]")
            # print(f"  - 최종 타임라인 댓글: {len(save_data['timeline_comments'])}개")
            # print(f"  - 업데이트 횟수: {save_data.get('update_count', 1)}")
            # print(f"  - 통계: {save_data['statistics']}")
            
            # JSON 파일로 저장
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2, default=str)
            
            # 저장 결과 출력
            # stats = save_data["statistics"]
            # action = "업데이트" if existing_data else "저장"
            # print(f"{datetime.now()} 하이라이트 채팅 {action} 완료:")
            # print(f"  - 파일: {filename}")
            # print(f"  - 채널: {channel_name} ({channel_id})")
            # print(f"  - 방송 시간: {readable_time}")
            # print(f"  - 마지막 방제: {save_data.get('last_title', '')}")
            # print(f"  - 총 하이라이트: {stats['total_highlights']}개")
            # print(f"  - 업데이트 횟수: {save_data.get('update_count', 1)}")
            # if stats['total_with_scores'] > 0:
            #     print(f"  - 평균 재미도: {stats['avg_score']:.1f} (최고: {stats['max_score']:.1f})")
            #     print(f"  - 큰 하이라이트: {stats['big_highlights']}개")
            
            return str(file_path)
            
        except Exception as e:
            error_msg = f"하이라이트 채팅 파일 저장 실패 ({channel_name}, {stream_id}): {str(e)}"
            await log_error(error_msg)
            print(f"{datetime.now()} {error_msg}")
            return ""
    
    def _convert_highlight_data_to_dict(self, highlight_data) -> Dict:
        """highlight_chat_Data 객체를 딕셔너리로 변환"""
        try:
            # print(f"{datetime.now()} [데이터 변환] 타입: {type(highlight_data)}")
            
            if hasattr(highlight_data, '__dict__'):
                result = {
                    "timeline_comments": getattr(highlight_data, 'timeline_comments', []),
                    "stream_end_id": getattr(highlight_data, 'stream_end_id', ''),
                    "last_title": getattr(highlight_data, 'last_title', ''),
                }
                # print(f"{datetime.now()} [객체 변환] 속성 접근 성공")
                # print(f"  - timeline_comments: {len(result['timeline_comments'])}개")
                # print(f"  - stream_end_id: {result['stream_end_id']}")
                # print(f"  - last_title: {result['last_title']}")
                return result
                
            elif isinstance(highlight_data, dict):
                print(f"{datetime.now()} [딕셔너리] 키: {list(highlight_data.keys())}")
                return highlight_data
            else:
                print(f"{datetime.now()} [알 수 없는 타입] {type(highlight_data)}")
                return {"timeline_comments": [], "stream_end_id": "", "last_title": ""}
                
        except Exception as e:
            print(f"{datetime.now()} [변환 오류] {str(e)}")
            return {"timeline_comments": [], "stream_end_id": "", "last_title": ""}
    
    def _get_stream_end_time(self, highlight_data) -> str:
        """스트림 종료 시간 추출"""
        try:
            if hasattr(highlight_data, 'stream_end_id') and highlight_data.stream_end_id:
                return self._extract_readable_time_from_id(highlight_data.stream_end_id)
            elif isinstance(highlight_data, dict) and 'stream_end_id' in highlight_data:
                if highlight_data['stream_end_id']:
                    return self._extract_readable_time_from_id(highlight_data['stream_end_id'])
        except Exception as e:
            print(f"{datetime.now()} 스트림 종료 시간 추출 실패: {str(e)}")
        
        return ""
    
    def _calculate_statistics(self, stream_data: Dict) -> Dict:
        """하이라이트 통계 계산"""
        try:
            timeline_comments = stream_data.get("timeline_comments", [])
            
            if not timeline_comments:
                return {
                    "total_highlights": 0,
                    "total_with_scores": 0,
                    "avg_score": 0.0,
                    "max_score": 0.0,
                    "min_score": 0.0,
                    "big_highlights": 0,
                    "score_ranges": {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
                }
            
            # 점수 데이터 추출
            scores = []
            big_highlights = 0
            
            for comment in timeline_comments:
                if isinstance(comment, dict) and 'score_difference' in comment:
                    try:
                        score = float(comment['score_difference'])
                        scores.append(score)
                        if score > 70:  # 큰 하이라이트 기준
                            big_highlights += 1
                    except (ValueError, TypeError):
                        continue
            
            if not scores:
                return {
                    "total_highlights": len(timeline_comments),
                    "total_with_scores": len(scores),
                    "avg_score": 0.0,
                    "max_score": 0.0,
                    "min_score": 0.0,
                    "big_highlights": 0,
                    "score_ranges": {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
                }
            
            # 점수 범위별 분류
            score_ranges = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
            for score in scores:
                if score <= 20:
                    score_ranges["0-20"] += 1
                elif score <= 40:
                    score_ranges["21-40"] += 1
                elif score <= 60:
                    score_ranges["41-60"] += 1
                elif score <= 80:
                    score_ranges["61-80"] += 1
                else:
                    score_ranges["81-100"] += 1
            
            return {
                "total_highlights": len(timeline_comments),
                "total_with_scores": len(scores),
                "avg_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
                "max_score": round(max(scores), 2) if scores else 0.0,
                "min_score": round(min(scores), 2) if scores else 0.0,
                "big_highlights": big_highlights,
                "score_ranges": score_ranges
            }
            
        except Exception as e:
            print(f"{datetime.now()} 통계 계산 오류: {str(e)}")
            return {
                "total_highlights": 0,
                "total_with_scores": 0,
                "avg_score": 0.0,
                "max_score": 0.0,
                "min_score": 0.0,
                "big_highlights": 0,
                "score_ranges": {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
            }
    
    def get_saved_files_info(self, channel_name: str = None) -> list:
        """저장된 파일들의 정보 반환"""
        try:
            json_files = list(self.highlight_stream_dir.glob("highlight_chat_*.json"))
            
            file_list = []
            for file_path in sorted(json_files, key=lambda x: x.stat().st_mtime, reverse=True):
                try:
                    # 파일 기본 정보
                    file_info = {
                        "filename": file_path.name,
                        "path": str(file_path),
                        "size_mb": round(file_path.stat().st_size / 1024 / 1024, 2),
                        "modified_at": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                    }
                    
                    # JSON 내용 정보
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        file_info.update({
                            "channel_id": data.get("channel_id", ""),
                            "channel_name": data.get("channel_name", "Unknown"),
                            "stream_start_time": data.get("stream_start_time", ""),
                            "total_highlights": data.get("statistics", {}).get("total_highlights", 0),
                            "avg_score": data.get("statistics", {}).get("avg_score", 0.0),
                            "saved_at": data.get("saved_at", ""),
                            "last_updated": data.get("last_updated", ""),
                            "update_count": data.get("update_count", 1),
                        })
                    except Exception:
                        # JSON 읽기 실패해도 기본 정보는 유지
                        pass
                    
                    # 특정 채널 필터링
                    if channel_name and file_info.get("channel_name") != channel_name:
                        continue
                    
                    file_list.append(file_info)
                    
                except Exception as e:
                    print(f"{datetime.now()} 파일 정보 읽기 실패 ({file_path}): {str(e)}")
                    continue
            
            return file_list
            
        except Exception as e:
            print(f"{datetime.now()} 저장된 파일 정보 조회 실패: {str(e)}")
            return []