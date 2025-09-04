import asyncio
import re
import json
import statistics
from math import exp, floor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import deque, Counter
from os import environ, path, makedirs
import pandas as pd
from uuid import uuid4
from live_message import upload_image_to_imgur
from base import log_error, if_after_time, changeUTCtime, iconLinkData, initVar
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from notification_service import send_push_notification

@dataclass
class ChatAnalysisData:
    """채팅 분석 데이터를 저장하는 클래스"""
    timestamp: datetime
    openDate: datetime
    message_count: int = 0
    viewer_count: int = 0
    fun_keywords: Dict[str, int] = field(default_factory=dict)
    chat_velocity: float = 0.0  # 채팅 속도 (메시지/초)

@dataclass
class StreamHighlight:
    """하이라이트 순간 정보"""
    timestamp: datetime
    channel_id: str
    channel_name: str
    fun_score: float
    reason: str
    chat_context: List[str]
    viewer_count: int
    duration: int  # seconds
    after_openDate: datetime
    score_details: dict

class ChatMessageWithAnalyzer:
    def setup_analyzer(self, channel_id: str, channel_name: str):
        """분석기 초기화"""
        self.chat_analyzer = ChatAnalyzer(self.init, channel_id, channel_name)
        self.analysis_task = None
        self.log_save_task = None

    async def start_analyzer(self):
        """분석기 시작 - start() 메서드에서 호출"""
        if not self.analysis_task or self.analysis_task.done():
            self.analysis_task = asyncio.create_task(self._run_analyzer())
            print(f"채팅 분석기 시작: {self.chat_analyzer.channel_name}")

            # 주기적 로그 저장 태스크 시작
            self.log_save_task = asyncio.create_task(self.chat_analyzer.save_logs_periodically())
            print(f"로그 저장 태스크 시작: 30분마다 자동 저장")

    async def stop_analyzer(self):
        """분석기 중지"""
        # 분석 태스크 중지
        if self.analysis_task and not self.analysis_task.done():
            self.analysis_task.cancel()
        
        # 로그 저장 태스크 중지
        if self.log_save_task and not self.log_save_task.done():
            self.log_save_task.cancel()
            
        try:
            await self.analysis_task
        except asyncio.CancelledError:
            pass
            
        try:
            await self.log_save_task
        except asyncio.CancelledError:
            pass
        
        # 종료 전 마지막 로그 저장
        await self.chat_analyzer.save_detailed_logs_to_file(force_save=True)
        print(f"종료 시 최종 로그 저장 완료: {self.chat_analyzer.channel_name}")

    # 편의 메서드들
    async def save_current_logs(self):
        """현재 로그 즉시 저장"""
        await self.chat_analyzer.save_detailed_logs_to_file(force_save=True)
    
    def export_analysis_csv(self, hours=24):
        """분석 데이터 CSV로 내보내기"""
        return self.chat_analyzer.export_logs_to_csv(hours)
    
    def analyze_log_file(self, filename):
        """저장된 로그 파일 분석"""
        self.chat_analyzer.analyze_saved_logs(filename)

    async def _run_analyzer(self):
        """주기적인 분석 실행"""
        while True:
            try:
                # 5초마다 분석
                await asyncio.sleep(self.chat_analyzer.analysis_interval) 

                # 분석 실행
                result = await self.chat_analyzer.analyze()

                if result:
                    fun_score, analysis, score_details = result
                    print(f"{datetime.now()} {self.chat_analyzer.channel_name}, 재미도 점수: {fun_score}\n디테일 점수{score_details}")
                      
            except asyncio.CancelledError:
                break

            except Exception as e:
                await log_error(f"분석기 실행 오류: {e}")
                await asyncio.sleep(10)  # 오류시 10초 대기

class ChatAnalyzer:
    """채팅 데이터를 분석하여 재미있는 순간을 감지하는 클래스"""
    def __init__(self, init: initVar, channel_id: str, channel_name: str = ""):
        self.init = init
        self.channel_id = channel_id
        self.channel_name = channel_name

        # 분석 설정
        self.window_size = 30  # 30초 윈도우
        self.analysis_interval = 5  # 5초마다 분석

        # 채팅 데이터 저장 (약 30분)
        self.history_1min = int(60/self.analysis_interval)
        self.chat_buffer = deque(maxlen=3600)  # 30분 분량
        self.analysis_history = deque(maxlen= self.history_1min * 30)  # 30분간 분석 결과

        # 재미 키워드 패턴 (한국어 최적화)
        self.fun_patterns = {
        'laugh': re.compile(r'ㅋ{2,}|ㅎ{2,}|하하|ㅏㅏ|캬|푸하|풉|웃겨|개웃|존웃'),
        'excitement': re.compile(r'!{2,}|\?{2,}|ㄷㄷ|헐|대박|와|오|우와|미친|ㅁㅊ|개쩔|쩐다|ㄱㄱ|고고|가즈아'),
        'surprise': re.compile(r'헉|뭣|뭐야|어떻게|진짜|실화|레전드|띠용|충격|놀람|ㄴㅇㅅ|지리네'),
        'reaction': re.compile(r'ㅠㅠ|ㅜㅜ|아니|안돼|제발|부탁|응원'),
        }

        # 가중 평균으로 최종 점수
        self.weights = {
            'engagement': 0.30,     # 참여도 가중치 증가
            'reaction': 0.30,       # 반응 강도 가중치 증가
            'diversity': 0.15,      # 다양성 유지
            'chat_spike': 0.15,     # 채팅 급증 
            'viewer_spike': 0.10,   # 시청자 급증 
        }

        # 하이라이트 저장
        self.highlights: List[StreamHighlight] = []
        self.last_analysis_time = datetime.now()

        # 임계값 설정
        self.small_fun_threshold    = 50    # 작은 재미
        self.big_fun_threshold      = 80    # 큰 재미

        # 로그 파일 설정
        self.detailed_logs = []  # 상세 분석 로그
        self.log_dir = "fun_score_logs"
        self.create_log_directory()
        
    def create_log_directory(self):
        """로그 디렉터리 생성"""
        if not path.exists(self.log_dir):
            makedirs(self.log_dir)

    async def add_chat_message(self, nickname: str, message: str, timestamp: Optional[datetime] = None) -> None:
        """채팅 메시지 추가"""
        if timestamp is None:
            timestamp = datetime.now()

        # 키워드 추출
        keywords = self._extract_keywords(message)

        # 채팅 데이터 저장
        chat_data = {
        'timestamp': timestamp,
        'nickname': nickname,
        'message': message,
        'keywords': keywords,
        'keyword_count': sum(keywords.values())
        }

        self.chat_buffer.append(chat_data)

    def _extract_keywords(self, message: str) -> Dict[str, int]:
        """메시지에서 재미 키워드 추출"""
        keywords = {}

        for pattern_name, pattern in self.fun_patterns.items():
            matches = pattern.findall(message.lower())
            if matches:
                keywords[pattern_name] = len(matches)
                
        return keywords
    
    async def analyze(self) -> Optional[Tuple[float, ChatAnalysisData]]:
        """현재 시점 분석 수행"""
        current_time = datetime.now()
        self.last_analysis_time = current_time

        # 윈도우 시작 시간
        window_start = current_time - timedelta(seconds=self.window_size)

        # 윈도우 내 채팅 필터링
        window_chats = [
            chat for chat in self.chat_buffer
            if chat['timestamp'] >= window_start
        ]

        if not window_chats:
            return None
        
        viewer_count = self.init.stream_status[self.channel_id].view_count

        # 분석 데이터 생성
        analysis = ChatAnalysisData(
            timestamp=current_time,
            openDate=self.init.stream_status[self.channel_id].state_update_time['openDate'],
            message_count=len(window_chats),
            viewer_count=viewer_count,
            chat_velocity=len(window_chats) / self.window_size,
        )

        # 키워드 집계
        keyword_counter = Counter()
        for chat in window_chats:
            for key, count in chat['keywords'].items():
                keyword_counter[key] += count

        analysis.fun_keywords = dict(keyword_counter)

        # 상세 점수 계산
        fun_score, check_create_highlight, score_details = self._calculate_fun_score(analysis, window_chats)
        
        # 상세 로그 저장
        detailed_log = {
            'timestamp': current_time.isoformat(),
            'fun_score': fun_score,
            'score_components': score_details,
            'analysis_data': {
                'message_count': analysis.message_count,
                'viewer_count': analysis.viewer_count,
                'chat_velocity': analysis.chat_velocity,
                'fun_keywords': analysis.fun_keywords
            },
            'sample_messages': [chat['message'] for chat in window_chats[-5:]]  # 최근 5개 메시지
        }
        
        self.detailed_logs.append(detailed_log)
        # 최대 2000개까지만 보관
        if len(self.detailed_logs) > 2000:
            self.detailed_logs = self.detailed_logs[-2000:]

        # 하이라이트 체크
        if fun_score >= self.small_fun_threshold and check_create_highlight:
            await self._create_highlight(analysis, fun_score, score_details, window_chats)

        # 분석 기록 저장
        self.analysis_history.append((current_time, analysis, fun_score))

        return fun_score, analysis, score_details
    
    # def _calculate_fun_score(self, analysis: ChatAnalysisData, window_chats: List[Dict]) -> float:
    #     """재미도 점수를 세부 구성 요소와 함께 계산"""
    #     score_details = {
    #         'chat_velocity_score': 0,
    #         'keyword_score': 0,
    #         'diversity_score': 0,
    #         'participation_score': 0,
    #         'chat_spike_bonus': 0,
    #         'viewer_spike_bonus': 0,
    #         'keyword_breakdown': {
    #             'laugh': analysis.fun_keywords.get('laugh', 0),
    #             'excitement': analysis.fun_keywords.get('excitement', 0),
    #             'surprise': analysis.fun_keywords.get('surprise', 0),
    #             'reaction': analysis.fun_keywords.get('reaction', 0)
    #         }
    #     }
        
    #     score = 0.0
    #     check_create_highlight = False

    #     # 1. 채팅 속도 점수 (최대 15점)
    #     chat_velocity_score = min(analysis.chat_velocity * 5, 15)
    #     score += chat_velocity_score
    #     score_details['chat_velocity_score'] = chat_velocity_score

    #     # 2. 키워드 점수 (최대 30점)
    #     keyword_score = 0
    #     keyword_score += analysis.fun_keywords.get('laugh', 0) * 3.0
    #     keyword_score += analysis.fun_keywords.get('excitement', 0) * 2.0
    #     keyword_score += analysis.fun_keywords.get('surprise', 0) * 2.0
    #     keyword_score += analysis.fun_keywords.get('reaction', 0) * 1.0
    #     keyword_score = min(keyword_score, 30)
    #     score += keyword_score
    #     score_details['keyword_score'] = keyword_score

    #     # 3. 메시지 길이 다양성 (최대 5점)
    #     if window_chats:
    #         msg_lengths = [len(chat['message']) for chat in window_chats]
    #         if len(msg_lengths) > 1:
    #             if len(msg_lengths) >= 2:
    #                 diversity = min(statistics.stdev(msg_lengths) / 10, 5)
    #                 score += diversity
    #                 score_details['diversity_score'] = diversity

    #     # 4. 채팅 작성자 수 (최대 10점)
    #     if window_chats:
    #         unique_users = len(set(chat['nickname'] for chat in window_chats))
    #         participation_score = min(unique_users / self.window_size * 10, 10)
    #         score += participation_score
    #         score_details['participation_score'] = participation_score

    #     # 5. 급증 보너스 (최대 40점)
    #     if len(self.analysis_history) >= 30:
    #         recent_analyses = list(self.analysis_history)[-30:]
    #         avg_recent_views = sum(a[1].viewer_count for a in recent_analyses) / len(recent_analyses)
            
    #         # 채팅 수 급증
    #         chat_spike_bonus = self.calculate_improved_chat_spike_bonus(analysis, recent_analyses)
    #         score += chat_spike_bonus
    #         score_details['chat_spike_bonus'] = chat_spike_bonus

    #         # 시청자 수 급증
    #         if avg_recent_views > 0:
    #             spike_ratio = analysis.viewer_count / avg_recent_views
    #             if spike_ratio > 1.0:
    #                 viewer_spike_bonus = min((spike_ratio - 1) * 10, 10)
    #                 score += viewer_spike_bonus
    #                 score_details['viewer_spike_bonus'] = viewer_spike_bonus
        
    #     # 하이라이트 생성 조건 확인
    #     if len(self.analysis_history) >= 10:
    #         recent_analyses = list(self.analysis_history)[-10:]
    #         max_recent_score = max(a[2] for a in recent_analyses)

    #         if score >= max_recent_score and self.check_bef_recent_scores(score): 
    #             check_create_highlight = True

    #     return min(score, 100), check_create_highlight, score_details
    
    #재미도 점수 계산
    def _calculate_fun_score(self, analysis: ChatAnalysisData, window_chats: List[Dict]) -> Tuple[float, bool, dict]:
        # 적응형 기준값 초기화
        if not hasattr(self, 'baseline_metrics'):
            self.baseline_metrics = {
                'avg_chat_count': 10.0,
                'avg_chat_velocity': 1.0,
                'avg_viewer_count': 100.0,
            }
        
        # 기준값 자동 업데이트
        self._update_baselines()
        
        # 1. 참여도 점수 (30% 가중치) - 최대 100점
        engagement_score = self._calculate_engagement_score(analysis)
            
        # 2. 반응 강도 점수 (30% 가중치) - 최대 100점
        reaction_score = self._calculate_reaction_score(analysis)
        
        # 3. 다양성 점수 (15% 가중치) - 최대 100점    
        diversity_score = self._calculate_diversity_score(window_chats)
        
        # 4. 급증 점수 (30% 가중치) - 최대 100점
        chat_spike_score = self._calculate_chat_spike_score(analysis)

        viewer_trend_score = self._calculate_viewer_trend_score(analysis)

        final_score = (
            engagement_score * self.weights['engagement'] +
            reaction_score * self.weights['reaction'] +
            diversity_score * self.weights['diversity'] +
            chat_spike_score * self.weights['chat_spike'] +
            viewer_trend_score * self.weights['viewer_spike']
        )
        
        final_score = min(final_score, 100.0)
        
        # 동적 하이라이트 임계값 계산 - 최근 5분
        history_num = self.history_1min*5
        if len(self.analysis_history) >= history_num:
            recent_scores = [a[2] for a in list(self.analysis_history)[-history_num:]]
            sorted_scores = sorted(recent_scores, reverse=True)
            # 상위 10%를 하이라이트로 설정
            threshold_index = min(floor(len(sorted_scores) * 0.10), len(sorted_scores) - 1)
            dynamic_threshold = sorted_scores[threshold_index]
            threshold = max(min(dynamic_threshold, 80.0), 40.0)
        else:
            threshold = self.small_fun_threshold  # 기본 임계값
        
        check_create_highlight = final_score >= threshold and self._should_create_new_highlight(final_score)
          
        # 상세 점수 정보
        score_details = {
            'engagement_score': engagement_score,
            'reaction_score': reaction_score,
            'diversity_score': diversity_score,
            'chat_spike_score': chat_spike_score,
            'viewer_trend_score': viewer_trend_score,
            'final_score': final_score,
            'threshold': threshold,
            'baseline_chat_count': self.baseline_metrics['avg_chat_count'],
            'baseline_chat_velocity': self.baseline_metrics['avg_chat_velocity'],
            'baseline_viewer_count': self.baseline_metrics['avg_viewer_count'],
            'reaction_keyword_breakdown': {
                'laugh': analysis.fun_keywords.get('laugh', 0),
                'excitement': analysis.fun_keywords.get('excitement', 0),
                'surprise': analysis.fun_keywords.get('surprise', 0),
                'reaction': analysis.fun_keywords.get('reaction', 0)
            }
        }
        
        return final_score, check_create_highlight, score_details
    
    #채널별 기준값 자동 업데이트
    def _update_baselines(self):
        if len(self.analysis_history) < 20:
            return
            
        recent_20 = list(self.analysis_history)[-20:]
        
        # 최근 20개 데이터의 평균으로 기준값 업데이트
        recent_chat_counts = [a[1].message_count for a in recent_20]
        recent_velocities = [a[1].chat_velocity for a in recent_20]
        recent_viewers = [a[1].viewer_count for a in recent_20]
        
        # 지수 이동 평균으로 부드럽게 업데이트 (alpha=0.15)
        alpha = 0.15
        avg_count = sum(recent_chat_counts) / len(recent_chat_counts)
        avg_velocity = sum(recent_velocities) / len(recent_velocities)
        avg_viewers = sum(recent_viewers) / len(recent_viewers)
        
        self.baseline_metrics['avg_chat_count'] = (
            alpha * avg_count + (1 - alpha) * self.baseline_metrics['avg_chat_count']
        )
        self.baseline_metrics['avg_chat_velocity'] = (
            alpha * avg_velocity + (1 - alpha) * self.baseline_metrics['avg_chat_velocity']
        )
        self.baseline_metrics['avg_viewer_count'] = (
            alpha * avg_viewers + (1 - alpha) * self.baseline_metrics['avg_viewer_count']
        )

    #참여도 점수 계산
    def _calculate_engagement_score(self, analysis: ChatAnalysisData) -> float:
        chat_count = analysis.message_count
        chat_velocity = analysis.chat_velocity
        
        baseline_count = self.baseline_metrics['avg_chat_count']
        baseline_velocity = self.baseline_metrics['avg_chat_velocity']
        
        # 정규화된 점수 (기준 대비 상대적 성능)
        if baseline_count > 0:
            count_ratio = chat_count / baseline_count
            count_score = min(self._sigmoid_transform(count_ratio, 1.0) * 50, 50)
        else:
            count_score = 0
            
        if baseline_velocity > 0:
            velocity_ratio = chat_velocity / baseline_velocity
            velocity_score = min(self._sigmoid_transform(velocity_ratio, 1.0) * 50, 50)
        else:
            velocity_score = 0
        
        return count_score + velocity_score

    #반응 강도 점수 계산
    def _calculate_reaction_score(self, analysis: ChatAnalysisData) -> float:
        keywords = analysis.fun_keywords
        
        # 키워드별 가중치 (감정 강도 반영)
        keyword_weights = {
            'laugh': 4.0,      # 웃음 - 강한 긍정 반응
            'excitement': 3.0,  # 흥분 - 강한 에너지
            'surprise': 3.5,   # 놀람 - 예상치 못한 재미
            'reaction': 2.0,   # 일반 반응
        }
        
        total_weighted_keywords = 0
        for keyword, count in keywords.items():
            weight = keyword_weights.get(keyword, 1.0)
            total_weighted_keywords += count * weight
        
        # 채팅 수 대비 키워드 밀도로 정규화
        if analysis.message_count > 0:
            keyword_density = total_weighted_keywords / analysis.message_count
            # 밀도 1.0 (평균 1채팅당 1키워드)를 기준으로 점수화
            reaction_score = min(self._sigmoid_transform(keyword_density, 1.0) * 100, 100)
        else:
            reaction_score = 0
            
        return reaction_score

    #사용자 참여의 다양성 점수 계산
    def _calculate_diversity_score(self, window_chats: List[Dict]) -> float:
        if not window_chats:
            return 0
            
        # 고유 사용자 수
        unique_users = len(set(chat['nickname'] for chat in window_chats))

        # 사용자 다양성 점수 (채팅 대비)
        user_diversity = min((unique_users / len(window_chats)) * 60, 60)

        # 메시지 길이 다양성
        msg_lengths = [len(chat['message']) for chat in window_chats]
        if len(msg_lengths) > 1:
            length_diversity = min(statistics.stdev(msg_lengths) / 20, 10)  # 표준편차 기반
        else:
            length_diversity = 0
         
        # 시간대별 분산도 (채팅이 한 순간에 몰렸는지, 고르게 분포했는지)
        if len(window_chats) >= 3:
            time_intervals = []
            sorted_chats = sorted(window_chats, key=lambda x: x['timestamp'])
            for i in range(1, len(sorted_chats)):
                interval = (sorted_chats[i]['timestamp'] - sorted_chats[i-1]['timestamp']).total_seconds()
                time_intervals.append(interval)
            
            if time_intervals:
                time_diversity = min(statistics.stdev(time_intervals) / 5, 10)
            else:
                time_diversity = 0
        else:
            time_diversity = 0
        
        return user_diversity + length_diversity + time_diversity

    #채팅 수 급증 점수 계산
    def _calculate_chat_spike_score(self, analysis: ChatAnalysisData) -> float:
        chat_spike_score = 0
        
        if len(self.analysis_history) >= 30:
            # 최근 30개 데이터를 사용하여 급증 판정
            recent_30 = list(self.analysis_history)[-30:]
            recent_avg = sum(a[1].message_count for a in recent_30) / len(recent_30)
            
            if recent_avg > 0:
                current_spike_ratio = analysis.message_count / recent_avg
                
                # 급증 조건: 최근 평균의 1.5배 이상 + 절대 증가량 3개 이상
                if current_spike_ratio >= 1.5 and analysis.message_count - recent_avg >= 30:
                    spike_intensity = min((current_spike_ratio - 1.0) * 40, 100)
                    chat_spike_score = spike_intensity

        return chat_spike_score
    
        #채팅 급증 보너스 계산
    
    #시청자 수 증가 추세 기반 점수 계산
    def _calculate_viewer_trend_score(self ,analysis: ChatAnalysisData):
        current_viewers = analysis.viewer_count
        history_num =  self.history_1min * 10

        #10분동안의 시청자 수 데이터가 있는지 
        if len(self.analysis_history) < history_num:
            return 0
        
        # 최근 시청자 수 데이터 추출
        recent_viewers = [a[1].viewer_count for a in list(self.analysis_history)[-history_num:]]  # 최근 10분
        
        if not recent_viewers or current_viewers <= 0:
            return 0
        
        trend_score = 0
        
        # 1. 단기 증가 추세 (최근 5분 vs 이전 5분)
        if len(self.analysis_history) >= 10:
            recent_5_avg = sum([a[1].viewer_count for a in list(self.analysis_history)[-int(history_num/2):]]) / (history_num/2)
            previous_5_avg = sum([a[1].viewer_count for a in list(self.analysis_history)[-history_num:-int(history_num/2)]]) / (history_num/2)
            
            if previous_5_avg > 0:
                growth_ratio = recent_5_avg / previous_5_avg
                
                if growth_ratio >= 1.3:        # 30% 이상 증가
                    trend_score += 40
                elif growth_ratio >= 1.2:      # 20% 이상 증가  
                    trend_score += 30
                elif growth_ratio >= 1.1:      # 10% 이상 증가
                    trend_score += 20
                elif growth_ratio >= 1.05:     # 5% 이상 증가
                    trend_score += 10
        
        # 2. 즉시 급증 감지 (최근 1분 평균 vs 현재)
        if len(self.analysis_history) >= history_num/10:
            recent_1_avg = sum([a[1].viewer_count for a in list(self.analysis_history)[-int(history_num/10):]]) / (history_num/10)
            
            if recent_1_avg > 0:
                immediate_ratio = current_viewers / recent_1_avg
                
                if immediate_ratio >= 1.5:      # 50% 이상 급증
                    trend_score += 30
                elif immediate_ratio >= 1.3:    # 30% 이상 급증
                    trend_score += 20
                elif immediate_ratio >= 1.2:    # 20% 이상 급증
                    trend_score += 15
                elif immediate_ratio >= 1.1:    # 10% 이상 급증
                    trend_score += 10
        
        # 3. 절대 증가량 보너스
        if len(self.analysis_history) >= (history_num/2):
            recent_5_avg = sum([a[1].viewer_count for a in list(self.analysis_history)[-int(history_num/2):]]) / (history_num/2)
            absolute_increase = current_viewers - recent_5_avg
            
            # 채널 규모별 차등 적용
            if recent_5_avg <= 100:         # 소규모 채널
                if absolute_increase >= 50:
                    trend_score += 25
                elif absolute_increase >= 20:
                    trend_score += 15
                elif absolute_increase >= 10:
                    trend_score += 10
            elif recent_5_avg <= 500:       # 중간 규모
                if absolute_increase >= 200:
                    trend_score += 25
                elif absolute_increase >= 100:
                    trend_score += 15
                elif absolute_increase >= 50:
                    trend_score += 10
            else:                           # 대규모 채널
                if absolute_increase >= 1000:
                    trend_score += 25
                elif absolute_increase >= 500:
                    trend_score += 15
                elif absolute_increase >= 200:
                    trend_score += 10
        
        # 4. 지속적 상승 보너스 (연속으로 증가하는 패턴)
        if len(self.analysis_history) >= history_num:
            splits_5_viewers = []
            splits_5_viewers.append(sum([a[1].viewer_count for a in list(self.analysis_history)[-history_num:-int(history_num/5*4)]]) / (history_num/5))
            splits_5_viewers.append(sum([a[1].viewer_count for a in list(self.analysis_history)[-int(history_num/5*4):-int(history_num/5*3)]]) / (history_num/5))
            splits_5_viewers.append(sum([a[1].viewer_count for a in list(self.analysis_history)[-int(history_num/5*3):-int(history_num/5*2)]]) / (history_num/5))
            splits_5_viewers.append(sum([a[1].viewer_count for a in list(self.analysis_history)[-int(history_num/5*2):-int(history_num/5)]]) / (history_num/5))
            splits_5_viewers.append(sum([a[1].viewer_count for a in list(self.analysis_history)[-int(history_num/5):]]) / int(history_num/5))

            increasing_count = 0
            
            for i in range(1, len(splits_5_viewers)):
                if splits_5_viewers[i] > splits_5_viewers[i-1]:
                    increasing_count += 1
            
            if increasing_count >= 4:       # 연속 4회 증가
                trend_score += 20
            elif increasing_count >= 3:     # 연속 3회 증가
                trend_score += 15
            elif increasing_count >= 2:     # 연속 2회 증가
                trend_score += 10
        
        # 최대 점수 제한
        return min(trend_score, 80)

    def _sigmoid_transform(self, x: float, midpoint: float = 1.0, steepness: float = 2.0) -> float:
            return 2 / (1 + exp(-steepness * (x - midpoint)))

    #새 하이라이트를 생성해야 하는지 판단
    def _should_create_new_highlight(self, score):
        if not self.highlights:
            return True
        
        last_highlight = self.highlights[-1]
        
        time_diff = (datetime.now() - last_highlight.timestamp).total_seconds()
        
        # 쿨다운: 2분 간격
        cooldown = 120
        if time_diff < cooldown:
            return False

        # 최근 30초
        bef_recent_scores = list(self.analysis_history)[-int(self.history_1min*0.5):]

        #이전 30초 동안 15점 이상 높아진 경우
        if score > min(a[2] for a in bef_recent_scores) + 15:
            return False

        return True

    #하이라이트 생성
    async def _create_highlight(self, analysis: ChatAnalysisData, fun_score: float, score_details: dict, window_chats: List[Dict]) -> None:
        # 최근 10개 채팅 컨텍스트
        chat_context = [
            f"{chat['nickname']}: {chat['message']}"
            for chat in window_chats[-10:]
        ]

        # 하이라이트 이유 결정
        reason = self._determine_highlight_reason(analysis, fun_score)

        # 방송이 켜진 시점 이후 작성된 채팅의 시간  
        after_openDate = analysis.timestamp - datetime.fromisoformat(analysis.openDate)
        after_openDate = str(after_openDate).split('.')[0]

        highlight = StreamHighlight(
            timestamp=analysis.timestamp,
            channel_id=self.channel_id,
            channel_name=self.channel_name,
            fun_score=fun_score,
            reason=reason,
            chat_context=chat_context,
            viewer_count=analysis.viewer_count,
            duration=self.window_size,
            after_openDate=after_openDate,
            score_details=score_details,
        )

        self.highlights.append(highlight)
        if not self.init.DO_TEST:
            await self._save_highlight_to_db(highlight)

        # 큰 재미인 경우 즉시 알림
        if fun_score >= self.big_fun_threshold:
            await self._send_notification(highlight)

    #하이라이트 이유 생성
    def _determine_highlight_reason(self, analysis: ChatAnalysisData, score: float) -> str:
        reasons = []

        if analysis.fun_keywords.get('laugh', 0) >= 10:
            reasons.append("😂 폭소 반응")
        if analysis.fun_keywords.get('excitement', 0) >= 8:
            reasons.append("🔥 뜨거운 반응")
        if analysis.fun_keywords.get('surprise', 0) >= 5:
            reasons.append("😱 놀라운 순간")
        if analysis.chat_velocity >= 2:
            reasons.append("💬 채팅 폭발")
        if score >= 80:
            reasons.append("🏆 레전드 순간")

        return " + ".join(reasons) if reasons else "재미있는 순간 감지"

    #하이라이트 DB 저장
    async def _save_highlight_to_db(self, highlight: StreamHighlight):
        try:
            # Supabase에 저장
            data = {
                'id': str(uuid4()),
                'channel_id': highlight.channel_id,
                'channel_name': highlight.channel_name,
                'timestamp': highlight.timestamp.isoformat(),
                'fun_score': highlight.fun_score,
                'reason': highlight.reason,
                'chat_context': highlight.chat_context,
                'viewer_count': highlight.viewer_count,
                'duration': highlight.duration,
                'after_openDate': highlight.after_openDate,
                'score_details': highlight.score_details,
            }
            
            # TODO: 실제 DB 저장 코드
            self.init.supabase.table('stream_highlights').insert(data).execute()
            
        except Exception as e:
            await log_error(f"하이라이트 DB 저장 오류: {e}")

    #알림 전송
    async def _send_notification(self, highlight: StreamHighlight):
        try:

            message = "🎉 하이라이트"
            channel_name = self.channel_name
            channel_color = self.init.stream_status[highlight.channel_id].id_list.loc[highlight.channel_id, 'channel_color']

            thumbnail_url = self.init.stream_status[highlight.channel_id].thumbnail_url
            platform_name= self.init.stream_status[highlight.channel_id].platform_name
            # image_url = upload_image_to_imgur(self.init.stream_status[highlight.channel_id], highlight.channel_id, thumbnail_url, platform_prefix = platform_name)
            image_url = 'https://i.imgur.com/Mwbjz5a.jpeg'

            # 알림 JSON 생성
            json_data = {"username": channel_name, 
             "avatar_url": self.init.stream_status[highlight.channel_id].profile_image,
                "embeds": [
                    {"color": int(channel_color),
                    "fields": [
                        {"name": "방제", "value": self.init.stream_status[highlight.channel_id].title, "inline": True},
                        {"name": ':busts_in_silhouette: 시청자수',
                        "value": self.init.stream_status[highlight.channel_id].view_count, "inline": True}
                        ],
                    "title": f"{channel_name} {message} \n재미도: {highlight.fun_score:.0f}/100\n",
                "url": self.init.stream_status[highlight.channel_id].channel_url,
                "image": {"url": image_url},
                "footer": { "text": f"뱅온 시간", "inline": True, "icon_url": iconLinkData().chzzk_icon },
                "timestamp": changeUTCtime(highlight.timestamp.isoformat())}]}
            
            # 알림 전송
            list_of_urls = get_list_of_urls(self.init.DO_TEST, self.init.userStateData, highlight.channel_name, highlight.channel_id, "하이라이트 알림")
            if self.init.DO_TEST: list_of_urls.append(environ['highlightURL'])
            asyncio.create_task(send_push_notification(list_of_urls, json_data))
            asyncio.create_task(DiscordWebhookSender().send_messages(list_of_urls, json_data))
            
        except Exception as e:
            await log_error(f"디스코드 알림 오류: {e}")

    #최근 하이라이트 조회
    def get_recent_highlights(self, minutes: int = 10) -> List[StreamHighlight]:
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        return [h for h in self.highlights if h.timestamp >= cutoff_time]
    
    #통계 정보 반환
    def get_stats(self) -> Dict:
        if not self.analysis_history:
            return {}
        
        recent_scores = [score for _, _, score in list(self.analysis_history)[-10:]]

        return {
            'total_messages': len(self.chat_buffer),
            'total_highlights': len(self.highlights),
            'avg_fun_score': sum(recent_scores) / len(recent_scores) if recent_scores else 0,
            'max_fun_score': max(recent_scores) if recent_scores else 0
        }
    
    #분석 데이터를 DataFrame으로 내보내기
    def export_analysis_data(self, hours: int = 1) -> pd.DataFrame:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        recent_logs = [
            log for log in self.detailed_logs 
            if datetime.fromisoformat(log['timestamp']) >= cutoff_time
        ]
        
        if not recent_logs:
            return pd.DataFrame()
        
        # DataFrame 생성
        data = []
        for log in recent_logs:
            row = {
                'timestamp': log['timestamp'],
                'fun_score': log['fun_score'],
                'message_count': log['analysis_data']['message_count'],
                'viewer_count': log['analysis_data']['viewer_count'],
                'chat_velocity': log['analysis_data']['chat_velocity'],
                
                # 점수 구성 요소
                'velocity_score': log['score_components']['chat_velocity_score'],
                'keyword_score': log['score_components']['keyword_score'],
                'diversity_score': log['score_components']['diversity_score'],
                'participation_score': log['score_components']['participation_score'],
                'chat_spike_bonus': log['score_components']['chat_spike_bonus'],
                'viewer_spike_bonus': log['score_components']['viewer_spike_bonus'],
                
                # 키워드 개별
                'laugh_count': log['score_components']['keyword_breakdown']['laugh'],
                'excitement_count': log['score_components']['keyword_breakdown']['excitement'],
                'surprise_count': log['score_components']['keyword_breakdown']['surprise'],
                'reaction_count': log['score_components']['keyword_breakdown']['reaction']
            }
            data.append(row)
        
        return pd.DataFrame(data)
    
    async def save_detailed_logs_to_file(self, force_save=False):
        """detailed_logs를 파일에 저장"""
        try:
            # 로그가 충분히 쌓였거나 강제 저장일 때만 실행
            if len(self.detailed_logs) < 100 and not force_save:
                return
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.log_dir}/fun_score_detailed_{self.channel_name}_{timestamp}.json"
            
            # JSON 형태로 저장
            log_data = {
                "channel_id": self.channel_id,
                "channel_name": self.channel_name,
                "save_timestamp": datetime.now().isoformat(),
                "total_logs": len(self.detailed_logs),
                "logs": self.detailed_logs.copy()  # 전체 로그 복사
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)
            
            print(f"상세 로그 저장 완료: {filename} ({len(self.detailed_logs)}개 기록)")
            
            # 메모리 절약을 위해 저장 후 로그 일부 삭제 (최근 2000개만 유지)
            if len(self.detailed_logs) > 2000:
                self.detailed_logs = self.detailed_logs[-2000:]
                
        except Exception as e:
            print(f"로그 저장 오류: {e}")
    
    async def save_logs_periodically(self):
        """주기적으로 로그 저장 (별도 태스크로 실행)"""
        while True:
            try:
                await asyncio.sleep(1800)  # 30분마다
                await self.save_detailed_logs_to_file()
            except Exception as e:
                print(f"주기적 로그 저장 오류: {e}")
                await asyncio.sleep(300)  # 오류 시 5분 후 재시도
    
    def export_logs_to_csv(self, hours=24):
        """최근 로그를 CSV 파일로 내보내기"""
        try:
            df = self.export_analysis_data(hours)
            
            if df.empty:
                print(f"최근 {hours}시간 동안 데이터가 없습니다.")
                return None
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.log_dir}/fun_score_analysis_{self.channel_name}_{timestamp}.csv"
            
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"CSV 내보내기 완료: {filename} ({len(df)}행)")
            
            return filename
            
        except Exception as e:
            print(f"CSV 내보내기 오류: {e}")
            return None
    
    def load_logs_from_file(self, filename):
        """파일에서 로그 불러오기 (분석용)"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"로그 파일 로드: {filename}")
            print(f"채널: {data['channel_name']}")
            print(f"저장 시점: {data['save_timestamp']}")
            print(f"총 기록 수: {data['total_logs']}")
            
            return data['logs']
            
        except Exception as e:
            print(f"로그 파일 로드 오류: {e}")
            return []
    
    def analyze_saved_logs(self, filename):
        """저장된 로그 파일 분석"""
        logs = self.load_logs_from_file(filename)
        
        if not logs:
            return
        
        # 기본 통계
        scores = [log['fun_score'] for log in logs]
        
        print(f"\n=== 저장된 로그 분석 결과 ===")
        print(f"분석 기간: {logs[0]['timestamp']} ~ {logs[-1]['timestamp']}")
        print(f"총 분석 횟수: {len(logs)}")
        print(f"평균 재미도: {sum(scores) / len(scores):.2f}")
        print(f"최고 재미도: {max(scores):.2f}")
        print(f"최저 재미도: {min(scores):.2f}")
        
        # 하이라이트 분석
        highlights = [log for log in logs if log['fun_score'] >= 50]
        big_highlights = [log for log in logs if log['fun_score'] >= 80]
        
        print(f"하이라이트 발생: {len(highlights)}회 ({len(highlights)/len(logs)*100:.1f}%)")
        print(f"대형 하이라이트: {len(big_highlights)}회 ({len(big_highlights)/len(logs)*100:.1f}%)")
        
        # 점수 구성 요소별 평균
        if logs:
            avg_velocity = sum(log['score_components']['chat_velocity_score'] for log in logs) / len(logs)
            avg_keyword = sum(log['score_components']['keyword_score'] for log in logs) / len(logs)
            avg_participation = sum(log['score_components']['participation_score'] for log in logs) / len(logs)
            avg_diversity = sum(log['score_components']['diversity_score'] for log in logs) / len(logs)
            
            print(f"\n--- 점수 구성 요소별 평균 ---")
            print(f"채팅 속도: {avg_velocity:.2f}/15")
            print(f"키워드: {avg_keyword:.2f}/30")
            print(f"참여도: {avg_participation:.2f}/10")
            print(f"다양성: {avg_diversity:.2f}/5")