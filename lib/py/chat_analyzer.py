import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import deque, Counter
from os import environ
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

class ChatMessageWithAnalyzer:
    def setup_analyzer(self, channel_id: str, channel_name: str):
        """분석기 초기화"""
        self.chat_analyzer = ChatAnalyzer(self.init, channel_id, channel_name)
        self.analysis_task = None

    async def start_analyzer(self):
        """분석기 시작 - start() 메서드에서 호출"""
        if not self.analysis_task or self.analysis_task.done():
            self.analysis_task = asyncio.create_task(self._run_analyzer())
            print(f"채팅 분석기 시작: {self.chat_analyzer.channel_name}")

    async def stop_analyzer(self):
        """분석기 중지 - cleanup에서 호출"""
        if self.analysis_task and not self.analysis_task.done():
            self.analysis_task.cancel()
        try:
            await self.analysis_task
        except asyncio.CancelledError:
            pass

    async def _run_analyzer(self):
        """주기적인 분석 실행"""
        while True:
            try:
                # 10초마다 분석
                if not if_after_time(self.chat_analyzer.last_analysis_time.isoformat(), sec=10):
                    await asyncio.sleep(0.5) 
                    continue
  
                # 분석 실행
                result = await self.chat_analyzer.analyze()

                if result:
                    fun_score, analysis = result
                    print(f"{self.chat_analyzer.channel_name}, 재미도 점수: {fun_score}\n")
                      
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
        self.window_size = 60  # 1분 윈도우
        self.analysis_interval = 10  # 10초마다 분석

        # 채팅 데이터 저장 (최대 30분)
        self.chat_buffer = deque(maxlen=1800)  # 30분 분량
        self.analysis_history = deque(maxlen=180)  # 30분간 분석 결과

        # 재미 키워드 패턴 (한국어 최적화)
        self.fun_patterns = {
        'laugh': re.compile(r'ㅋ{2,}|ㅎ{2,}|하하|ㅏㅏ|캬|푸하|풉|웃겨|개웃|존웃'),
        'excitement': re.compile(r'!{2,}|\?{2,}|ㄷㄷ|헐|대박|와|오|우와|미친|개쩔|쩐다|ㄱㄱ|고고|가즈아'),
        'surprise': re.compile(r'헉|뭣|뭐야|어떻게|진짜|실화|레전드|띠용|충격|놀람'),
        'reaction': re.compile(r'ㅠㅠ|ㅜㅜ|아니|안돼|제발|부탁|응원'),
        }

        # 하이라이트 저장
        self.highlights: List[StreamHighlight] = []
        self.last_analysis_time = datetime.now()

        # 임계값 설정
        self.small_fun_threshold    = 50    # 작은 재미
        self.big_fun_threshold      = 80    # 큰 재미

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

        # 분석 간격 체크
        time_since_last = (current_time - self.last_analysis_time).seconds
        if time_since_last < self.analysis_interval:
            return None
        
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

        # 재미도 점수 계산
        fun_score, check_create_highlight = self._calculate_fun_score(analysis, window_chats)

        # 하이라이트 체크
        if fun_score >= self.small_fun_threshold and check_create_highlight:
            await self._create_highlight(analysis, fun_score, window_chats)

        # 분석 기록 저장
        self.analysis_history.append((current_time, analysis, fun_score))

        return fun_score, analysis
    
    def _calculate_fun_score(self, analysis: ChatAnalysisData, window_chats: List[Dict]) -> float:
        """재미도 점수 계산 (0-100)"""
        score = 0.0
        check_create_highlight = True

        # 1. 채팅 속도 점수 (최대 15점), 초당 3개 채팅 발생시 15점
        chat_velocity_score = min(analysis.chat_velocity * 5, 15)
        score += chat_velocity_score

        # 2. 키워드 점수 (최대 30점)
        keyword_score = 0
        keyword_score += analysis.fun_keywords.get('laugh', 0) * 3.0
        keyword_score += analysis.fun_keywords.get('excitement', 0) * 2.0
        keyword_score += analysis.fun_keywords.get('surprise', 0) * 2.0
        keyword_score += analysis.fun_keywords.get('reaction', 0) * 1.0
        score += min(keyword_score, 30)

        # 3. 메시지 길이 다양성 (최대 5점)
        if window_chats:
            msg_lengths = [len(chat['message']) for chat in window_chats]
            if len(msg_lengths) > 1:
                # 표준편차가 클수록 다양한 길이의 메시지
                import statistics
                if len(msg_lengths) >= 2:
                    diversity = min(statistics.stdev(msg_lengths) / 20, 5)
                    score += diversity

        # 4. 채팅 작성자 수 (최대 10점), 초당 2명 채팅 작성시 10점
        if window_chats:
            unique_users = len(set(chat['nickname'] for chat in window_chats))
            participation_score = min(unique_users / self.window_size * 10, 10)
            score += participation_score

        # 5. 급증 보너스 (최대 40점)
        if len(self.analysis_history) >= 30:
            # 최근 30개 분석과 비교
            recent_analyses = list(self.analysis_history)[-30:]
            avg_recent_msgs = sum(a[1].message_count for a in recent_analyses) / len(recent_analyses)
            avg_recent_views = sum(a[1].viewer_count for a in recent_analyses) / len(recent_analyses)
            
            # 채팅 수 급증
            if avg_recent_msgs > 0:
                spike_ratio = analysis.message_count / avg_recent_msgs
                if spike_ratio > 1.0:  # 최대 50% 증가시 15점 
                    spike_bonus = min((spike_ratio - 1) * 40, 20)
                    score += spike_bonus

            # 시청자 수 급증
            if avg_recent_views > 0:
                spike_ratio = analysis.viewer_count / avg_recent_views
                if spike_ratio > 1.0:  # 최대 50% 증가시 15점 
                    spike_bonus = min((spike_ratio - 1) * 40, 20)
                    score += spike_bonus
        
        # 최근의 fun_score 중에 가장 점수가 높고, 직전 보다 10점 이상 높을 경우인지 확인
        if len(self.analysis_history) >= 10:
            recent_analyses = list(self.analysis_history)[-10:]
            max_recent_score = max(a[2] for a in recent_analyses)

            if score >= max_recent_score and self.check_bef_recent_scores(score): 
                check_create_highlight = True
            else:
                check_create_highlight = False

        return min(score, 100), check_create_highlight
    
    def check_bef_recent_scores(self, score):
        bef_recent_scores = list(self.analysis_history)[-3:]

        for a in bef_recent_scores:
            if score < a[2] + 10:
                return False
            
        return True

    async def _create_highlight(self, analysis: ChatAnalysisData, fun_score: float, window_chats: List[Dict]) -> None:
        """하이라이트 생성"""
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
        )

        self.highlights.append(highlight)
        if not self.init.DO_TEST:
            await self._save_highlight_to_db(highlight)

        # 큰 재미인 경우 즉시 알림
        if fun_score >= self.big_fun_threshold:
            await self._send_notification(highlight)

    def _determine_highlight_reason(self, analysis: ChatAnalysisData, score: float) -> str:
        """하이라이트 이유 생성"""
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

    async def _save_highlight_to_db(self, highlight: StreamHighlight):
        """하이라이트 DB 저장"""
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
            }
            
            # TODO: 실제 DB 저장 코드
            self.init.supabase.table('stream_highlights').insert(data).execute()
            
        except Exception as e:
            await log_error(f"하이라이트 DB 저장 오류: {e}")

    async def _send_notification(self, highlight: StreamHighlight):
        """알림 전송"""
        try:

            message = "🎉 하이라이트"
            channel_name = self.data.channel_name
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

    def get_recent_highlights(self, minutes: int = 10) -> List[StreamHighlight]:
        """최근 하이라이트 조회"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        return [h for h in self.highlights if h.timestamp >= cutoff_time]
    
    def get_stats(self) -> Dict:
        """통계 정보 반환"""
        if not self.analysis_history:
            return {}
        
        recent_scores = [score for _, _, score in list(self.analysis_history)[-10:]]

        return {
            'total_messages': len(self.chat_buffer),
            'total_highlights': len(self.highlights),
            'avg_fun_score': sum(recent_scores) / len(recent_scores) if recent_scores else 0,
            'max_fun_score': max(recent_scores) if recent_scores else 0
        }