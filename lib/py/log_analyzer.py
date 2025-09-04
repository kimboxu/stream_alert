import json
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
import glob

class FunScoreLogAnalyzer:
    """저장된 재미도 로그 파일을 분석하는 클래스"""
    
    def __init__(self, log_dir="fun_score_logs"):
        self.log_dir = log_dir
        
    def load_log_file(self, filename):
        """단일 로그 파일 로드"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data['logs']
        except Exception as e:
            print(f"파일 로드 오류: {e}")
            return []
    
    def load_all_logs(self, channel_name=None):
        """모든 로그 파일을 로드하여 합치기"""
        pattern = f"{self.log_dir}/fun_score_detailed_"
        if channel_name:
            pattern += f"{channel_name}_"
        pattern += "*.json"
        
        files = glob.glob(pattern)
        all_logs = []
        
        for file in sorted(files):
            logs = self.load_log_file(file)
            all_logs.extend(logs)
            print(f"로드: {file} ({len(logs)}개)")
        
        print(f"총 {len(files)}개 파일에서 {len(all_logs)}개 로그 로드됨")
        return all_logs
    
    def analyze_basic_stats(self, logs):
        """기본 통계 분석"""
        if not logs:
            print("분석할 로그가 없습니다.")
            return {}
        
        scores = [log['fun_score'] for log in logs]
        
        # 시간 정보
        start_time = logs[0]['timestamp']
        end_time = logs[-1]['timestamp']
        
        # 점수 통계
        stats = {
            'period': f"{start_time} ~ {end_time}",
            'total_analyses': len(logs),
            'avg_score': sum(scores) / len(scores),
            'max_score': max(scores),
            'min_score': min(scores),
            'highlights': len([s for s in scores if s >= 50]),
            'big_highlights': len([s for s in scores if s >= 80])
        }
        
        print(f"\n=== 기본 통계 ===")
        print(f"분석 기간: {stats['period']}")
        print(f"총 분석 횟수: {stats['total_analyses']}")
        print(f"평균 재미도: {stats['avg_score']:.2f}")
        print(f"최고 재미도: {stats['max_score']:.2f}")
        print(f"최저 재미도: {stats['min_score']:.2f}")
        print(f"하이라이트: {stats['highlights']}회 ({stats['highlights']/len(logs)*100:.1f}%)")
        print(f"대형 하이라이트: {stats['big_highlights']}회 ({stats['big_highlights']/len(logs)*100:.1f}%)")
        
        return stats
    
    def analyze_score_components(self, logs):
        """점수 구성 요소 분석 - 새로운 구조에 맞게 수정"""
        if not logs:
            return
        
        # 새로운 구조에서는 score_components에 다른 필드들이 있음
        try:
            # 첫 번째 로그의 구조 확인
            first_log = logs[0]
            print(f"\n=== 로그 구조 확인 ===")
            print(f"Score components keys: {list(first_log['score_components'].keys())}")
            
            # 새로운 구조에 맞는 분석
            engagement_scores = [log['score_components'].get('engagement_score', 0) for log in logs]
            reaction_scores = [log['score_components'].get('reaction_score', 0) for log in logs]
            diversity_scores = [log['score_components'].get('diversity_score', 0) for log in logs]
            chat_spike_scores = [log['score_components'].get('chat_spike_score', 0) for log in logs]
            viewer_trend_scores = [log['score_components'].get('viewer_trend_score', 0) for log in logs]
            
            print(f"\n=== 새로운 점수 구성 요소 분석 ===")
            print(f"참여도 점수: 평균 {sum(engagement_scores)/len(engagement_scores):.2f}/100 (최대 {max(engagement_scores):.1f})")
            print(f"반응 강도 점수: 평균 {sum(reaction_scores)/len(reaction_scores):.2f}/100 (최대 {max(reaction_scores):.1f})")
            print(f"다양성 점수: 평균 {sum(diversity_scores)/len(diversity_scores):.2f}/100 (최대 {max(diversity_scores):.1f})")
            print(f"채팅 급증 점수: 평균 {sum(chat_spike_scores)/len(chat_spike_scores):.2f}/100 (최대 {max(chat_spike_scores):.1f})")
            print(f"시청자 증가 점수: 평균 {sum(viewer_trend_scores)/len(viewer_trend_scores):.2f}/80 (최대 {max(viewer_trend_scores):.1f})")
            
            # 각 구성요소의 전체 점수 기여도
            total_engagement = sum(engagement_scores)
            total_reaction = sum(reaction_scores)
            total_diversity = sum(diversity_scores)
            total_chat_spike = sum(chat_spike_scores)
            total_viewer_trend = sum(viewer_trend_scores)
            grand_total = total_engagement + total_reaction + total_diversity + total_chat_spike + total_viewer_trend
            
            if grand_total > 0:
                print(f"\n=== 구성 요소별 기여도 ===")
                print(f"참여도: {total_engagement/grand_total*100:.1f}%")
                print(f"반응 강도: {total_reaction/grand_total*100:.1f}%")
                print(f"다양성: {total_diversity/grand_total*100:.1f}%")
                print(f"채팅 급증: {total_chat_spike/grand_total*100:.1f}%")
                print(f"시청자 증가: {total_viewer_trend/grand_total*100:.1f}%")
            
        except KeyError as e:
            print(f"로그 구조 오류: {e}")
            print("기존 구조로 분석을 시도합니다...")
            
            # 기존 구조 분석 시도
            try:
                velocity_scores = [log['score_components'].get('chat_velocity_score', 0) for log in logs]
                keyword_scores = [log['score_components'].get('keyword_score', 0) for log in logs]
                participation_scores = [log['score_components'].get('participation_score', 0) for log in logs]
                diversity_scores = [log['score_components'].get('diversity_score', 0) for log in logs]
                chat_bonuses = [log['score_components'].get('chat_spike_bonus', 0) for log in logs]
                viewer_bonuses = [log['score_components'].get('viewer_spike_bonus', 0) for log in logs]
                
                print(f"\n=== 기존 점수 구성 요소 분석 ===")
                print(f"채팅 속도 점수: 평균 {sum(velocity_scores)/len(velocity_scores):.2f} (최대 {max(velocity_scores):.1f})")
                print(f"키워드 점수: 평균 {sum(keyword_scores)/len(keyword_scores):.2f} (최대 {max(keyword_scores):.1f})")
                print(f"참여도 점수: 평균 {sum(participation_scores)/len(participation_scores):.2f} (최대 {max(participation_scores):.1f})")
                print(f"다양성 점수: 평균 {sum(diversity_scores)/len(diversity_scores):.2f} (최대 {max(diversity_scores):.1f})")
                print(f"채팅 급증 보너스: 평균 {sum(chat_bonuses)/len(chat_bonuses):.2f} (최대 {max(chat_bonuses):.1f})")
                print(f"시청자 급증 보너스: 평균 {sum(viewer_bonuses)/len(viewer_bonuses):.2f} (최대 {max(viewer_bonuses):.1f})")
                
            except Exception as e2:
                print(f"기존 구조 분석도 실패: {e2}")
    
    def analyze_keywords(self, logs):
        """키워드 분석 - 새로운 구조에 맞게 수정"""
        if not logs:
            return
        
        try:
            # 새로운 구조: reaction_keyword_breakdown
            laugh_total = sum(log['score_components'].get('reaction_keyword_breakdown', {}).get('laugh', 0) for log in logs)
            excitement_total = sum(log['score_components'].get('reaction_keyword_breakdown', {}).get('excitement', 0) for log in logs)
            surprise_total = sum(log['score_components'].get('reaction_keyword_breakdown', {}).get('surprise', 0) for log in logs)
            reaction_total = sum(log['score_components'].get('reaction_keyword_breakdown', {}).get('reaction', 0) for log in logs)
            
        except:
            # 기존 구조: keyword_breakdown
            try:
                laugh_total = sum(log['score_components'].get('keyword_breakdown', {}).get('laugh', 0) for log in logs)
                excitement_total = sum(log['score_components'].get('keyword_breakdown', {}).get('excitement', 0) for log in logs)
                surprise_total = sum(log['score_components'].get('keyword_breakdown', {}).get('surprise', 0) for log in logs)
                reaction_total = sum(log['score_components'].get('keyword_breakdown', {}).get('reaction', 0) for log in logs)
            except:
                print("키워드 데이터를 찾을 수 없습니다.")
                return
        
        print(f"\n=== 키워드 분석 ===")
        print(f"웃음 키워드: 총 {laugh_total}개 (평균 {laugh_total/len(logs):.2f}/회)")
        print(f"흥분 키워드: 총 {excitement_total}개 (평균 {excitement_total/len(logs):.2f}/회)")
        print(f"놀라움 키워드: 총 {surprise_total}개 (평균 {surprise_total/len(logs):.2f}/회)")
        print(f"반응 키워드: 총 {reaction_total}개 (평균 {reaction_total/len(logs):.2f}/회)")
    
    def find_peak_moments(self, logs, top_n=10):
        """최고 재미도 순간 찾기"""
        if not logs:
            return
        
        # 점수순으로 정렬
        sorted_logs = sorted(logs, key=lambda x: x['fun_score'], reverse=True)
        
        print(f"\n=== TOP {top_n} 재미 순간 ===")
        for i, log in enumerate(sorted_logs[:top_n]):
            timestamp = datetime.fromisoformat(log['timestamp']).strftime('%m/%d %H:%M:%S')
            score = log['fun_score']
            messages = log.get('sample_messages', ['샘플 없음'])
            recent_msg = messages[-1] if messages else '메시지 없음'
            
            print(f"{i+1:2d}. [{timestamp}] 점수: {score:5.1f} | 최근 채팅: {recent_msg}")
    
    def analyze_time_patterns(self, logs):
        """시간대별 패턴 분석"""
        if not logs:
            return
        
        # 시간대별 그룹화
        hourly_scores = {}
        for log in logs:
            hour = datetime.fromisoformat(log['timestamp']).hour
            if hour not in hourly_scores:
                hourly_scores[hour] = []
            hourly_scores[hour].append(log['fun_score'])
        
        print(f"\n=== 시간대별 평균 재미도 ===")
        for hour in sorted(hourly_scores.keys()):
            scores = hourly_scores[hour]
            avg_score = sum(scores) / len(scores)
            highlights = len([s for s in scores if s >= 50])
            print(f"{hour:2d}시: 평균 {avg_score:5.1f} (분석 {len(scores):3d}회, 하이라이트 {highlights:2d}회)")
    
    def export_to_csv(self, logs, filename=None):
        """로그를 CSV로 내보내기 - 새로운 구조에 맞게 수정"""
        if not logs:
            print("내보낼 데이터가 없습니다.")
            return
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"fun_score_analysis_{timestamp}.csv"
        
        # DataFrame 생성
        data = []
        for log in logs:
            try:
                # 새로운 구조에 맞는 데이터 추출
                row = {
                    'timestamp': log['timestamp'],
                    'fun_score': log['fun_score'],
                    'message_count': log['analysis_data']['message_count'],
                    'viewer_count': log['analysis_data']['viewer_count'],
                    'chat_velocity': log['analysis_data']['chat_velocity'],
                    
                    # 새로운 구조의 점수들
                    'engagement_score': log['score_components'].get('engagement_score', 0),
                    'reaction_score': log['score_components'].get('reaction_score', 0),
                    'diversity_score': log['score_components'].get('diversity_score', 0),
                    'chat_spike_score': log['score_components'].get('chat_spike_score', 0),
                    'viewer_trend_score': log['score_components'].get('viewer_trend_score', 0),
                    
                    # 기준값들
                    'baseline_chat_count': log['score_components'].get('baseline_chat_count', 0),
                    'baseline_chat_velocity': log['score_components'].get('baseline_chat_velocity', 0),
                    'baseline_viewer_count': log['score_components'].get('baseline_viewer_count', 0),
                    'threshold': log['score_components'].get('threshold', 50),
                    
                    # 키워드 데이터
                    'laugh_count': log['score_components'].get('reaction_keyword_breakdown', {}).get('laugh', 0),
                    'excitement_count': log['score_components'].get('reaction_keyword_breakdown', {}).get('excitement', 0),
                    'surprise_count': log['score_components'].get('reaction_keyword_breakdown', {}).get('surprise', 0),
                    'reaction_count': log['score_components'].get('reaction_keyword_breakdown', {}).get('reaction', 0)
                }
                
            except KeyError:
                # 기존 구조로 대체
                row = {
                    'timestamp': log['timestamp'],
                    'fun_score': log['fun_score'],
                    'message_count': log['analysis_data']['message_count'],
                    'viewer_count': log['analysis_data']['viewer_count'],
                    'chat_velocity': log['analysis_data']['chat_velocity'],
                    'velocity_score': log['score_components'].get('chat_velocity_score', 0),
                    'keyword_score': log['score_components'].get('keyword_score', 0),
                    'participation_score': log['score_components'].get('participation_score', 0),
                    'diversity_score': log['score_components'].get('diversity_score', 0),
                    'chat_spike_bonus': log['score_components'].get('chat_spike_bonus', 0),
                    'viewer_spike_bonus': log['score_components'].get('viewer_spike_bonus', 0),
                    'laugh_count': log['score_components'].get('keyword_breakdown', {}).get('laugh', 0),
                    'excitement_count': log['score_components'].get('keyword_breakdown', {}).get('excitement', 0),
                    'surprise_count': log['score_components'].get('keyword_breakdown', {}).get('surprise', 0),
                    'reaction_count': log['score_components'].get('keyword_breakdown', {}).get('reaction', 0)
                }
            
            data.append(row)
        
        df = pd.DataFrame(data)
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"CSV 저장 완료: {filename} ({len(df)}행)")
        return filename
    
    def create_simple_plot(self, logs, save_plot=True):
        """간단한 점수 변화 그래프"""
        if not logs:
            return
        
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            import platform
            
            # 한글 폰트 설정
            plt.rcParams['font.family'] = ['DejaVu Sans']
            if platform.system() == 'Windows':
                plt.rcParams['font.family'] = ['Malgun Gothic', 'DejaVu Sans']
            elif platform.system() == 'Darwin':  # macOS
                plt.rcParams['font.family'] = ['AppleGothic', 'DejaVu Sans']
            else:  # Linux
                plt.rcParams['font.family'] = ['Noto Sans CJK KR', 'DejaVu Sans']
            
            plt.rcParams['axes.unicode_minus'] = False  # 마이너스 기호 깨짐 방지
            
            # 데이터 준비
            times = [datetime.fromisoformat(log['timestamp']) for log in logs]
            scores = [log['fun_score'] for log in logs]
            
            # 그래프 생성
            plt.figure(figsize=(15, 6))
            plt.plot(times, scores, 'b-', alpha=0.7, linewidth=1)
            plt.axhline(y=50, color='orange', linestyle='--', alpha=0.7, label='하이라이트 임계값')
            plt.axhline(y=80, color='red', linestyle='--', alpha=0.7, label='대형 하이라이트 임계값')
            
            plt.title('재미도 점수 변화')
            plt.xlabel('시간')
            plt.ylabel('재미도 점수')
            plt.legend()
            plt.grid(True, alpha=0.3)
            
            # x축 포맷팅
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
            plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=6))
            plt.xticks(rotation=45)
            
            plt.tight_layout()
            
            if save_plot:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"fun_score_plot_{timestamp}.png"
                plt.savefig(filename, dpi=150, bbox_inches='tight')
                print(f"그래프 저장: {filename}")
            
            plt.show()
            
        except ImportError:
            print("matplotlib가 설치되지 않아 그래프를 생성할 수 없습니다.")
    
    def full_analysis(self, channel_name=None):
        """전체 분석 실행"""
        print("재미도 로그 분석을 시작합니다...")
        
        # 로그 로드
        logs = self.load_all_logs(channel_name)
        
        if not logs:
            print("분석할 로그가 없습니다.")
            return
        
        # 각종 분석 실행
        self.analyze_basic_stats(logs)
        self.analyze_score_components(logs)
        self.analyze_keywords(logs)
        self.find_peak_moments(logs)
        self.analyze_time_patterns(logs)
        
        # CSV 내보내기
        csv_file = self.export_to_csv(logs)
        
        # 그래프 생성 (선택사항)
        try:
            self.create_simple_plot(logs)
        except:
            print("그래프 생성을 건너뜁니다.")
        
        print(f"\n분석 완료! CSV 파일: {csv_file}")
        return logs


# 사용 예시
if __name__ == "__main__":
    # 분석기 생성
    analyzer = FunScoreLogAnalyzer("fun_score_logs")
    
    # 전체 분석 실행
    analyzer.full_analysis("지누")
    
    # 또는 특정 파일만 분석
    # logs = analyzer.load_log_file("fun_score_logs/fun_score_detailed_채널명_20250903_143022.json")
    # analyzer.analyze_basic_stats(logs)