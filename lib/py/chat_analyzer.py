import asyncio
import re
import json
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
                # 10초마다 분석
                if not if_after_time(self.chat_analyzer.last_analysis_time.isoformat(), sec=10):
                    await asyncio.sleep(0.5) 
                    continue
  
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
        self.analysis_interval = 10  # 10초마다 분석

        # 채팅 데이터 저장 (최대 30분)
        self.chat_buffer = deque(maxlen=1800)  # 30분 분량
        self.analysis_history = deque(maxlen=180)  # 30분간 분석 결과

        # 재미 키워드 패턴 (한국어 최적화)
        self.fun_patterns = {
        'laugh': re.compile(r'ㅋ{2,}|ㅎ{2,}|하하|ㅏㅏ|캬|푸하|풉|웃겨|개웃|존웃'),
        'excitement': re.compile(r'!{2,}|\?{2,}|ㄷㄷ|헐|대박|와|오|우와|미친|ㅁㅊ|개쩔|쩐다|ㄱㄱ|고고|가즈아'),
        'surprise': re.compile(r'헉|뭣|뭐야|어떻게|진짜|실화|레전드|띠용|충격|놀람'),
        'reaction': re.compile(r'ㅠㅠ|ㅜㅜ|아니|안돼|제발|부탁|응원'),
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
        # 최대 1000개까지만 보관
        if len(self.detailed_logs) > 1000:
            self.detailed_logs = self.detailed_logs[-1000:]

        # 하이라이트 체크
        if fun_score >= self.small_fun_threshold and check_create_highlight:
            await self._create_highlight(analysis, fun_score, score_details, window_chats)

        # 분석 기록 저장
        self.analysis_history.append((current_time, analysis, fun_score))

        return fun_score, analysis, score_details
    
    def _calculate_fun_score(self, analysis: ChatAnalysisData, window_chats: List[Dict]) -> float:
        """재미도 점수를 세부 구성 요소와 함께 계산"""
        score_details = {
            'chat_velocity_score': 0,
            'keyword_score': 0,
            'diversity_score': 0,
            'participation_score': 0,
            'chat_spike_bonus': 0,
            'viewer_spike_bonus': 0,
            'keyword_breakdown': {
                'laugh': analysis.fun_keywords.get('laugh', 0),
                'excitement': analysis.fun_keywords.get('excitement', 0),
                'surprise': analysis.fun_keywords.get('surprise', 0),
                'reaction': analysis.fun_keywords.get('reaction', 0)
            }
        }
        
        score = 0.0
        check_create_highlight = False

        # 1. 채팅 속도 점수 (최대 15점)
        chat_velocity_score = min(analysis.chat_velocity * 5, 15)
        score += chat_velocity_score
        score_details['chat_velocity_score'] = chat_velocity_score

        # 2. 키워드 점수 (최대 30점)
        keyword_score = 0
        keyword_score += analysis.fun_keywords.get('laugh', 0) * 3.0
        keyword_score += analysis.fun_keywords.get('excitement', 0) * 2.0
        keyword_score += analysis.fun_keywords.get('surprise', 0) * 2.0
        keyword_score += analysis.fun_keywords.get('reaction', 0) * 1.0
        keyword_score = min(keyword_score, 30)
        score += keyword_score
        score_details['keyword_score'] = keyword_score

        # 3. 메시지 길이 다양성 (최대 5점)
        if window_chats:
            msg_lengths = [len(chat['message']) for chat in window_chats]
            if len(msg_lengths) > 1:
                import statistics
                if len(msg_lengths) >= 2:
                    diversity = min(statistics.stdev(msg_lengths) / 20, 5)
                    score += diversity
                    score_details['diversity_score'] = diversity

        # 4. 채팅 작성자 수 (최대 10점)
        if window_chats:
            unique_users = len(set(chat['nickname'] for chat in window_chats))
            participation_score = min(unique_users / self.window_size * 10, 10)
            score += participation_score
            score_details['participation_score'] = participation_score

        # 5. 급증 보너스 (최대 40점)
        if len(self.analysis_history) >= 30:
            recent_analyses = list(self.analysis_history)[-30:]
            avg_recent_msgs = sum(a[1].message_count for a in recent_analyses) / len(recent_analyses)
            avg_recent_views = sum(a[1].viewer_count for a in recent_analyses) / len(recent_analyses)
            
            # 채팅 수 급증
            if avg_recent_msgs > 0:
                spike_ratio = analysis.message_count / avg_recent_msgs
                if spike_ratio > 1.0:
                    chat_spike_bonus = min((spike_ratio - 1) * 40, 20)
                    score += chat_spike_bonus
                    score_details['chat_spike_bonus'] = chat_spike_bonus

            # 시청자 수 급증
            if avg_recent_views > 0:
                spike_ratio = analysis.viewer_count / avg_recent_views
                if spike_ratio > 1.0:
                    viewer_spike_bonus = min((spike_ratio - 1) * 40, 20)
                    score += viewer_spike_bonus
                    score_details['viewer_spike_bonus'] = viewer_spike_bonus
        
        # 하이라이트 생성 조건 확인
        if len(self.analysis_history) >= 10:
            recent_analyses = list(self.analysis_history)[-10:]
            max_recent_score = max(a[2] for a in recent_analyses)

            if score >= max_recent_score and self.check_bef_recent_scores(score): 
                check_create_highlight = True

        return min(score, 100), check_create_highlight, score_details
    
    def check_bef_recent_scores(self, score):
        bef_recent_scores = list(self.analysis_history)[-3:]

        for a in bef_recent_scores:
            if score < a[2] + 15:
                return False
            
        return True

    async def _create_highlight(self, analysis: ChatAnalysisData, fun_score: float, score_details: dict, window_chats: List[Dict]) -> None:
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
            score_details=score_details,
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
                'score_details': highlight.score_details,
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
    
    def export_analysis_data(self, hours: int = 1) -> pd.DataFrame:
        """분석 데이터를 DataFrame으로 내보내기"""
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
            
            # 메모리 절약을 위해 저장 후 로그 일부 삭제 (최근 1000개만 유지)
            if len(self.detailed_logs) > 1000:
                self.detailed_logs = self.detailed_logs[-1000:]
                
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