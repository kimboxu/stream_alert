import asyncio
import re
import json
import statistics
from requests import get
from io import BytesIO
from PIL import Image as PILImage
from math import exp, floor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import deque, Counter
from os import environ, path, makedirs
import pandas as pd
import glob
from uuid import uuid4
from pathlib import Path
from live_message import upload_image_to_imgur
from base import log_error, if_after_time, changeUTCtime, iconLinkData, initVar, get_stream_start_id, format_time_for_comment, get_message
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from notification_service import send_push_notification
from make_log_api_performance import PerformanceManager
from highlight_chat_saver import HighlightChatSaver

@dataclass
class ChatAnalysisData:
    """채팅 분석 데이터를 저장하는 클래스"""
    timestamp: datetime
    openDate: datetime
    message_count: int = 0
    viewer_count: int = 0
    threshold: int = 0
    fun_keywords: Dict[str, int] = field(default_factory=dict)

@dataclass
class StreamHighlight:
    """하이라이트 순간 정보"""
    timestamp: datetime
    channel_id: str
    channel_name: str
    fun_score: float
    reason: str
    chat_context: List[str]
    duration: int  # seconds
    after_openDate: datetime
    comment_after_openDate: datetime
    score_details: dict
    analysis_data: dict
    image: PILImage.Image = None

class ChatMessageWithAnalyzer:
    def setup_analyzer(self, channel_id: str, channel_name: str):
        """분석기 초기화"""
        self.chat_analyzer = ChatAnalyzer(self.init, self.performance_manager, channel_id, channel_name)
        self.analysis_task = None
        self.log_save_task = None
        self.is_save_log = False

        # 하이라이트 채팅 저장기 추가
        self.highlight_saver = HighlightChatSaver()

    async def start_analyzer(self):
        """분석기 시작 - start() 메서드에서 호출"""
        if not self.analysis_task or self.analysis_task.done():
            self.analysis_task = asyncio.create_task(self._run_analyzer())
            print(f"{datetime.now()} 채팅 분석기 시작: {self.chat_analyzer.channel_name}, {self.init.highlight_chat[self.chat_analyzer.channel_id]}")

            # 주기적 로그 저장 태스크 시작
            self.log_save_task = asyncio.create_task(self.chat_analyzer.save_logs_periodically())
            print(f"{datetime.now()} 로그 저장 태스크 시작: 30분마다 자동 저장")

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

    async def should_offLine(self):
        # 로그 저장
        if not self.is_save_log:
            self.is_save_log = True
        
            asyncio.create_task(self.highlight_processing())

    async def highlight_processing(self):
        """하이라이트 처리"""
        try:
            print(f"{datetime.now()} 하이라이트 처리 시작: {self.chat_analyzer.channel_name}")

            await self.chat_analyzer.save_detailed_logs_to_file(save_cache=True,force_save=True)

            # 하이라이트 생성
            timeline_comments = await self.chat_analyzer._make_highlight_chat(self.chat_analyzer.highlights)
            self.chat_analyzer.highlights = []
            self.chat_analyzer.update_highlight_chat(timeline_comments)

            # 하이라이트 채팅 업데이트 직후 파일로 저장
            await self._save_completed_highlight_chat_after_update()
            
            return True
            
        except Exception as e:
            await log_error(f"하이라이트 처리 오류: {e}")
            return False

    async def _save_completed_highlight_chat_after_update(self):
        """하이라이트 채팅 저장"""
        try:
            channel_id = self.chat_analyzer.channel_id
            channel_name = self.chat_analyzer.channel_name
            
            # 현재 스트림의 stream_start_id 가져오기
            stream_start_time = self.init.stream_status[channel_id].start_at['openDate']
            stream_start_id = get_stream_start_id(channel_id, stream_start_time)
            
            # 해당 채널의 하이라이트 데이터 확인
            if (channel_id not in self.init.highlight_chat or 
                stream_start_id not in self.init.highlight_chat[channel_id]):
                print(f"{datetime.now()} 저장할 하이라이트 데이터 없음: {channel_name} - {stream_start_id}")
                return

            # 현재 스트림의 하이라이트 데이터 가져오기
            highlight_data = self.init.highlight_chat[channel_id][stream_start_id]
            
            # timeline_comments가 업데이트되었는지 확인
            if (hasattr(highlight_data, 'timeline_comments') and 
                highlight_data.timeline_comments):
                
                print(f"{datetime.now()} 하이라이트 채팅 저장 시작: {channel_name}")
                print(f"  - 스트림 ID: {stream_start_id}")
                print(f"  - 하이라이트 개수: {len(highlight_data.timeline_comments)}개")
                
                # 파일로 저장
                file_path = await self.highlight_saver.save_completed_stream_highlight(
                    channel_id, channel_name, stream_start_id, highlight_data
                )
                
                if file_path:
                    print(f"{datetime.now()} 하이라이트 채팅 저장 성공: {file_path}")
                    
                    # 저장 성공 후 메모리에서 제거
                    del self.init.highlight_chat[channel_id][stream_start_id]
                    print(f"{datetime.now()} 메모리에서 제거 완료: {stream_start_id}")
                else:
                    print(f"{datetime.now()} 하이라이트 채팅 저장 실패: {channel_name}")
            else:
                print(f"{datetime.now()} timeline_comments가 비어있음: {channel_name}")
                
        except Exception as e:
            from base import log_error
            await log_error(f"하이라이트 채팅 저장 오류 ({channel_name}): {e}")
            print(f"{datetime.now()} 하이라이트 채팅 저장 오류: {e}")

    async def _run_analyzer(self):
        """주기적인 분석 실행"""
        while True:
            try:
                # 5초마다 분석
                await asyncio.sleep(self.chat_analyzer.analysis_interval) 

                # 분석 실행
                detailed_log = await self.chat_analyzer.analyze()

                # print(f"{datetime.now()} {self.chat_analyzer.channel_name}, 디테일 점수{detailed_log}")
                      
            except asyncio.CancelledError:
                break

            except Exception as e:
                await log_error(f"분석기 실행 오류: {e}")
                await asyncio.sleep(10)  # 오류시 10초 대기

class ChatAnalyzer:
    """채팅 데이터를 분석하여 재미있는 순간을 감지하는 클래스"""
    def __init__(self, init: initVar, performance_manager: PerformanceManager, channel_id: str, channel_name: str = ""):
        self.init = init
        self.performance_manager = performance_manager
        self.DiscordWebhookSender_class = DiscordWebhookSender()
        self.channel_id = channel_id
        self.channel_name = channel_name

        # 분석 설정
        self.window_size = 30       # 30초 윈도우
        self.analysis_interval = 5  # 5초마다 분석
        self.max_file_age_days = 30 # 30일 이상된 파일 삭제

        # 채팅 데이터 저장 (약 30분)
        self.history_1min = int(60/self.analysis_interval)
        self.chat_buffer = deque(maxlen=3600)  #30분 분량(2/초 채팅 기준)
        self.analysis_history = deque(maxlen= self.history_1min * 30)  # 30분간 분석 결과

        # 재미 키워드 패턴 (한국어 최적화)
        self.fun_patterns = {
        'laugh': re.compile(r'ㅋ{2,}|z{2,}|ㅎ{2,}|하하|푸하|풉|웃겨|개웃|존웃|엌'),
        'excitement': re.compile(r'!{1,}|\?{2,}|ㄷ{2,}|ㄱ{2,}|ㅏ{2,}|헐|대박|캬|^굳$|^구뜨|^와|^오$|^오(?!\S)|^오.|^오우|^오이|^옹|^올$|우와|미친|ㅁㅊ|나이스|ㄴㅇㅅ|개쩔|쩐다|고고|가자잇|가즈아|ㄱㅈㅇ|ㄷㄱㄷㄱ|ㄷㄱㅈ|ㅗㅜㅑ|으흐흐'),
        'surprise': re.compile(r'^\s*\?\s*$|헉|왓|뭣|뭐야|뭐여|무야|어라|어래|어머|어떻게|진짜|실화|레전드|띠용|충격|놀람|지리네|o0o|O0O|0o0'),
        'reaction': re.compile(r'ㅠ{2,}|ㅜ{2,}|ㅎㅇㅌ|ㄹㅇ|앗|아악|아으|으아|으악|끄악|아니|안돼|제발|부탁|응원'),
        'greeting': re.compile(r'^.하$|^.바$|^.ㅎ$|^.ㅂ$|ㅎㅇ|안녕|반갑'),
        }

        # 가중 평균으로 최종 점수
        self.weights = {
            'chat_spike': 0.35,     # 채팅 급증 
            'reaction': 0.40,       # 반응 강도
            'diversity': 0.10,      # 다양성 유지
            'viewer_spike': 0.15,   # 시청자 급증 
        }

        # 하이라이트 저장
        self.highlights: List[StreamHighlight] = []
        self.last_highlight = None
        self.last_analysis_time = datetime.now()

        # 임계값 설정
        self.small_fun_difference   = 15    # 작은 재미 차이
        self.big_fun_difference     = 70    # 큰 재미 차이
        self.cooldown               = 90    # 쿨다운

        # 로그 파일 설정
        self.detailed_logs = []  # 상세 분석 로그
        self._setup_log_directories()
        
    def _setup_log_directories(self):
        """프로젝트 구조에 맞는 로그 디렉토리 설정"""
        # 현재 스크립트 위치를 기준으로 프로젝트 루트 찾기
        current_file = Path(__file__)
        
        if current_file.parent.name == 'py':
            project_root = current_file.parent.parent  # stream_alert/
        else:
            # 만약 다른 위치에 있다면 현재 디렉토리 기준
            project_root = current_file.parent
        
        # 로그 디렉토리 경로 설정
        self.data_dir = project_root / "data"
        self.log_dir = self.data_dir / "fun_score_logs"
        
        # 디렉토리 생성
        self.log_dir.mkdir(parents=True, exist_ok=True)


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
        )

        # 키워드 집계
        keyword_counter = Counter()
        for chat in window_chats:
            for key, count in chat['keywords'].items():
                keyword_counter[key] += count

        analysis.fun_keywords = dict(keyword_counter)

        # 상세 점수 계산
        score_details = self._calculate_fun_score(current_time, analysis, window_chats)

        # 방송이 켜진 시점 이후 작성된 채팅의 시간  
        after_openDate = analysis.timestamp - datetime.fromisoformat(analysis.openDate)
        after_openDate = str(after_openDate).split('.')[0]
        after_openDate = format_time_for_comment(after_openDate)
        
        # 상세 로그 저장
        detailed_log = {
            'timestamp': current_time.isoformat(),
            'fun_score': score_details['final_score'],
            'score_components': score_details,
            'reason': self._determine_highlight_reason(analysis, score_details),
            'analysis_data': {
                'message_count': analysis.message_count,
                'viewer_count': analysis.viewer_count,
                'fun_keywords': analysis.fun_keywords
            },
            'after_openDate': after_openDate,
            'comment_after_openDate': after_openDate,
            'chat_context': [ f"{chat['nickname']}: {chat['message']}" for chat in window_chats[-30:]],  # 최근 30개 메시지
        }
        
        self.detailed_logs.append(detailed_log)
        # 최대 2000개까지만 보관
        if len(self.detailed_logs) > 2000:
            self.detailed_logs = self.detailed_logs[-2000:]

        # 하이라이트 체크
        if score_details['highlights'] or self.init.DO_TEST:
            await self._create_highlight(detailed_log)

        # 분석 기록 저장
        self.analysis_history.append((analysis, score_details['final_score']))

        return detailed_log
    
    #재미도 점수 계산
    def _calculate_fun_score(self, current_time: datetime, analysis: ChatAnalysisData, window_chats: List[Dict]) -> Tuple[float, bool, dict]:
        # 적응형 기준값 초기화
        if not hasattr(self, 'baseline_metrics'):
            self.baseline_metrics = {
                'avg_chat_count': 10.0,
                'avg_viewer_count': 100.0,
                'avg_threshold_score': self.small_fun_difference,
            }
        
        # 기준값 자동 업데이트
        self._update_baselines()
        
        # 1. 채팅 급증 점수 (35% 가중치) - 최대 100점
        chat_spike_score = self._calculate_chat_spike_score(analysis)
            
        # 2. 반응 강도 점수 (40% 가중치) - 최대 100점
        reaction_score = self._calculate_reaction_score(analysis)
        
        # 3. 다양성 점수 (10% 가중치) - 최대 100점
        diversity_score = self._calculate_diversity_score(window_chats)

        # 4. 시청자 급증 점수 (15% 가중치) - 최대 100점
        viewer_trend_score = self._calculate_viewer_trend_score(analysis)

        final_score = (
            chat_spike_score * self.weights['chat_spike'] +
            reaction_score * self.weights['reaction'] +
            diversity_score * self.weights['diversity'] +
            viewer_trend_score * self.weights['viewer_spike']
        )
        
        final_score = min(final_score, 100.0)
         
        # 상세 점수 정보
        score_details = {
            'chat_spike_score': chat_spike_score,
            'reaction_score': reaction_score,
            'diversity_score': diversity_score,
            
            'viewer_trend_score': viewer_trend_score,
            'final_score': final_score,
            'baseline_chat_count': self.baseline_metrics['avg_chat_count'],
            'baseline_viewer_count': self.baseline_metrics['avg_viewer_count'],
            'baseline_threshold': self.baseline_metrics['avg_threshold_score'],
            'highlights': self._is_highlight(final_score, self.small_fun_difference),
            'big_highlights': self._is_highlight(final_score, self.big_fun_difference),
            'score_difference': self.get_score_difference(final_score),
            'should_create_new_highlight':self._should_create_new_highlight(final_score, current_time),
        }
        
        return score_details
    
    #채널별 기준값 자동 업데이트
    def _update_baselines(self):
        if len(self.analysis_history) < 20:
            return
            
        recent_20 = list(self.analysis_history)[-20:]
        
        # 최근 20개 데이터의 평균으로 기준값 업데이트
        recent_chat_counts = [a[0].message_count for a in recent_20]
        recent_viewers = [a[0].viewer_count for a in recent_20]
        recent_final_score = [a[1] for a in recent_20]
        
        # 지수 이동 평균으로 부드럽게 업데이트 (alpha=0.10)
        alpha = 0.10
        avg_count = sum(recent_chat_counts) / len(recent_chat_counts)
        avg_viewers = sum(recent_viewers) / len(recent_viewers)
        avg_final_score = sum(recent_final_score) / len(recent_final_score)
        
        self.baseline_metrics['avg_chat_count'] = (
            alpha * avg_count + (1 - alpha) * self.baseline_metrics['avg_chat_count']
        )
        self.baseline_metrics['avg_viewer_count'] = (
            alpha * avg_viewers + (1 - alpha) * self.baseline_metrics['avg_viewer_count']
        )
        self.baseline_metrics['avg_threshold_score'] = (
            alpha * avg_final_score + (1 - alpha) * self.baseline_metrics['avg_threshold_score']
        )

    #채팅 급증 점수 계산
    def _calculate_chat_spike_score(self, analysis: ChatAnalysisData) -> float:
        # 인사 반응(방송 시작 직후 or 방송 종료 직전의 인사는 제외)
        del_greeting_message_count = analysis.message_count - analysis.fun_keywords.get("greeting",0)

        # 정규화된 점수 (기존 대비 상대적으로 2배 일 경우 50점)
        count_ratio = del_greeting_message_count / self.baseline_metrics['avg_chat_count']
        count_score = min(self._sigmoid_transform(count_ratio, 2.0) * 100, 100)
  
        return count_score

    #반응 강도 점수 계산
    def _calculate_reaction_score(self, analysis: ChatAnalysisData) -> float:
        keywords = analysis.fun_keywords
        
        # 키워드별 가중치 (감정 강도 반영)
        keyword_weights = {
            'laugh': 4.0,      # 웃음 - 강한 긍정 반응
            'excitement': 3.5,  # 흥분 - 강한 에너지
            'surprise': 2.5,   # 놀람 - 예상치 못한 재미
            'reaction': 1.0,   # 일반 반응
            # 'greeting': 0.0,   # 인사 반응(방송 시작 직후 or 방송 종료 직전의 인사는 제외)
        }
        
        total_weighted_keywords = 0
        for keyword, count in keywords.items():
            
            weight = keyword_weights.get(keyword, 1.0)
            total_weighted_keywords += count * weight
        
        # 채팅 수 대비 키워드 밀도로 정규화
        keyword_density = total_weighted_keywords / self.baseline_metrics['avg_chat_count']
        # 밀도 2.0 (평균 채팅 대비 1키워드 * keyword_weights 비율*3.0배)를 기준으로 점수화
        reaction_score = min(self._sigmoid_transform(keyword_density, 2.0*3.0) * 100, 100)
            
        return reaction_score

    #사용자 참여의 다양성 점수 계산
    def _calculate_diversity_score(self, window_chats: List[Dict]) -> float:
        if not window_chats:
            return 0
            
        # 고유 사용자 수
        unique_users = len(set(chat['nickname'] for chat in window_chats))

        # 사용자 다양성 점수 (채팅 대비)
        user_diversity = min((unique_users / len(window_chats)) * 60, 50)

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
                time_diversity = min(statistics.stdev(time_intervals) / 5, 40)
            else:
                time_diversity = 0
        else:
            time_diversity = 0
        
        return user_diversity + length_diversity + time_diversity
    
    #시청자 수 증가 추세 기반 점수 계산
    def _calculate_viewer_trend_score(self ,analysis: ChatAnalysisData):
        current_viewers = analysis.viewer_count
        history_num =  self.history_1min * 20

        #20분동안의 시청자 수 데이터가 있는지 
        if len(self.analysis_history) < history_num:
            return 0
        
        # 최근 시청자 수 데이터 추출
        recent_viewers = [a[0].viewer_count for a in list(self.analysis_history)[-history_num:]]  # 최근 20분
        
        if not recent_viewers or current_viewers <= 0:
            return 0
        
        trend_score = 0
        
        # 1. 단기 증가 추세 (최근 10분 vs 이전 10분)
        if len(self.analysis_history) >= history_num:
            recent_10_avg = sum([a[0].viewer_count for a in list(self.analysis_history)[-int(history_num/2):]]) / (history_num/2)
            previous_10_avg = sum([a[0].viewer_count for a in list(self.analysis_history)[-history_num:-int(history_num/2)]]) / (history_num/2)
            
            if previous_10_avg > 0:
                growth_ratio = recent_10_avg / previous_10_avg
                
                if growth_ratio >= 1.3:        # 30% 이상 증가
                    trend_score += 40
                elif growth_ratio >= 1.2:      # 20% 이상 증가  
                    trend_score += 30
                elif growth_ratio >= 1.1:      # 10% 이상 증가
                    trend_score += 20
                elif growth_ratio >= 1.05:     # 5% 이상 증가
                    trend_score += 10
        
        # 2. 즉시 급증 감지 (최근 1분 평균 vs 현재)
        if len(self.analysis_history) >= self.history_1min:
            recent_1_avg = sum([a[0].viewer_count for a in list(self.analysis_history)[-int(self.history_1min):]]) / (self.history_1min)
            
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
        
        # 3. 지속적 상승 보너스 (연속으로 증가하는 패턴)
        if len(self.analysis_history) >= history_num:
            splits_5_viewers = []
            splits_5_viewers.append(sum([a[0].viewer_count for a in list(self.analysis_history)[-history_num:-int(history_num/5*4)]]) / (history_num/5))
            splits_5_viewers.append(sum([a[0].viewer_count for a in list(self.analysis_history)[-int(history_num/5*4):-int(history_num/5*3)]]) / (history_num/5))
            splits_5_viewers.append(sum([a[0].viewer_count for a in list(self.analysis_history)[-int(history_num/5*3):-int(history_num/5*2)]]) / (history_num/5))
            splits_5_viewers.append(sum([a[0].viewer_count for a in list(self.analysis_history)[-int(history_num/5*2):-int(history_num/5)]]) / (history_num/5))
            splits_5_viewers.append(sum([a[0].viewer_count for a in list(self.analysis_history)[-int(history_num/5):]]) / int(history_num/5))

            increasing_count = 0
            
            for i in range(1, len(splits_5_viewers)):
                if splits_5_viewers[i] > splits_5_viewers[i-1]:
                    increasing_count += 1
            
            if increasing_count >= 4:       # 연속 4회 증가
                trend_score += 30
            elif increasing_count >= 3:     # 연속 3회 증가
                trend_score += 20
            elif increasing_count >= 2:     # 연속 2회 증가
                trend_score += 10
        
        # 최대 점수 제한
        return min(trend_score, 100)

    def _sigmoid_transform(self, x: float, midpoint: float = 1.0, steepness: float = 2.0) -> float:
            return 2 / (1 + exp(-steepness * (x - midpoint)))

    #하이라이트를 인지 판단
    def _is_highlight(self, fun_score, fun_difference):
        if self.init.DO_TEST:
            return True
        
        if fun_score < self.baseline_metrics['avg_threshold_score']:
            return False

        if len(self.analysis_history) < int(self.history_1min*2):
            return False
        
        #이전 1분 중 가장 작은 점수가 fun_difference점 이상 높아진 경우
        if self.get_score_difference(fun_score) < fun_difference:
            return False

        return True
    
        #새 하이라이트를 생성해야 하는지 판단
    def _should_create_new_highlight(self, fun_score, current_time: datetime):
        if not self._is_highlight(fun_score, self.small_fun_difference):
            return False
        
        if self.last_highlight is None:
            return True
           
        # 쿨다운: 2분 간격
        if not self.check_cooldown(current_time, self.last_highlight.timestamp):
            return False

        return True
    
    def check_cooldown(self, current_time: datetime, last_timestamp: datetime):
        time_diff = (current_time - datetime.fromisoformat(last_timestamp)).total_seconds()
        
        # 쿨다운: 2분 간격
        if time_diff < self.cooldown:
            return False
        return True
    
    def get_score_difference(self, fun_score):
        if len(self.analysis_history) < int(self.history_1min):
            return 0
        
        bef_recent_scores = list(self.analysis_history)[-int(self.history_1min):]

        #이전 1분 중 가장 작은 점수와의 차이
        return max(fun_score - min(a[1] for a in bef_recent_scores), 0)

    #하이라이트 생성
    async def _create_highlight(self, detailed_log: dict) -> None:
        for _ in range(10):
            try:
                # 썸네일 가져오기
                thumbnail_url = self.init.stream_status[self.channel_id].thumbnail_url
                image_content = await get_message(self.performance_manager, "image", thumbnail_url)
                if not image_content:
                    print(f"_create_highlight 썸네일 가져오기 실패")
                    await asyncio.sleep(0.1)
                    continue
                image = PILImage.open(BytesIO(image_content))
                break
            except Exception as e:
                await log_error(f"썸네일 가져오기 실패: {e}")
                return

        highlight = StreamHighlight(
            timestamp=detailed_log['timestamp'],
            channel_id=self.channel_id,
            channel_name=self.channel_name,
            fun_score=detailed_log['fun_score'],
            reason=detailed_log['reason'],
            chat_context=detailed_log['chat_context'],
            duration=self.window_size,
            after_openDate=detailed_log['after_openDate'],
            comment_after_openDate=detailed_log['comment_after_openDate'],
            score_details=detailed_log['score_components'],
            image=image,
            analysis_data = {
                'message_count': detailed_log['analysis_data']['message_count'],
                'viewer_count': detailed_log['analysis_data']['viewer_count'],
                'fun_keywords': detailed_log['analysis_data']['fun_keywords'],
            },
        )


        # 큰 재미인 경우 알림 보내기
        if highlight.score_details['big_highlights'] and highlight.score_details['should_create_new_highlight']:
            await self._send_notification(highlight)

        #하이라이트의 피크 점수로 수정
        await self.change_score_to_peak(highlight)
        if highlight.score_details['should_create_new_highlight']:
            self.highlights.append(highlight)
            self.last_highlight = highlight

        # if not self.init.DO_TEST:
        #     await self._save_highlight_to_db(highlight)

        if len(self.highlights) > 10:
            timeline_comments = await self._make_highlight_chat(self.highlights[:-1])
            self.update_highlight_chat(timeline_comments)
            self.highlights = [self.highlights[-1]]

    #하이라이트 이유 생성
    def _determine_highlight_reason(self, analysis: ChatAnalysisData, score_details: dict) -> str:
        reasons = []

        if analysis.fun_keywords.get('laugh', 0) >= analysis.message_count/3:
            reasons.append("😂 폭소 반응")
        if analysis.fun_keywords.get('excitement', 0) >= analysis.message_count/3:
            reasons.append("🔥 뜨거운 반응")
        if analysis.fun_keywords.get('surprise', 0) >= analysis.message_count/3:
            reasons.append("😱 놀라운 순간")
        if score_details['chat_spike_score'] >= 50:
            reasons.append("💬 채팅량 폭증")
        if score_details['final_score'] >= 80:
            reasons.append("🏆 레전드 순간")

        return " + ".join(reasons) if reasons else "재미있는 순간 감지"

    async def change_score_to_peak(self, highlight: StreamHighlight):
        if not self.highlights:
            print(f"{datetime.now()} highlights가 비어있어서 change_score_to_peak 건너뜀")
            return
        
        is_higher_score = False
        if highlight.fun_score > self.highlights[-1].fun_score:
            is_higher_score = True
            
        
        if (highlight.score_details['highlights'] and not highlight.score_details['should_create_new_highlight']):
            idx = None
            is_new_highlight_check_cnt = 0
            for i,detailed_log in enumerate(reversed(self.detailed_logs)):
                # 현 사점과 직전의 하이라이트 사이에 하이라이트가 아닌 구간이 있는지
                if not detailed_log['score_components']['highlights']:
                    is_new_highlight_check_cnt += 1

                if detailed_log['score_components']['should_create_new_highlight']:
                    idx = i
                    break

            #직전 하이라이트의 should_create_new_highlight를 False로 변경 후 현재것을 True로 변경
            if idx:
                # 현 사점과 직전의 하이라이트 사이에 하이라이트가 아닌 구간이 있다면, 직전의 하이라이트 제거하지 않고, 새로운 하이라이트 추가
                if not is_higher_score and not is_new_highlight_check_cnt:
                    return
                
                highlight.score_details['should_create_new_highlight'] = True

                if is_new_highlight_check_cnt >= 3:
                    return
                
                highlight.comment_after_openDate = self.detailed_logs[-(idx+1)]['comment_after_openDate']
                self.detailed_logs[-1]['comment_after_openDate'] = self.detailed_logs[-(idx+1)]['comment_after_openDate']
                self.detailed_logs[-(idx+1)]['score_components']['should_create_new_highlight'] = False
                self.highlights = self.highlights[:-1]
                return
                
            await log_error(f"error change_score_to_peak: idx None")
            print(f"{datetime.now()} {self.detailed_logs}")

    #하이라이트 DB 저장
    async def _save_highlight_to_db(self, highlight: StreamHighlight):
        for _ in range(5):
            try:
                # Supabase에 저장
                data = {
                    'id': str(uuid4()),
                    'timestamp': highlight.timestamp,
                    'channel_id': highlight.channel_id,
                    'channel_name': highlight.channel_name,
                    'fun_score': highlight.fun_score,
                    'reason': highlight.reason,
                    'chat_context': highlight.chat_context,
                    'duration': highlight.duration,
                    'after_openDate': highlight.after_openDate,
                    'score_details': highlight.score_details,
                    'analysis_data': highlight.analysis_data,
                }
                
                # TODO: 실제 DB 저장 코드
                self.init.supabase.table('stream_highlights').insert(data).execute()
                break
                
            except Exception as e:
                await log_error(f"하이라이트 DB 저장 오류: {e}")
                await asyncio.sleep(0.2)

    #알림 전송
    async def _send_notification(self, highlight: StreamHighlight):
        try:
            message = "🎉 하이라이트"
            channel_name = self.channel_name
            channel_color = self.init.stream_status[highlight.channel_id].id_list.loc[highlight.channel_id, 'channel_color']
            openDate=self.init.stream_status[self.channel_id].state_update_time['openDate']

            thumbnail_url = self.init.stream_status[highlight.channel_id].thumbnail_url
            platform_name= self.init.stream_status[highlight.channel_id].platform_name
            icon = iconLinkData().chzzk_icon if platform_name == 'chzzk' else iconLinkData().afreeca_icon

            if self.init.DO_TEST: 
                image_url = 'https://i.imgur.com/Mwbjz5a.jpeg'
            else:
                image_url = upload_image_to_imgur(self.init.stream_status[highlight.channel_id], highlight.channel_id, thumbnail_url, platform_prefix = platform_name)
            
 
            timeline_comments = await self._make_highlight_chat([highlight])
        
            first_comment = timeline_comments[0] if timeline_comments else {}
            text = first_comment.get("text", "하이라이트 주석")
            description = first_comment.get("description", "분석 결과를 가져올 수 없습니다")

            # 알림 JSON 생성
            json_data = {"username": channel_name, 
             "avatar_url": self.init.stream_status[highlight.channel_id].profile_image,
                "embeds": [
                    {"color": int(channel_color),
                    "fields": [
                        {"name": "방제", "value": self.init.stream_status[highlight.channel_id].title, "inline": True},
                        {"name": ':busts_in_silhouette: 시청자수',
                        "value": self.init.stream_status[highlight.channel_id].view_count, "inline": True},
                        {"name": 'Description', "value": description}
                        ],
                    "title": f"{channel_name} {message}: 재미도: {highlight.fun_score:.0f}/100\n",
                    # "description": description,
                "url": self.init.stream_status[highlight.channel_id].channel_url,
                "image": {"url": image_url},
                "footer": { "text": f"뱅온 시간", "inline": True, "icon_url": icon },
                "timestamp": changeUTCtime(openDate)}]}
            print(f"{datetime.now()} {json_data}")
            # 알림 전송
            list_of_urls = get_list_of_urls(self.init.DO_TEST, self.init.userStateData, highlight.channel_name, highlight.channel_id, "하이라이트 알림")
            asyncio.create_task(send_push_notification(list_of_urls, json_data))
            asyncio.create_task(self.DiscordWebhookSender_class.send_messages(list_of_urls, json_data))
            
        except Exception as e:
            await log_error(f"디스코드 알림 오류: {e}")

    #detailed_logs를 파일에 저장
    async def save_detailed_logs_to_file(self, save_cache=False, force_save=False):
        try:
            # 로그가 충분히 쌓였거나 강제 저장일 때만 실행
            if len(self.detailed_logs) < 100 and not force_save:
                return
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"fun_score_detailed_{self.channel_name}_{timestamp}.json"
            
            # 전체 파일 경로
            file_path = self.log_dir / filename

            if save_cache:
                # 전체 로그 저장
                logs_to_save = self.detailed_logs.copy()
                remaining_logs = []  # 전부 삭제
            else:
                # 최근 일부만 제외하고 저장
                keep_count = int(self.history_1min * 2)
                logs_to_save = self.detailed_logs[:-keep_count].copy() if len(self.detailed_logs) > keep_count else []
                remaining_logs = self.detailed_logs[-keep_count:] if len(self.detailed_logs) > keep_count else self.detailed_logs.copy()
            
            # 저장할 로그가 없으면 종료
            if not logs_to_save:
                print(f"{datetime.now()} 저장할 로그가 없습니다.")
                return
            
            # JSON 형태로 저장
            log_data = {
                "channel_id": self.channel_id,
                "channel_name": self.channel_name,
                "save_timestamp": datetime.now().isoformat(),
                "total_logs": len(logs_to_save),
                "logs": logs_to_save,
                "save_type": "full_cache" if save_cache else "partial"
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)
            
            # 저장 완료 메시지
            save_type = "전체 캐시" if save_cache else "일부"
            print(f"{datetime.now()} 📄 상세 로그 저장 완료: {file_path} ({len(logs_to_save)}개 기록, {save_type})")
            
            # 저장 후 로그 업데이트
            self.detailed_logs = remaining_logs
            
            # 남은 로그 수 출력
            print(f"{datetime.now()} 남은 로그: {len(self.detailed_logs)}개")
                
        except Exception as e:
            print(f"{datetime.now()} ❌ 로그 저장 오류: {e}")

    async def _cleanup_old_log_files(self):
        """오래된 fun_score_logs 파일 삭제"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.max_file_age_days)
            pattern = str(self.log_dir / "fun_score_detailed_*.json")
            
            deleted_count = 0
            for file_path in glob.glob(pattern):
                file_path = Path(file_path)
                
                try:
                    # 파일명에서 날짜 추출
                    filename = file_path.stem
                    # fun_score_detailed_{channel_name}_{YYYYMMDD_HHMMSS}.json 형식
                    parts = filename.split('_')
                    if len(parts) >= 2:
                        datetime_part = parts[-1]  # YYYYMMDD_HHMMSS
                        if len(datetime_part) >= 8:
                            date_str = datetime_part[:8]  # YYYYMMDD
                            file_date = datetime.strptime(date_str, "%Y%m%d")
                            
                            if file_date < cutoff_date:
                                file_path.unlink()
                                deleted_count += 1
                                print(f"{datetime.now()} 오래된 fun_score 로그 파일 삭제: {file_path.name}")
                                
                except (ValueError, IndexError) as e:
                    print(f"{datetime.now()} 파일 날짜 파싱 실패 ({file_path.name}): {e}")
                    continue
            
            if deleted_count > 0:
                print(f"{datetime.now()} 총 {deleted_count}개의 오래된 fun_score 로그 파일 삭제 완료")
                
        except Exception as e:
            from base import log_error
            await log_error(f"fun_score 로그 파일 정리 실패: {e}")
    
    #주기적으로 로그 저장
    async def save_logs_periodically(self):
        cleanup_last_run_date = None  # 마지막 정리 실행 날짜 추적
        
        while True:
            try:
                await asyncio.sleep(1800)  # 30분마다
                await self.save_detailed_logs_to_file()

                # 매일 한 번씩 파일 정리
                current_date = datetime.now().date()
                current_hour = datetime.now().hour
                
                if (5 <= current_hour <= 7 and 
                    cleanup_last_run_date != current_date):
                    await self._cleanup_old_log_files()
                    cleanup_last_run_date = current_date
                    print(f"{datetime.now()} 일일 파일 정리 완료 - 다음 실행: {current_date + timedelta(days=1)}")

            except Exception as e:
                print(f"{datetime.now()} ⚠ 주기적 로그 저장 오류: {e}")
                await asyncio.sleep(300)  # 오류 시 5분 후 재시도

    async def _make_highlight_chat(self, highlights: list[StreamHighlight]):
        if not highlights:
            return []
        
        highlight_data  = []
        images_with_labels = []  # 라벨이 있는 이미지들
        for i, highlight in enumerate(highlights):
            try:
                analysis_data = highlight.analysis_data
                fun_keywords = analysis_data.get('fun_keywords', {})
                score_details = highlight.score_details

                highlight_data.append({ "하이라이트_ID"     :   f"HIGHLIGHT_{i+1}",  # 고유 식별자
                                        "재미도 점수"       :   highlight.fun_score,
                                        "하이라이트 이유"   :   highlight.reason,
                                        "최근 채팅"         :   highlight.chat_context,
                                        "최고점수_시간"     :   highlight.after_openDate,
                                        "VOD_타임라인_시간" :   highlight.comment_after_openDate,
                                        "방송 썸네일"       :   f"이미지_{i+1}",  # 이미지 순서 표시
                                        "메시지 갯수"       :   analysis_data['message_count'],
                                        "시청자 수"         :   analysis_data['viewer_count'],
                                        "웃음 키워드 수"    :   fun_keywords.get('laugh',0),
                                        "놀람 키워드 수"    :   fun_keywords.get('surprise',0),
                                        "흥분 키워드 수"    :   fun_keywords.get('excitement',0),
                                        "일반반응 키워드 수":   fun_keywords.get('reaction',0),
                                        "인사 키워드 수"    :   fun_keywords.get('greeting',0),
                                        "채팅 급증 점수"    :   score_details['chat_spike_score'],
                                        "리액션 점수"       :   score_details['reaction_score'],
                                        "다양성 점수"       :   score_details['diversity_score'],
                                        "시청자 급증 점수"  :   score_details['viewer_trend_score'],
                                        "기준 채팅 수"      :   score_details['baseline_chat_count'],
                                        "기준 시청자 수"    :   score_details['baseline_viewer_count'],
                                        "하이라이트 여부"   :   score_details['highlights'],
                                        "큰 하이라이트 여부":   score_details['big_highlights'],
                                        "재미도 점수 차이"  :   score_details['score_difference'],
                })

                # 이미지에 라벨 추가하여 수집
                images_with_labels.append(highlight.image)

            except Exception as e:
                print(f"{datetime.now()} 하이라이트 데이터 처리 오류: {e}")
                continue

        try:
            # 명확한 이미지 매핑 지시사항 포함
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

            response = self.init.model.generate_content(msg_list)

            # JSON 파싱
            try:
                timeline_comments = json.loads(response.text)
                if isinstance(timeline_comments, list):
                    # 시간순으로 정렬
                    timeline_comments.sort(key=lambda x: x.get('comment_after_openDate', ''))
                    print(f"{datetime.now()} 배치 분석 완료: {len(timeline_comments)}개 댓글 생성")
                    return timeline_comments
                
                else:
                    raise ValueError("응답이 리스트 형태가 아닙니다")

            except (json.JSONDecodeError, ValueError, KeyError) as e:
                print(f"{datetime.now()} JSON 파싱 오류: {e}")
                print(f"{datetime.now()} 응답 내용: {response.text[:500]}...")
                return []
                        
        except Exception as e:
            await log_error(f"{datetime.now()}타임라인 댓글 생성 오류: {e}")
            return []

    def update_highlight_chat(self, timeline_comments):
        stream_start_time = self.init.stream_status[self.channel_id].start_at['openDate']
        stream_start_id = get_stream_start_id(self.channel_id, stream_start_time)
        self.init.highlight_chat[self.channel_id][stream_start_id].timeline_comments.extend(timeline_comments)
                
        print(f"{datetime.now()} 타임라인 댓글 생성 완료: {len(timeline_comments)}개")
        for comment in timeline_comments:
            if 'comment_after_openDate' in comment and 'score_difference' in comment and 'text' in comment and 'description' in comment:
                print(f"**{comment['comment_after_openDate']}** {comment['score_difference']}** {comment['text']}** {comment['description']}")
