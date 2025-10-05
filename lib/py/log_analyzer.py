import json
import pandas as pd
from datetime import datetime
import glob
import argparse
import sys
import asyncio
from pathlib import Path

# AI 기능을 위한 추가 임포트
try:
    from base import format_time_for_comment
    from chat_analyzer import StreamHighlight
    from genai_model import get_genai_model
    AI_AVAILABLE = True
except ImportError as e:
    print(f"AI 기능을 사용할 수 없습니다: {e}")
    AI_AVAILABLE = False

class SessionBasedFunScoreAnalyzer:
    """방송 세션별로 재미도 로그를 분석하는 클래스"""
    
    def __init__(self, channel_name, date, use_ai=False, base_dir=None):
        # 임계값
        self.small_fun_difference   = 15    # 작은 재미 차이
        self.big_fun_difference     = 70    # 큰 재미 차이
        
        # AI 사용 여부 설정
        self.use_ai = use_ai

        # 기본 디렉토리 설정 (스크립트 위치 기준)
        if base_dir is None:
            script_dir = Path(__file__).parent
            self.base_dir = script_dir.parent  # stream_alert/ 디렉토리
        else:
            self.base_dir = Path(base_dir)
        
        # 각 디렉토리 경로 설정
        self.data_dir = self.base_dir / "data"
        self.log_dir = self.data_dir / "fun_score_logs"
        self.output_dir = self.base_dir / "output"
        self.csv_dir = self.output_dir / "csv"
        self.plots_dir = self.output_dir / "plots"
        self.reports_dir = self.output_dir / "reports"
        
        # 출력 디렉토리 생성
        self._ensure_directories()
        
        self.channel_name = channel_name
        self.date = date
        
        # 프로젝트 구조 정보 출력
        self._print_project_info()
        
    def _ensure_directories(self):
        """필요한 디렉토리들이 없으면 생성"""
        directories = [
            self.data_dir, 
            self.log_dir, 
            self.output_dir, 
            self.csv_dir, 
            self.plots_dir,
            self.reports_dir
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            
    def _print_project_info(self):
        """프로젝트 구조 정보 출력"""
        print(f"프로젝트 구조:")
        print(f"   Base: {self.base_dir}")
        print(f"   Logs: {self.log_dir}")
        print(f"   CSV: {self.csv_dir}")
        print(f"   Plots: {self.plots_dir}")
        print(f"   Reports: {self.reports_dir}")
        print(f"   AI 사용: {'예' if self.use_ai else '아니오'}")
        
    def parse_time_string(self, time_str):
        """after_openDate 시간 문자열을 초로 변환"""
        # "0:00:30" 형태의 문자열을 파싱
        parts = time_str.split(':')
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        return 0
    
    def get_date_from_timestamp(self, timestamp_str):
        """timestamp에서 날짜 문자열 추출 (YYYY-MM-DD 형태)"""
        try:
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
        except:
            return None
    
    def detect_session_breaks(self, logs):
        """after_openDate를 기준으로 방송 세션 구분점 찾기"""
        if not logs:
            return []
        
        sessions = []
        current_session = [logs[0]]
        prev_time = self.parse_time_string(logs[0]['after_openDate'])
        date_str = self.get_date_from_timestamp(logs[0]['timestamp'])
        
        for _, log in enumerate(logs[1:], 1):
            current_time = self.parse_time_string(log['after_openDate'])
            
            # after_openDate가 이전보다 작아지면 새로운 방송 시작
            if current_time < prev_time:
                date_str = self.get_date_from_timestamp(current_session[0]['timestamp'])

                # 현재 세션 저장
                sessions.append([date_str, current_session])
                # 새로운 세션 시작
                current_session = [log]
                print(f"새 세션 감지: {log['timestamp']} (after_openDate: {log['after_openDate']})")
            else:
                current_session.append(log)
            
            prev_time = current_time
        
        # 마지막 세션 추가
        if current_session:
            date_str = self.get_date_from_timestamp(current_session[0]['timestamp'])
            sessions.append([date_str, current_session])
        
        return sessions
    
    def load_all_logs(self):
        """모든 로그 파일을 로드하여 합치기"""
        pattern = f"fun_score_detailed_"
        if self.channel_name:
            pattern += f"{self.channel_name}_"
        pattern += "*.json"
        
        # log_dir에서 파일 검색
        search_pattern = self.log_dir / pattern
        files = glob.glob(str(search_pattern))
        all_logs = []
        
        print(f"📂 로그 검색 경로: {search_pattern}")
        
        if not files:
            print(f"⚠️ 경고: {self.log_dir}에서 로그 파일을 찾을 수 없습니다.")
            print(f"   다음 패턴으로 검색했습니다: {pattern}")
            return []
        
        for file in sorted(files):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logs = data['logs']
                all_logs.extend(logs)
                print(f"✅ 로드: {Path(file).name} ({len(logs)}개)")
            except Exception as e:
                print(f"❌ 파일 로드 오류 {file}: {e}")
                continue
        
        print(f"📊 총 {len(files)}개 파일에서 {len(all_logs)}개 로그 로드됨")
        return all_logs
    
    def analyze_session(self, session_logs, date_str):
        """ 세션 분석"""
        if not session_logs:
            return {}
        
        scores = [log['fun_score'] for log in session_logs]
        test_scores = [log.get('test_fun_score', 0) for log in session_logs]

        # 세션 시작/종료 시간
        start_time = session_logs[0]['timestamp']
        end_time = session_logs[-1]['timestamp']
        start_after_open = session_logs[0]['after_openDate']
        end_after_open = session_logs[-1]['after_openDate']

        start_seconds = self.parse_time_string(start_after_open)
        end_seconds = self.parse_time_string(end_after_open)
        duration_seconds = end_seconds - start_seconds
        duration_hours = duration_seconds / 3600

        # 하이라이트 정보
        highlights = sum(1 for log in session_logs 
                        if log.get('score_components', {}).get('highlights', False) 
                        and log.get('score_components', {}).get('should_create_new_highlight', True))
        big_highlights = sum(1 for log in session_logs 
                            if log.get('score_components', {}).get('big_highlights', False)
                            and log.get('score_components', {}).get('should_create_new_highlight', True))

        # test 하이라이트
        test_highlights = sum(1 for log in session_logs 
                            if log.get('score_components', {}).get('test_highlights', False) 
                            and log.get('score_components', {}).get('test_should_create_new_highlight', True))
        test_big_highlights = sum(1 for log in session_logs 
                                if log.get('score_components', {}).get('test_big_highlights', False)
                                and log.get('score_components', {}).get('test_should_create_new_highlight', True))

        # 동적 임계값 및 점수 차이 통계
        baseline_thresholds = []
        score_differences = []
        test_score_differences = []

        for log in session_logs:
            score_comp = log.get('score_components', {})
            if 'baseline_threshold' in score_comp:
                baseline_thresholds.append(score_comp['baseline_threshold'])
            if 'score_difference' in score_comp:
                score_differences.append(score_comp['score_difference'])
            if 'test_score_difference' in score_comp:
                test_score_differences.append(score_comp['test_score_difference'])
            else:
                # fallback: test용 별도 값 없으면 score_difference 그대로 활용
                test_score_differences.append(score_comp.get('score_difference', 0))

        avg_baseline_thresholds = sum(baseline_thresholds) / len(baseline_thresholds) if baseline_thresholds else 50
        avg_score_difference = sum(score_differences) / len(score_differences) if score_differences else 0
        max_score_difference = max(score_differences) if score_differences else 0

        avg_test_score_difference = sum(test_score_differences) / len(test_score_differences) if test_score_differences else 0
        max_test_score_difference = max(test_score_differences) if test_score_differences else 0

        stats = {
            'date_str': date_str,
            'start_time': start_time,
            'end_time': end_time,
            'start_after_open': start_after_open,
            'end_after_open': end_after_open,
            'duration_hours': duration_hours,
            'total_analyses': len(session_logs),

            # 점수
            'avg_score': sum(scores) / len(scores),
            'avg_test_score': sum(test_scores) / len(test_scores) if test_scores else 0,
            'max_score': max(scores),
            'min_score': min(scores),

            # 하이라이트
            'highlights': highlights,
            'big_highlights': big_highlights,
            'test_highlights': test_highlights,
            'test_big_highlights': test_big_highlights,

            # 동적 하이라이트 관련 통계
            'avg_baseline_thresholds': avg_baseline_thresholds,
            'avg_score_difference': avg_score_difference,
            'max_score_difference': max_score_difference,

            # 점수 차이 (test 버전)
            'avg_test_score_difference': avg_test_score_difference,
            'max_test_score_difference': max_test_score_difference,

            # 하이라이트 비율
            'highlight_rate': highlights / len(scores) * 100,
            'big_highlight_rate': big_highlights / len(scores) * 100,
            'test_highlight_rate': test_highlights / len(scores) * 100 if test_scores else 0,
            'test_big_highlight_rate': test_big_highlights / len(scores) * 100 if test_scores else 0,

            # 뷰어 수
            'max_viewers': max([log['analysis_data']['viewer_count'] for log in session_logs]),
            'avg_viewers': sum([log['analysis_data']['viewer_count'] for log in session_logs]) / len(session_logs),
        }

        return stats
    
    def create_session_plot(self, session_logs, session_stats, save_plot=True):
        """세션별 그래프 생성"""
        if not session_logs:
            return
        
        try:
            import matplotlib.pyplot as plt
            import platform
            
            # 한글 폰트 설정
            plt.rcParams['font.family'] = ['DejaVu Sans']
            if platform.system() == 'Windows':
                plt.rcParams['font.family'] = ['Malgun Gothic', 'DejaVu Sans']
            elif platform.system() == 'Darwin':
                plt.rcParams['font.family'] = ['AppleGothic', 'DejaVu Sans']
            else:
                plt.rcParams['font.family'] = ['Noto Sans CJK KR', 'DejaVu Sans']
            
            plt.rcParams['axes.unicode_minus'] = False
            
            # 데이터 준비
            after_open_times = [self.parse_time_string(log['after_openDate']) / 60 for log in session_logs]
            scores = [log['fun_score'] for log in session_logs]
            viewer_counts = [log['analysis_data']['viewer_count'] for log in session_logs]
            
            # 동적 임계값 데이터
            baseline_thresholds = []
            score_difference_list = []
            for log in session_logs:
                threshold = log.get('score_components', {}).get('baseline_threshold', 50)
                score_difference = log.get('score_components', {}).get('score_difference', 0)
                baseline_thresholds.append(threshold)
                score_difference_list.append(score_difference)

            
            # 2개 서브플롯 생성
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
            
            # 첫 번째 플롯: 재미도 점수
            ax1.plot(after_open_times, scores, 'b-', alpha=0.7, linewidth=1.5, label='재미도 점수')
            
            # 동적 임계값 라인
            # ax1.plot(after_open_times, baseline_thresholds, 'orange', linestyle='-.', alpha=0.5, label='동적 임계값')
            ax1.plot(after_open_times, score_difference_list, 'purple', linestyle='-.', alpha=0.8, label='하이라이트 동적 임계값')
            
            # 고정 임계값 (참고용)
            ax1.axhline(y=self.small_fun_difference, color='darkorange', linestyle=':', alpha=0.9, linewidth=3,
                    label=f'하이라이트 기준: {self.small_fun_difference}점 차이')
            ax1.axhline(y=self.big_fun_difference, color='crimson', linestyle=':', alpha=0.9, linewidth=3,
                        label=f'대형 하이라이트 기준: {self.big_fun_difference}점 차이')
            
            ax1.fill_between(after_open_times, scores, alpha=0.3)
            ax1.fill_between(after_open_times, score_difference_list, alpha=0.3)
            
            # 하이라이트 순간 표시
            highlight_times = []
            highlight_scores = []
            big_highlight_times = []
            big_highlight_scores = []
            
            for i, log in enumerate(session_logs):
                score_comp = log.get('score_components', {})
                is_highlight = score_comp.get('highlights', False)
                is_big_highlight = score_comp.get('big_highlights', False)
                should_create = score_comp.get('should_create_new_highlight', True)
                
                if is_highlight and should_create:
                    highlight_times.append(after_open_times[i])
                    highlight_scores.append(scores[i])
                if is_big_highlight and should_create:
                    big_highlight_times.append(after_open_times[i])
                    big_highlight_scores.append(scores[i])
            
            if highlight_times:
                ax1.scatter(highlight_times, highlight_scores, color='orange', s=30, alpha=0.7, 
                        zorder=5, label=f'하이라이트 ({len(highlight_times)}개)')
            
            if big_highlight_times:
                ax1.scatter(big_highlight_times, big_highlight_scores, color='red', s=50, alpha=0.8, 
                        zorder=5, label=f'대형 하이라이트 ({len(big_highlight_times)}개)')
            
            ax1.set_title(f'재미도 점수 변화 - ({session_stats["date_str"]})\n'
                        f'({session_stats["start_after_open"]} ~ {session_stats["end_after_open"]}, '
                        f'{session_stats["duration_hours"]:.1f}시간, 평균 임계값: {session_stats.get("avg_baseline_thresholds", 50):.1f})')
            ax1.set_xlabel('방송 시작 후 시간 (분)')
            ax1.set_ylabel('재미도 점수')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # 두 번째 플롯: 시청자 수
            ax2.plot(after_open_times, viewer_counts, 'g-', alpha=0.7, linewidth=1.5, label='시청자 수')
            ax2.fill_between(after_open_times, viewer_counts, alpha=0.3, color='green')
            ax2.set_xlabel('방송 시작 후 시간 (분)')
            ax2.set_ylabel('시청자 수')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            plt.tight_layout()
            
            if save_plot:
                start_date = datetime.fromisoformat(session_stats['start_time']).strftime('%Y-%m-%d_%H%M')
                filename = f"{self.channel_name}_{start_date}_plot.png"
                
                plot_path = self.plots_dir / filename
                plt.savefig(plot_path, dpi=150, bbox_inches='tight')
                print(f"📈 세션 그래프 저장: {plot_path}")
            
            plt.show()
            
        except ImportError:
            print("⚠️ matplotlib가 설치되지 않아 그래프를 생성할 수 없습니다.")
    
    def export_session_to_csv(self, session_logs, session_stats):
        """ 데이터를 CSV 내보내기"""
        if not session_logs:
            return None
        
        data = []
        for log in session_logs:
            try:
                score_components = log.get('score_components', {})
                
                row = {
                    'timestamp': log['timestamp'],
                    'after_openDate': log['after_openDate'],
                    'after_open_minutes': self.parse_time_string(log['after_openDate']) / 60,
                    'fun_score': log['fun_score'],
                    'message_count': log['analysis_data']['message_count'],
                    'viewer_count': log['analysis_data']['viewer_count'],
                    
                    # 점수 구성 요소들
                    'chat_spike_score': score_components.get('chat_spike_score', 0),
                    'reaction_score': score_components.get('reaction_score', 0),
                    'diversity_score': score_components.get('diversity_score', 0),
                    'viewer_trend_score': score_components.get('viewer_trend_score', 0),
                    'final_score': score_components.get('final_score', 0),
                    
                    # 동적 하이라이트 정보
                    'baseline_threshold': score_components.get('baseline_threshold', 50),
                    'score_difference': score_components.get('score_difference', 0),
                    'baseline_chat_count': score_components.get('baseline_chat_count', 0),
                    'baseline_viewer_count': score_components.get('baseline_viewer_count', 0),
                    
                    # 하이라이트 정보
                    'is_highlight': score_components.get('highlights', False),
                    'is_big_highlight': score_components.get('big_highlights', False),
                    'should_create_new_highlight': score_components.get('should_create_new_highlight', True),
                    'is_actual_highlight': score_components.get('highlights', False) and score_components.get('should_create_new_highlight', True),
                    'is_actual_big_highlight': score_components.get('big_highlights', False) and score_components.get('should_create_new_highlight', True),
                    
                    # 키워드 데이터
                    'laugh_count': log['analysis_data'].get('fun_keywords', {}).get('laugh', 0),
                    'excitement_count': log['analysis_data'].get('fun_keywords', {}).get('excitement', 0),
                    'surprise_count': log['analysis_data'].get('fun_keywords', {}).get('surprise', 0),
                    'reaction_count': log['analysis_data'].get('fun_keywords', {}).get('reaction', 0),
                    
                    # 추가 정보
                    'total_keywords': sum(log['analysis_data'].get('fun_keywords', {}).values()),
                    'chat_context_sample': str(log.get('chat_context', [])[:3])
                }
            except Exception as e:
                print(f"데이터 처리 오류: {e}")
                continue
            
            data.append(row)
        
        if not data:
            return None
        
        df = pd.DataFrame(data)
        start_date = datetime.fromisoformat(session_stats['start_time']).strftime('%Y-%m-%d_%H%M')
        filename = f"{self.channel_name}_{start_date}.csv"
        
        # csv 디렉토리에 저장
        csv_path = self.csv_dir / filename
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"💾 세션 CSV 저장: {csv_path} ({len(df)}행)")
        return str(csv_path)
    
    async def export_highlights_to_text(self, session_logs, session_stats):
        """하이라이트 데이터를 VOD 댓글 형식의 타임라인 텍스트로 추출"""
        if not session_logs:
            return None
        
        # AI 사용 여부에 따라 분기
        if self.use_ai:
            return await self._export_highlights_with_ai(session_logs, session_stats)
        else:
            return await self._export_highlights_basic(session_logs, session_stats)

    async def _export_highlights_with_ai(self, session_logs, session_stats):
        """AI를 사용한 하이라이트 댓글 생성"""
        
        try:
            if not AI_AVAILABLE:
                print(f"{datetime.now()} AI 모듈을 가져올 수 없어서 기본 로직을 사용합니다.")
                return await self._export_highlights_basic(session_logs, session_stats)
            
            model = get_genai_model(0)
            
            print(f"{datetime.now()} AI 모델 로드 완료")
            
            # 1단계: 하이라이트 데이터 수집 및 StreamHighlight 객체 생성
            highlights = []
            
            for log in session_logs:
                score_components = log.get('score_components', {})
                
                # 하이라이트인지 확인
                if (score_components.get('highlights', False) and 
                    score_components.get('should_create_new_highlight', True)):
                    
                    # StreamHighlight 객체 생성
                    highlight = StreamHighlight(
                        timestamp=log['timestamp'],
                        channel_id="log_analyzer_dummy",  # 로그 분석용 더미 값
                        channel_name=self.channel_name,
                        fun_score=log['fun_score'],
                        reason=log.get('reason', '재미있는 순간 감지'),
                        chat_context=log.get('chat_context', []),
                        duration=30,  # 기본값
                        after_openDate=log['after_openDate'],
                        comment_after_openDate=log['comment_after_openDate'],
                        score_details=score_components,
                        image=log.get('image', ""),
                        analysis_data=log.get('analysis_data', {}),
                    )
                    highlights.append(highlight)
            
            if not highlights:
                print(f"{datetime.now()} 하이라이트가 없어서 AI 텍스트 생성을 건너뜁니다.")
                return None
            
            # 2단계: ChatAnalyzer의 _make_highlight_chat 로직 재현
            timeline_comments = await self._ai_make_highlight_chat(highlights, model)
            
            if not timeline_comments:
                print(f"{datetime.now()} AI 댓글 생성 실패, 기본 로직으로 fallback")
                return await self._export_highlights_basic(session_logs, session_stats)
            
            # 3단계: 텍스트 형식으로 변환
            highlight_lines = []
            
            for comment in timeline_comments:
                try:
                    after_open = comment.get('comment_after_openDate', '00:00:00')
                    after_open = format_time_for_comment(after_open, 25)
                    
                    # AI가 생성한 description 사용
                    description = comment.get('description', comment.get('text', '재미구간'))
                    
                    # 재미 점수 정보 추가 (선택적)
                    score_diff = float(comment.get('score_difference', 0))
                    if score_diff:
                        fun_score = self._calculate_fun_score_from_diff(score_diff)
                        final_text = f"재미 점수:{fun_score} - {description}"
                    else:
                        final_text = description
                    
                    highlight_lines.append(f"{after_open}- {final_text}")
                    
                except Exception as comment_error:
                    print(f"{datetime.now()} 댓글 처리 중 오류: {comment_error}")
                    continue
            
            if not highlight_lines:
                print(f"{datetime.now()} 유효한 AI 댓글이 없어서 기본 로직 사용")
                return await self._export_highlights_basic(session_logs, session_stats)
            
            # 4단계: 파일 저장
            final_content = "\n\n".join(highlight_lines)
            start_date = datetime.fromisoformat(session_stats['start_time']).strftime('%Y-%m-%d_%H%M')
            filename = f"{self.channel_name}_{start_date}_highlights.txt"
            file_path = self.reports_dir / filename
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            print(f"{datetime.now()} AI 기반 하이라이트 텍스트 저장: {file_path}")
            print(f"{datetime.now()} 생성된 댓글 수: {len(highlight_lines)}개")
            
            return {
                'highlights_count': len(highlight_lines),
                'file_path': str(file_path),
                'method': 'ai_generated',
                'ai_comments': timeline_comments
            }
            
        except Exception as e:
            print(f"{datetime.now()} AI 하이라이트 텍스트 생성 중 오류: {e}")
            return await self._export_highlights_basic(session_logs, session_stats)

    async def _ai_make_highlight_chat(self, highlights: list[StreamHighlight], model):
        """ChatAnalyzer의 _make_highlight_chat 로직을 재현"""
        if not highlights:
            return []
        
        try:
            # 하이라이트 데이터 구성 (ChatAnalyzer와 동일한 형식)
            highlight_data = []
            images_with_labels = []  # 이미지가 없으므로 빈 리스트
            
            for i, highlight in enumerate(highlights):
                try:
                    analysis_data = highlight.analysis_data
                    fun_keywords = analysis_data.get('fun_keywords', {})
                    score_details = highlight.score_details

                    highlight_data.append({
                        "하이라이트_ID": f"HIGHLIGHT_{i+1}",
                        "재미도_점수": highlight.fun_score,
                        "하이라이트_이유": highlight.reason,
                        "최근_채팅": highlight.chat_context,
                        "최고점수_시간": highlight.after_openDate,
                        "VOD_타임라인_시간": highlight.comment_after_openDate,
                        "방송_썸네일": f"이미지_{i+1}",  # 이미지가 없지만 형식 유지
                        "메시지_갯수": analysis_data['message_count'],
                        "시청자_수": analysis_data['viewer_count'],
                        "웃음_키워드_수": fun_keywords.get('laugh', 0),
                        "놀람_키워드_수": fun_keywords.get('surprise', 0),
                        "흥분_키워드_수": fun_keywords.get('excitement', 0),
                        "일반반응_키워드_수": fun_keywords.get('reaction', 0),
                        "인사_키워드_수": fun_keywords.get('greeting', 0),
                        "채팅_급증_점수": score_details['chat_spike_score'],
                        "리액션_점수": score_details['reaction_score'],
                        "다양성_점수": score_details['diversity_score'],
                        "시청자_급증_점수": score_details['viewer_trend_score'],
                        "기준_채팅_수": score_details['baseline_chat_count'],
                        "기준_시청자_수": score_details['baseline_viewer_count'],
                        "하이라이트_여부": score_details['highlights'],
                        "큰_하이라이트_여부": score_details['big_highlights'],
                        "재미도_점수_차이": score_details['score_difference'],
                    })
                    images_with_labels.append(highlight.image)

                except Exception as e:
                    print(f"{datetime.now()} 하이라이트 데이터 처리 오류: {e}")
                    continue

            if not highlight_data:
                return []

            # AI 프롬프트 생성 (ChatAnalyzer와 동일)
            prompt = f"""다음 상세 분석 데이터를 바탕으로 VOD 타임라인 댓글을 생성해주세요.

                중요: 각 하이라이트의 "방송 썸네일" 필드에 표시된 이미지 번호와 제공된 이미지 순서가 일치합니다.
                - 첫 번째 이미지는 "이미지_1"에 해당
                - 두 번째 이미지는 "이미지_2"에 해당
                - 이런 식으로 순서대로 매핑됩니다.

                각 하이라이트의 "하이라이트_ID"를 참조하여 해당하는 이미지를 분석해주세요.

                분석 데이터:
                {json.dumps(highlight_data, ensure_ascii=False, indent=2)}"""
            
            # 프롬프트와 모든 이미지를 순서대로 전송
            msg_list = [prompt] + images_with_labels
            
            print(f"{datetime.now()} 배치 분석 실행: 텍스트 데이터와 {len(images_with_labels)}개 이미지")

            # AI 모델 호출 (비동기)
            response = await asyncio.to_thread(model.generate_content, msg_list)

            # JSON 파싱
            try:
                timeline_comments = json.loads(response.text)
                if isinstance(timeline_comments, list):
                    # 시간순으로 정렬
                    timeline_comments.sort(key=lambda x: x.get('comment_after_openDate', ''))
                    print(f"{datetime.now()} AI 댓글 생성 완료: {len(timeline_comments)}개 댓글")
                    return timeline_comments
                else:
                    raise ValueError("응답이 리스트 형태가 아닙니다")

            except (json.JSONDecodeError, ValueError, KeyError) as e:
                print(f"{datetime.now()} AI JSON 파싱 오류: {e}")
                print(f"{datetime.now()} 응답 내용: {response.text[:500]}...")
                return []
                        
        except Exception as e:
            print(f"{datetime.now()} AI 타임라인 댓글 생성 오류: {e}")
            return []

    def _calculate_fun_score_from_diff(self, score_diff):
        """점수 차이를 기반으로 재미 점수 계산 (ChatAnalyzer와 동일한 로직)"""
        fun_score = 0
        thresholds = [15, 30, 40, 60, 70]
        
        for threshold in thresholds:
            if score_diff > threshold:
                fun_score += 1
        
        return fun_score

    async def _export_highlights_basic(self, session_logs, session_stats):
        """기본 로직을 사용한 하이라이트 댓글 생성"""
        from base import format_time_for_comment
        
        try:
            highlight_lines = []
            
            # 재미도 점수 기준점들 (VOD와 동일한 기준)
            fun_difference1 = 15
            fun_difference2 = 30
            fun_difference3 = 40
            fun_difference4 = 60
            fun_difference5 = 70
            
            for log in session_logs:
                score_components = log.get('score_components', {})
                
                # 하이라이트인지 확인
                if (score_components.get('highlights', False) and 
                    score_components.get('should_create_new_highlight', True)):
                    
                    after_open = log['comment_after_openDate']
                    after_open = format_time_for_comment(after_open, 25)
                    score_diff = score_components.get('score_difference', 0)
                    
                    # 재미 점수 계산 (VOD 시스템과 동일)
                    fun_score = 0
                    if score_diff > fun_difference1:
                        fun_score += 1
                    if score_diff > fun_difference2:
                        fun_score += 1
                    if score_diff > fun_difference3:
                        fun_score += 1
                    if score_diff > fun_difference4:
                        fun_score += 1
                    if score_diff > fun_difference5:
                        fun_score += 1
                    
                    # 간단한 설명 생성
                    analysis_data = log.get('analysis_data', {})
                    fun_keywords = analysis_data.get('fun_keywords', {})
                    message_count = analysis_data.get('message_count', 0)
                    
                    # 주요 반응 키워드 확인
                    main_reaction = ""
                    if fun_keywords.get('laugh', 0) >= max(message_count/3, 1):
                        main_reaction = "폭소"
                    elif fun_keywords.get('excitement', 0) >= max(message_count/3, 1):
                        main_reaction = "흥분"
                    elif fun_keywords.get('surprise', 0) >= max(message_count/3, 1):
                        main_reaction = "놀람"
                    elif score_components.get('chat_spike_score', 0) >= 50:
                        main_reaction = "채팅폭증"
                    else:
                        main_reaction = "재미구간"
                    
                    description = f"재미 점수:{fun_score} - {main_reaction}"
                    
                    # VOD 댓글 형식으로 라인 생성
                    highlight_lines.append(f"{after_open} - {description}")
            
            if not highlight_lines:
                return None
            
            # 자동 생성 안내 추가
            final_content = "\n\n".join(highlight_lines)
            
            # 파일 저장
            start_date = datetime.fromisoformat(session_stats['start_time']).strftime('%Y-%m-%d_%H%M')
            method_suffix = "_ai" if self.use_ai else "_basic"
            filename = f"{self.channel_name}_{start_date}_highlights{method_suffix}.txt"
            file_path = self.reports_dir / filename
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            print(f"하이라이트 텍스트 저장: {file_path}")
            
            return {
                'highlights_count': len(highlight_lines),
                'file_path': str(file_path),
                'method': 'ai' if self.use_ai else 'basic'
            }
            
        except Exception as e:
            print(f"{datetime.now()} 기본 하이라이트 텍스트 생성 중 오류: {e}")
            return None

    def create_session_summary(self, all_session_stats):
        """모든 세션의 요약 통계"""
        if not all_session_stats:
            return
        
        print(f"\n{'='*60}")
        print(f"전체 세션 요약 ({len(all_session_stats)}개 세션)")
        print(f"{'='*60}")
        
        # 총합/평균 계산 (원래 + test 비교)
        total_duration = sum([s['duration_hours'] for s in all_session_stats])
        total_highlights = sum([s['highlights'] for s in all_session_stats])
        total_big_highlights = sum([s['big_highlights'] for s in all_session_stats])
        total_test_highlights = sum([s['test_highlights'] for s in all_session_stats])
        total_test_big_highlights = sum([s['test_big_highlights'] for s in all_session_stats])

        # 평균 재미도 (가중 평균)
        avg_score_overall = sum([s['avg_score'] * s['total_analyses'] for s in all_session_stats]) / sum([s['total_analyses'] for s in all_session_stats])
        avg_test_score_overall = sum([s['avg_test_score'] * s['total_analyses'] for s in all_session_stats]) / sum([s['total_analyses'] for s in all_session_stats])
        
        print(f"이 방송 시간: {total_duration:.1f}시간")
        print(f"전체 평균 재미도: {avg_score_overall:.2f} (대조: Test {avg_test_score_overall:.2f})")
        print(f"이 하이라이트: {total_highlights}회 (대조: Test {total_test_highlights}회)")
        print(f"이 대형 하이라이트: {total_big_highlights}회 (대조: Test {total_test_big_highlights}회)")
        print(f"시간당 하이라이트: {total_highlights/total_duration:.1f}회/시간 (대조: Test {total_test_highlights/total_duration:.1f})")
        
        print(f"\n각 세션별 상세 비교:")
        # 헤더 확장 (평균점수, 하이라이트 수 -> 원 vs Test 비교)
        header = f"{'번호':>3} {'날짜':>8} {'시작시간':>6} {'길이':>6} " \
                f"{'평균점수':>8} {'Test평균':>9} " \
                f"{'HL':>5} {'TestHL':>7} " \
                f"{'대형HL':>6} {'Test대형':>8} "
        print(header)
        print(f"{'-'*len(header)}")
        
        # 각 세션별 출력
        for i, stats in enumerate(all_session_stats, 1):
            start_date = datetime.fromisoformat(stats['start_time']).strftime('%m/%d')
            start_time = datetime.fromisoformat(stats['start_time']).strftime('%H:%M')
            
            row = f"{i:>3} {start_date:>8} {start_time:>6} " \
                f"{stats['duration_hours']:>5.1f}h " \
                f"{stats['avg_score']:>8.1f} {stats['avg_test_score']:>9.1f} " \
                f"{stats['highlights']:>5} {stats['test_highlights']:>7} " \
                f"{stats['big_highlights']:>6} {stats['test_big_highlights']:>8}"
            print(row)
        
        # 요약 리포트를 파일로 저장
        self._save_summary_report(all_session_stats)
    
    def _save_summary_report(self, all_session_stats):
        """요약 리포트를 텍스트 파일로 저장"""
        if not all_session_stats:
            return
        
        # timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        start_date = datetime.fromisoformat(all_session_stats[0]['start_time']).strftime('%Y-%m-%d_%H%M')
        report_filename = f"{self.channel_name}_summary_report_{start_date}.txt"
        report_path = self.reports_dir / report_filename
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"방송 재미도 분석 리포트\n")
            f.write(f"채널: {self.channel_name}\n")
            f.write(f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n\n")
            
            total_duration = sum([s['duration_hours'] for s in all_session_stats])
            total_highlights = sum([s['highlights'] for s in all_session_stats])
            total_big_highlights = sum([s['big_highlights'] for s in all_session_stats])
            avg_score_overall = sum([s['avg_score'] * s['total_analyses'] for s in all_session_stats]) / sum([s['total_analyses'] for s in all_session_stats])
            
            f.write(f"전체 통계:\n")
            f.write(f"- 이 세션 수: {len(all_session_stats)}개\n")
            f.write(f"- 이 방송 시간: {total_duration:.1f}시간\n")
            f.write(f"- 전체 평균 재미도: {avg_score_overall:.2f}\n")
            f.write(f"- 이 하이라이트: {total_highlights}회\n")
            f.write(f"- 이 대형 하이라이트: {total_big_highlights}회\n")
            f.write(f"- 시간당 하이라이트: {total_highlights/total_duration:.1f}회/시간\n\n")
            
            f.write(f"세션별 상세:\n")
            # 헤더 수정
            header = f"{'번호':>4} {'날짜':>10} {'시작시간':>8} {'길이':>7} {'평균점수':>8} {'하이라이트':>8} {'대형':>4} {'최대시청':>8}"
            f.write(header + "\n")
            f.write(f"{'-'*len(header)}\n")
            
            # 각 세션 정보 출력 수정
            for i, stats in enumerate(all_session_stats, 1):
                start_date = datetime.fromisoformat(stats['start_time']).strftime('%m/%d')
                start_time = datetime.fromisoformat(stats['start_time']).strftime('%H:%M')
                
                row = f"{i:>4} {start_date:>10} {start_time:>8} " \
                    f"{stats['duration_hours']:>6.1f}h {stats['avg_score']:>7.1f} " \
                    f"{stats['highlights']:>7}회 {stats['big_highlights']:>3}회 " \
                    f"{stats['max_viewers']:>7}명"
                f.write(row + "\n")
        
        print(f"📄 요약 리포트 저장: {report_path}")
    
    async def full_session_analysis(self):
        """전체 세션별 분석 실행"""
        print("🔍 세션별 재미도 로그 분석을 시작합니다...")
        
        # 로그 로드
        logs = self.load_all_logs()
        if not logs:
            print("❌ 분석할 로그가 없습니다.")
            return
        
        # 시간순 정렬
        logs.sort(key=lambda x: x['timestamp'])
        
        # 세션 구분
        sessions = self.detect_session_breaks(logs)
        print(f"\n📢 총 {len(sessions)}개 세션이 감지되었습니다.")
        
        all_session_stats = []
        
        # 각 세션별 분석
        for date_str, session_logs in sessions:
            if not self.date == "모든 날짜" and not self.date == date_str:
                continue
            
            print(f"\n{'='*50}")
            print(f"📅 {date_str} 분석 중... ({len(session_logs)}개 로그)")
            
            # 세션 통계 계산
            session_stats = self.analyze_session(session_logs, date_str)
            all_session_stats.append(session_stats)
            
            # 세션 정보 출력
            print(f"⏰ 시작: {session_stats['start_time']} ({session_stats['start_after_open']})")
            print(f"⏰ 종료: {session_stats['end_time']} ({session_stats['end_after_open']})")
            print(f"📊 지속 시간: {session_stats['duration_hours']:.1f}시간")
            print(f"📈 평균 재미도: {session_stats['avg_score']:.2f}")
            print(f"🔥 최고 재미도: {session_stats['max_score']:.2f}")
            print(f"⭐ 하이라이트: {session_stats['highlights']}회 ({session_stats['highlight_rate']:.1f}%)")
            print(f"🌟 대형 하이라이트: {session_stats['big_highlights']}회 ({session_stats['big_highlight_rate']:.1f}%)")
            print(f"👥 최대 시청자: {session_stats['max_viewers']}명")
            
            # CSV 내보내기
            csv_file = self.export_session_to_csv(session_logs, session_stats)

            # 하이라이트 텍스트 파일 생성
            await self.export_highlights_to_text(session_logs, session_stats)
            
            # 그래프 생성
            try:
                self.create_session_plot(session_logs, session_stats)
            except Exception as e:
                print(f"❌ 그래프 생성 실패: {e}")
        
        # 전체 요약
        self.create_session_summary(all_session_stats)
        
        # 전체 세션 요약 CSV
        if all_session_stats:
            summary_df = pd.DataFrame(all_session_stats)
            start_date = datetime.fromisoformat(all_session_stats[0]['start_time']).strftime('%Y-%m-%d_%H%M')
            summary_filename = f"{self.channel_name}_summary_{start_date}.csv"
            
            # csv 디렉토리에 저장
            summary_path = self.csv_dir / summary_filename
            summary_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
            print(f"💾 세션 요약 CSV 저장: {summary_path}")
        
        return sessions

def parse_arguments():
    """명령행 인자를 파싱하는 함수"""
    parser = argparse.ArgumentParser(
        description='방송 세션별 재미도 로그 분석 도구',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python3 py/log_analyzer.py                    # 기본 설정으로 실행
  python3 py/log_analyzer.py 빅헤드             # 특정 채널 분석
  python3 py/log_analyzer.py --channel 빅헤드 --date 2025-09-06  # 특정 날짜 분석
  python3 py/log_analyzer.py --use-ai           # AI 기반 댓글 생성 사용
        """
    )
    
    # 위치 인자: 채널명 (선택사항)
    parser.add_argument(
        'channel_name',
        nargs='?',  # 선택적 위치 인자
        default='빅헤드',
        help='분석할 채널명 (기본값: 빅헤드)'
    )
    
    # 선택적 인자들
    parser.add_argument(
        '--channel',
        help='분석할 채널명 (위치 인자 대신 사용 가능)'
    )

    parser.add_argument(
        '--date',
        default='모든 날짜',
        help='분석할 날짜 지정 (YYYY-MM-DD 형태, 기본값: 모든 날짜)'
    )
    
    # AI 사용 여부 옵션 (기본값: False)
    parser.add_argument(
        '--use-ai',
        action='store_true',
        default=False,
        help='하이라이트 댓글 생성 시 AI 사용 (기본값: 사용하지 않음)'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='Stream Alert Analyzer 2.0'
    )
    
    return parser.parse_args()

async def main():
    """메인 실행 함수"""
    try:
        # 명령행 인자 파싱
        try:
            args = parse_arguments()
        
            # 채널명 결정
            channel_name = args.channel if args.channel else args.channel_name
            date = args.date if args.date != '모든 날짜' else '모든 날짜'
            use_ai = args.use_ai

        except:
            channel_name, date, use_ai = "빅헤드", '2025-10-04', False
        
        # AI 사용 가능 여부 확인
        if use_ai and not AI_AVAILABLE:
            print(f"경고: AI 기능을 사용할 수 없습니다. 필요한 모듈이 없습니다.")
            print(f"기본 로직으로 진행합니다.")
            use_ai = False
        
        print(f"=== Stream Alert 재미도 로그 분석 시작 ===")
        print(f"채널명: {channel_name}")
        print(f"분석할 날짜: {date}")
        print(f"AI 사용: {'예' if use_ai else '아니오'}")
        if use_ai:
            print(f"AI 모델: Gemini 2.0 Flash (base.py에서 로드)")
        print("="*60)
        
        # 분석기 생성 및 실행
        analyzer = SessionBasedFunScoreAnalyzer(channel_name, date, use_ai=use_ai)
        sessions = await analyzer.full_session_analysis()
        
        if sessions:
            filtered_sessions = [s for date_str, s in sessions if date == "모든 날짜" or date == date_str]
            print(f"\n분석 완료! {len(filtered_sessions)}개 세션을 분석했습니다.")
            print(f"결과 파일들이 output/ 폴더에 저장되었습니다.")
            if use_ai:
                print(f"AI 기반 자연스러운 댓글이 생성되었습니다.")
        else:
            print("\n분석할 데이터가 없습니다.")
            
    except KeyboardInterrupt:
        print("\n\n사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n예상치 못한 오류가 발생했습니다: {e}")
        print("문제가 지속되면 개발자에게 문의해주세요.")
        sys.exit(1)

# 스크립트가 직접 실행될 때만 main() 함수 호출
if __name__ == "__main__":
    asyncio.run(main())