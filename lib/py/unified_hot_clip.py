import asyncio
import statistics
from math import exp
from random import random
from collections import deque
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional

from base import (
    initVar,
    log_error,
    changeUTCtime,
    iconLinkData,
    save_sent_notifications,
)
from improved_get_message import get_message
from make_log_api_performance import PerformanceManager
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from notification_service import send_push_notification


@dataclass
class ClipData:
    """플랫폼 공통 클립 데이터를 저장하는 클래스"""

    clipUID: str  # 클립 고유 ID
    videoId: str  # 비디오 ID
    clipTitle: str  # 클립 제목
    ownerChannelId: str  # 채널 ID
    thumbnailImageUrl: str  # 썸네일 URL
    categoryType: str  # 카테고리
    clipCategory: str  # 세부 카테고리
    duration: int  # 길이(초)
    createdDate: datetime  # 생성일
    readCount: int  # 조회수
    platform: str = ""  # 플랫폼 이름
    clipUrl: str = ""  # 클립 URL
    hotScore: float = 0.0  # 핫클립 점수
    isHot: bool = False  # 핫클립 여부


@dataclass
class HotClipAnalysisResult:
    """핫클립 분석 결과"""

    channel_id: str
    channel_name: str
    platform: str
    hot_clips: List[ClipData] = field(default_factory=list)
    total_clips_analyzed: int = 0
    average_views: float = 0.0
    analysis_timestamp: datetime = field(default_factory=datetime.now)


class BaseHotClipDetector(ABC):
    """모든 핫클립 감지 플랫폼에 공통으로 사용되는 기본 클래스"""

    def __init__(
        self,
        init_var: initVar,
        performance_manager: PerformanceManager,
        channel_id: str,
        platform: str,
    ):
        self.init = init_var
        self.hot_clip_data = init_var.hot_clip_data
        self.performance_manager = performance_manager
        self.DiscordWebhookSender_class = DiscordWebhookSender()
        self.channel_id = channel_id
        self.platform = platform
        self.IDList = self.init.IDList

        # 공통 설정값
        self.days_to_analyze = 14  # 2주
        self.hot_threshold = 70.0  # 핫클립 임계값 (100점 만점)
        self.randarea = 120
        self.analysis_interval = 1800 - self.randarea // 2  # 30분 마다 분석

        # 가중치 설정
        self.weights = {
            "view_score": 0.7,  # 조회수 점수 70%
            "recency_score": 0.3,  # 최신성 점수 30%
        }

        # 데이터 저장
        self.clip_history: deque = deque(maxlen=1000)
        self.last_analysis_time = None
        self.baseline_metrics = {"avg_views": 100.0, "view_threshold": 200.0}

    @abstractmethod
    async def _collect_clips_data(self) -> List[ClipData]:
        """플랫폼별 클립 데이터 수집 (추상 메서드)"""
        pass

    @abstractmethod
    def _get_platform_icon_url(self) -> str:
        """플랫폼별 아이콘 URL 반환 (추상 메서드)"""
        pass

    async def start_monitoring(self):
        """핫클립 모니터링 시작"""
        # print(f"{datetime.now()} 핫클립 감지 시작: {self.channel_id}")

        while True:
            try:
                analysis_result = await self.analyze_hot_clips()

                if analysis_result and analysis_result.hot_clips:
                    await self._send_hot_clip_notifications(analysis_result)

                    # 알림 기록 저장
                    if not self.init.DO_TEST:
                        asyncio.create_task(
                            save_sent_notifications(
                                self.init.supabase,
                                self.channel_id,
                                self.hot_clip_data,
                                self.platform,
                            )
                        )

                await asyncio.sleep(self.analysis_interval + random() * self.randarea)

            except Exception as e:
                await log_error(f" 핫클립 모니터링 오류: {str(e)}")
                await asyncio.sleep(300)

    async def analyze_hot_clips(self) -> Optional[HotClipAnalysisResult]:
        """핫클립 분석 실행 (공통 로직)"""
        try:
            # 채널 정보 가져오기
            channel_name = self.IDList[self.platform].loc[
                self.channel_id, "channelName"
            ]

            # 클립 데이터 수집
            clips = await self._collect_clips_data()

            if not clips:
                return None

            # 2주 이내 클립만 필터링
            recent_clips = self._filter_recent_clips(clips, self.days_to_analyze)

            if len(recent_clips) < 5:
                return None

            # 기준 메트릭 업데이트
            self._update_baseline_metrics(recent_clips)

            # 핫클립 점수 계산
            hot_clips = []
            for clip in recent_clips:
                hot_score = self._calculate_hot_score(clip, recent_clips)
                clip.hotScore = hot_score

                if hot_score >= self.hot_threshold:
                    clip.isHot = True
                    hot_clips.append(clip)

            # 결과 정렬 (점수 높은 순)
            hot_clips.sort(key=lambda x: x.hotScore, reverse=True)

            # 분석 결과 생성
            result = HotClipAnalysisResult(
                channel_id=self.channel_id,
                channel_name=channel_name,
                platform=self.platform,
                hot_clips=hot_clips,  # 상위 5개 제한 제거
                total_clips_analyzed=len(recent_clips),
                average_views=self.baseline_metrics["avg_views"],
            )

            # print(f"{datetime.now()} 핫클립 분석 완료: {channel_name}, 분석된 클립 {len(recent_clips)}개, 핫클립 {len(hot_clips)}개")

            return result

        except Exception as e:
            await log_error(f"핫클립 분석 오류: {str(e)}")
            return None

    def _filter_recent_clips(self, clips: List[ClipData], days: int) -> List[ClipData]:
        """최근 N일 이내 클립만 필터링"""
        cutoff_date = datetime.now() - timedelta(days=days)
        return [clip for clip in clips if clip.createdDate >= cutoff_date]

    def _update_baseline_metrics(self, clips: List[ClipData]):
        """기준 메트릭 업데이트"""
        if not clips:
            return

        view_counts = [clip.readCount for clip in clips]
        self.baseline_metrics["avg_views"] = statistics.mean(view_counts)
        self.baseline_metrics["view_threshold"] = statistics.median(view_counts)

    def _calculate_hot_score(self, clip: ClipData, all_clips: List[ClipData]) -> float:
        """핫클립 점수 계산"""
        view_score = self._calculate_view_score(clip.readCount)
        recency_score = self._calculate_recency_score(clip.createdDate)

        hot_score = (
            view_score * self.weights["view_score"]
            + recency_score * self.weights["recency_score"]
        )

        return min(hot_score, 100.0)

    def _calculate_view_score(self, read_count: int) -> float:
        """조회수 기반 점수 계산"""
        avg_views = self.baseline_metrics["avg_views"]

        if avg_views <= 0:
            return 0.0

        view_ratio = read_count / avg_views
        normalized_score = min(self._sigmoid_transform(view_ratio, 3.0) * 100, 100)

        return normalized_score

    def _sigmoid_transform(
        self, x: float, midpoint: float = 1.0, steepness: float = 2.0
    ) -> float:
        """시그모이드 변환 함수"""
        return 2 / (1 + exp(-steepness * (x - midpoint)))

    def _calculate_recency_score(self, created_date: datetime) -> float:
        """최신성 기반 점수 계산"""
        now = datetime.now()
        time_diff = (now - created_date).total_seconds()
        hours_passed = time_diff / 3600

        if hours_passed <= 1:
            return 100.0
        elif hours_passed <= 6:
            return 90.0
        elif hours_passed <= 24:
            return 70.0
        elif hours_passed <= 72:
            return 50.0
        elif hours_passed <= 168:  # 7일
            return 30.0
        else:
            return 10.0

    def get_author(self, channel_name):
        avatar_url = self.IDList[self.platform].loc[self.channel_id, "profile_image"]
        channel_data = self.IDList[self.platform].loc[self.channel_id]
        video_url = (
            f"https://chzzk.naver.com/{channel_data['uid']}"
            if self.platform == "chzzk"
            else f"https://www.sooplive.co.kr/station/{channel_data['uid']}"
        )

        author = {"name": channel_name, "url": video_url, "icon_url": avatar_url}
        return author

    async def _send_hot_clip_notifications(self, result: HotClipAnalysisResult):
        """모든 핫클립에 대해 알림 전송"""
        try:
            if not result.hot_clips:
                return

            channel_name = result.channel_name
            channel_data = self.IDList[self.platform].loc[self.channel_id]
            channel_color = int(channel_data["channel_color"])
            sent_notifications = set(
                self.hot_clip_data[self.platform].loc[self.channel_id, "sent_clip_uids"]
            )

            # 이미 알림 보낸 클립은 제외
            new_hot_clips = [
                clip
                for clip in result.hot_clips
                if clip.clipUID not in sent_notifications
            ]

            if not new_hot_clips:
                # print(f"{datetime.now()} 새로운 핫클립 없음: {channel_name}")
                return

            # 알림 전송할 URL 목록 가져오기
            list_of_urls = get_list_of_urls(
                self.init.DO_TEST,
                self.init.userStateData,
                channel_name,
                self.channel_id,
                "핫클립 알림",
            )

            if not list_of_urls:
                return

            # 각 핫클립에 대해 개별 알림 전송
            for clip in new_hot_clips:
                embed = {
                    "color": channel_color,
                    "author": self.get_author(channel_name),
                    "title": f"🔥 핫클립: {clip.clipTitle}",
                    "url": clip.clipUrl,
                    "description": f"👀 조회수: {clip.readCount:,}회\n",
                    "fields": [
                        {
                            "name": "카테고리",
                            "value": clip.categoryType,
                            "inline": True,
                        },
                        {"name": "길이", "value": f"{clip.duration}초", "inline": True},
                        {
                            "name": "채널 평균 조회수",
                            "value": f"{result.average_views:.0f}회",
                            "inline": True,
                        },
                    ],
                    "thumbnail": {"url": channel_data["profile_image"]},
                    "image": {"url": clip.thumbnailImageUrl},
                    "footer": {
                        "text": f"핫클립 생성 시간",
                        "icon_url": self._get_platform_icon_url(),
                    },
                    "timestamp": changeUTCtime(clip.createdDate.isoformat()),
                }

                json_data = {
                    "username": f"[핫클립] {channel_name}",
                    "avatar_url": channel_data["profile_image"],
                    "embeds": [embed],
                }
                if self.init.is_hot_clip[self.channel_id]:

                    print(
                        f"{datetime.now()} 핫클립 알림 전송: {channel_name} - {clip.clipTitle} (점수: {clip.hotScore:.1f})"
                    )

                    # 알림 전송
                    asyncio.create_task(send_push_notification(list_of_urls, json_data))
                    asyncio.create_task(
                        self.DiscordWebhookSender_class.send_messages(
                            list_of_urls, json_data
                        )
                    )

                # 알림 보낸 클립으로 기록
                max_len = 500
                self.hot_clip_data[self.platform].loc[self.channel_id, "sent_clip_uids"].append(clip.clipUID)
                self.hot_clip_data[self.platform].loc[self.channel_id, "sent_clip_uids"] = self.hot_clip_data[self.platform].loc[self.channel_id, "sent_clip_uids"][-max_len:]
                # 연속 알림 간 간격
                await asyncio.sleep(1)

        except Exception as e:
            await log_error(f"핫클립 알림 전송 오류: {str(e)}")


class ChzzkHotClipDetector(BaseHotClipDetector):
    """치지직 핫클립 감지 클래스"""

    def __init__(
        self,
        init_var: initVar,
        performance_manager: PerformanceManager,
        channel_id: str,
    ):
        super().__init__(init_var, performance_manager, channel_id, "chzzk")

    def _get_platform_icon_url(self) -> str:
        return iconLinkData().chzzk_icon

    async def _collect_clips_data(self) -> List[ClipData]:
        """치지직 클립 데이터 수집"""
        all_clips = []
        next_clip_uid = None
        channel_code = self.IDList[self.platform].loc[self.channel_id, "uid"]

        cutoff_date = datetime.now() - timedelta(days=self.days_to_analyze)

        while True:
            # API URL 생성
            if next_clip_uid:
                url = f"https://api.chzzk.naver.com/service/v1/channels/{channel_code}/clips?clipUID={next_clip_uid}&filterType=ALL&orderType=RECENT"
            else:
                url = f"https://api.chzzk.naver.com/service/v1/channels/{channel_code}/clips?filterType=ALL&orderType=RECENT"

            response_data = await get_message(self.performance_manager, "chzzk", url)

            if not response_data or response_data.get("code") != 200:
                break

            clips_data = response_data.get("content", {}).get("data", [])

            if not clips_data:
                break

            for clip_info in clips_data:
                try:
                    created_date = datetime.strptime(
                        clip_info["createdDate"], "%Y-%m-%d %H:%M:%S"
                    )

                    if created_date < cutoff_date:
                        return all_clips

                    clip = ClipData(
                        clipUID=clip_info["clipUID"],
                        videoId=clip_info["videoId"],
                        clipTitle=clip_info["clipTitle"],
                        ownerChannelId=clip_info["ownerChannelId"],
                        thumbnailImageUrl=clip_info["thumbnailImageUrl"],
                        categoryType=clip_info["categoryType"],
                        clipCategory=clip_info["clipCategory"],
                        duration=clip_info["duration"],
                        createdDate=created_date,
                        readCount=clip_info["readCount"],
                        platform=self.platform,
                        clipUrl=f"https://chzzk.naver.com/clips/{clip_info['clipUID']}",
                    )

                    all_clips.append(clip)

                except Exception as e:
                    print(f"치지직 클립 데이터 파싱 오류: {str(e)}")
                    continue

            # 다음 페이지 확인
            next_page = response_data.get("content", {}).get("page", {}).get("next")
            if next_page and "clipUID" in next_page:
                next_clip_uid = next_page["clipUID"]
                await asyncio.sleep(0.5)
            else:
                break

        return all_clips


class AfreecaHotClipDetector(BaseHotClipDetector):
    """아프리카TV 핫클립 감지 클래스"""

    def __init__(
        self,
        init_var: initVar,
        performance_manager: PerformanceManager,
        channel_id: str,
    ):
        super().__init__(init_var, performance_manager, channel_id, "afreeca")

    def _get_platform_icon_url(self) -> str:
        return iconLinkData().soop_icon

    async def _collect_clips_data(self) -> List[ClipData]:
        """아프리카TV 클립 데이터 수집"""
        all_clips = []
        page = 1
        afreeca_id = self.IDList[self.platform].loc[self.channel_id, "uid"]

        cutoff_date = datetime.now() - timedelta(days=self.days_to_analyze)

        while True:
            url = f"https://chapi.sooplive.co.kr/api/{afreeca_id}/vods/all/all?keyword=&orderby=reg_date&perPage=20&field=title,contents,user_nick,user_id&page={page}&start_date=&end_date="

            response_data = await get_message(self.performance_manager, "afreeca", url)

            if not response_data or not response_data.get("data"):
                break

            clips_data = response_data["data"]
            found_old_clip = False

            for clip_info in clips_data:
                try:
                    # 클립인지 확인 (ucc.file_type이 "CLIP"인 것만)
                    ucc_info = clip_info.get("ucc", {})
                    if ucc_info.get("file_type") != "CLIP":
                        continue

                    created_date = datetime.strptime(
                        clip_info["reg_date"], "%Y-%m-%d %H:%M:%S"
                    )

                    if created_date < cutoff_date:
                        found_old_clip = True
                        break

                    # 썸네일 URL 처리 (성인 컨텐츠 제외)
                    thumb_url = ucc_info.get("thumb", "")
                    if ucc_info.get("thumb_type") != "ADULT" and thumb_url.startswith(
                        "//"
                    ):
                        thumb_url = f"https:{thumb_url}"
                    elif ucc_info.get("thumb_type") == "ADULT":
                        thumb_url = ""  # 성인 콘텐츠는 썸네일 제외

                    # 카테고리 태그 처리
                    category_tags = ucc_info.get("category_tags", [])
                    category_type = category_tags[0] if category_tags else "기타"

                    clip = ClipData(
                        clipUID=str(clip_info["title_no"]),
                        videoId=str(clip_info["title_no"]),
                        clipTitle=clip_info["title_name"],
                        ownerChannelId=self.channel_id,
                        thumbnailImageUrl=thumb_url,
                        categoryType=category_type,
                        clipCategory=category_type,
                        duration=ucc_info.get("total_file_duration", 0)
                        // 1000,  # 밀리초를 초로
                        createdDate=created_date,
                        readCount=clip_info.get("count", {}).get("vod_read_cnt", 0),
                        platform=self.platform,
                        clipUrl=f"https://vod.sooplive.co.kr/player/{clip_info['title_no']}",
                    )

                    all_clips.append(clip)

                except Exception as e:
                    print(f"아프리카TV 클립 데이터 파싱 오류: {str(e)}")
                    continue

            if found_old_clip or len(clips_data) < 20:
                break

            page += 1
            await asyncio.sleep(0.5)

        return all_clips
