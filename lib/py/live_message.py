import base64
import asyncio
from typing import Dict
from datetime import datetime, timedelta
from os import remove, environ, path
from requests import post, get
from urllib.request import urlretrieve
from dataclasses import dataclass, field
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from notification_service import send_push_notification
from make_log_api_performance import PerformanceManager
from aiohttp import ClientSession, ClientError, TCPConnector
from io import BytesIO
from improved_get_message import get_message
from typing import List, Tuple, Dict, Any
from base import (
    initVar,
    userDataVar,
    save_airing_data,
    update_flag,
    if_after_time,
    save_profile_data,
    chzzk_getLink,
    chzzk_getChannelOffStateData,
    iconLinkData,
    changeUTCtime,
    afreeca_getLink,
    afreeca_getChannelOffStateData,
    fCount,
    fSleep,
    log_error,
    get_stream_start_id,
    format_time_for_comment,
    get_timestamp_from_stream_id,
)


@dataclass
class LiveData:
    """라이브 방송 데이터를 저장하는 데이터 클래스"""

    livePostList: list = field(default_factory=list)  # 알림 메시지 리스트
    live: str = ""  # 라이브 상태 ("OPEN", "CLOSE" 등)
    IDlist: list = field(default_factory=list)  # 스트리머 개인 값
    title: str = ""  # 방송 제목
    view_count: int = 0  # 시청자 수
    category: str = ""  # 카테고리
    thumbnail_url: str = ""  # 썸네일 URL
    channel_url: str = ""  # 채널 URL
    profile_image: str = ""  # 프로필 이미지 URL
    platform: str = ""  # 플랫폼 이름

    temp_start_at: Dict[str, str] = field(
        default_factory=lambda: {
            "openDate": "2025-01-01 00:00:00",  # 방송 시작 시간
            "closeDate": "2025-01-01 00:00:00",  # 방송 종료 시간
        }
    )

    state_update_time: Dict[str, str] = field(
        default_factory=lambda: {
            "openDate": "2025-01-01 00:00:00",  # 온라인 상태 업데이트 시간
            "myCheckopenDate": "2025-01-01T00:00:00",  # 내가 확인한 온라인 상태 업데이트 시간
            "closeDate": "2025-01-01 00:00:00",  # 오프라인 상태 업데이트 시간
            "myCheckcloseDate": "2025-01-01T00:00:00",  # 내가 확인한 오프라인 상태 업데이트 시간
            "titleChangeDate": "2025-01-01T00:00:00",  # 제목 변경 업데이트 시간
            "changeChatChannelIdDate": "2025-01-01T00:00:00",  # cid 업데이트 시간
            "is_firstConnect": True,  # 채팅창 연결이 처음인지
        }
    )


@dataclass
class highlight_chat_Data:
    """하이라이트 채팅 데이터를 저장하는 데이터 클래스"""

    timeline_comments: list = field(default_factory=list)
    stream_end_id: str = ""
    last_title: str = ""


class base_live_message:
    """모든 스트리밍 플랫폼에 공통으로 사용되는 기본 클래스"""

    def __init__(
        self,
        init_var: initVar,
        performance_manager: PerformanceManager,
        channel_id,
        platform,
    ):
        """
        초기화 함수

        Args:
            init_var: 초기화 변수들이 포함된 객체
            channel_id: 채널 ID
            platform: 플랫폼 이름 (chzzk 또는 afreeca)
        """
        self.init = init_var
        self.performance_manager = performance_manager
        self.DO_TEST = init_var.DO_TEST
        self.userStateData = init_var.userStateData
        self.platform = platform
        self.channel_id = channel_id
        self.wait_get_live_thumbnail_image = False
        self.DiscordWebhookSender_class = DiscordWebhookSender()
        self.IDList = init_var.IDList
        self.title_data = init_var.titleData[platform]
        self.channel_name = self.IDList[self.platform].loc[channel_id, "channelName"]
        state_update_time = self.title_data.loc[self.channel_id, "state_update_time"]
        category = self.title_data.loc[self.channel_id, "category"]
        self.data = LiveData(
            state_update_time=state_update_time,
            IDlist=self.IDList[self.platform],
            category=category,
            platform=platform,
        )
        self.get_channel_url()

        self.stream_start_id = get_stream_start_id(
            self.channel_id, self.data.state_update_time["openDate"]
        )

        if not init_var.stream_status.get(channel_id):
            init_var.stream_status[channel_id] = self.data

        if not init_var.highlight_chat.get(channel_id):
            init_var.highlight_chat[channel_id] = {}

        if not init_var.wait_make_highlight_chat.get(channel_id):
            init_var.wait_make_highlight_chat[channel_id] = False

        if self.title_data.loc[self.channel_id, "live_state"] == "OPEN":
            self.init.highlight_chat[self.channel_id][
                self.stream_start_id
            ] = highlight_chat_Data()
            self.init.highlight_chat[self.channel_id][
                self.stream_start_id
            ].last_title = self.title_data.loc[self.channel_id, "title1"]

    async def start(self):
        await self.addMSGList()
        await self.postLive_message()

    # 방송 상태를 확인하고 상태 변경 시 메시지 리스트에 추가하는 함수
    async def addMSGList(self):
        try:
            if self.wait_get_live_thumbnail_image:
                return
            # 방송 상태 데이터 가져오기
            state_data = await self._get_state_data()

            if not self._is_valid_state_data(state_data):
                return

            self._update_title_if_needed()

            # 스트림 데이터 얻기
            stream_data = self._get_stream_data(state_data)
            change_state = self._update_stream_info(stream_data, state_data)
            await self.save_profile_image()

            # 온라인 상태일 때 상태 정보 업데이트
            if self.data.live in ["OPEN", 1]:
                # self.get_channel_url()
                self.getViewer_count(state_data)
                self.getCategory(state_data)
                self.getImageURL(state_data)
                # self.init_highlight_chat()
                # self.get_init_last_title()

            # 온라인/오프라인 상태 처리
            if self._should_process_online_status(change_state):
                await self._handle_online_status(state_data)
            elif self._should_process_offline_status(change_state):
                await self._handle_offline_status(state_data)

        except Exception as e:
            error_msg = (
                f"error get state_data {self.platform} live {str(e)}.{self.channel_id}"
            )
            asyncio.create_task(log_error(error_msg))
            self.init.is_state_control["all_date"] = True
            await update_flag(self.init.supabase, "user_date", self.init.is_state_control)

    # 방송 제목이 변경되었는지 확인하고 필요시 업데이트
    def _update_title_if_needed(self):
        if (
            if_after_time(self.data.state_update_time["titleChangeDate"])
            and self._get_old_title() != self._get_title()
        ):
            self.title_data.loc[self.channel_id, "title2"] = self.title_data.loc[
                self.channel_id, "title1"
            ]
            asyncio.create_task(
                save_airing_data(
                    self.init.supabase, self.title_data, self.platform, self.channel_id, updated_keys={"title2"}
                )
            )

    def _get_channel_name(self):
        return self.IDList[self.platform].loc[self.channel_id, "channelName"]
    
    def _get_updated_values(self):
        if self.platform == "chzzk":
            updated_values = {"live_state", "chatChannelId", "oldChatChannelId", "category", "title1", "title2", "state_update_time"}
        else:
            updated_values = {"live_state", "chatChannelId", "oldChatChannelId", "title1", "title2", "state_update_time"}
            
        return updated_values

    # 메시지 전송
    async def postLive_message(self):
        try:
            if not self.data.livePostList:
                return
            message, json_data = self.data.livePostList.pop(0)

            db_name = self._get_db_name(message)
            self._log_message(message)

            # 웹훅 URL 목록 가져오기
            list_of_urls = get_list_of_urls(
                self.DO_TEST,
                self.userStateData,
                self.channel_name,
                self.channel_id,
                db_name,
            )

            # 푸시 알림 및 메시지 전송
            asyncio.create_task(send_push_notification(list_of_urls, json_data))
            asyncio.create_task(
                self.DiscordWebhookSender_class.send_messages(list_of_urls, json_data)
            )

            asyncio.create_task(
                save_airing_data(
                    self.init.supabase, self.title_data, self.platform, self.channel_id, updated_keys=self._get_updated_values()
                )
            )

        except Exception as e:
            print(f"{datetime.now()} postLiveMSG {str(e)}")
            self.data.livePostList.clear()

    # 메시지 유형에 맞는 DB 이름 반환
    def _get_db_name(self, message):
        if message == "뱅온!":
            return "뱅온 알림"
        elif message == "방제 변경":
            return "방제 변경 알림"
        elif message == "뱅종":
            return "방종 알림"
        return "알림"

    # 메시지 로깅
    def _log_message(self, message):
        now = datetime.now()
        if message == "뱅온!":
            print(
                f"{now} onLine {self.channel_name} {message}, {self.init.highlight_chat[self.channel_id]}"
            )
        elif message == "방제 변경":
            old_title = self._get_old_title()
            print(f"{now} onLine {self.channel_name} {message}")
            print(f"{now} 이전 방제: {old_title}")
            print(f"{now} 현재 방제: {self.data.title}")
        elif message == "뱅종":
            print(f"{now} offLine {self.channel_name}")

    # 이전 방송 제목 반환
    def _get_old_title(self):
        return self.title_data.loc[self.channel_id, "title2"]

    # 현재 방송 제목 반환
    def _get_title(self):
        return self.title_data.loc[self.channel_id, "title1"]

    # 방송 시작 시 제목 업데이트
    def onLineTitle(self, message):
        if message == "뱅온!":
            self.title_data.loc[self.channel_id, "live_state"] = "OPEN"
            self.get_init_last_title()
        if self.data.title != self._get_title():
            self.title_data.loc[self.channel_id, "title2"] = self._get_title()
            self.title_data.loc[self.channel_id, "title1"] = self.data.title

            self.init_highlight_chat()
            if self.stream_start_id in self.init.highlight_chat[self.channel_id]:
                self.init.highlight_chat[self.channel_id][self.stream_start_id].last_title = self.data.title

    def record_title(self, message):
        try:
            if self.data.live in ["OPEN", 1]:
                self.init_highlight_chat()
                if message == "뱅온!":
                    message = "뱅온 방제"
                after_openDate = datetime.now() - datetime.fromisoformat(
                    self.data.state_update_time["openDate"]
                )
                after_openDate_seconds = int(
                    after_openDate.total_seconds()
                )  # timedelta를 초로 변환
                after_openDate = format_time_for_comment(after_openDate_seconds)
                self.init.highlight_chat[self.channel_id][
                    self.stream_start_id
                ].timeline_comments.append(
                    {
                        "comment_after_openDate": after_openDate,
                        "text": f"{message}: {self.data.title}",
                        "description": f"{message}: {self.data.title}",
                    }
                )
        except Exception as e:
            asyncio.create_task(
                log_error(
                    f"error record_title, {str(e)}, highlight_chat:{self.init.highlight_chat[self.channel_id]}"
                )
            )

    # 방송 시작 시간 업데이트
    def onLineTime(self, message):
        if message == "뱅온!":
            self.data.state_update_time["openDate"] = self.data.temp_start_at[
                "openDate"
            ]
            self.init_highlight_chat()  # 뱅온시 highlight_chat 생성 및 초기화

    # 방송 종료 시 상태 업데이트
    def offLineTitle(self):
        self.title_data.loc[self.channel_id, "live_state"] = "CLOSE"

    # 제목이 변경되었는지 확인
    def ifChangeTitle(self):
        return self.data.title not in [
            str(self._get_title()),
            str(self._get_old_title()),
        ]

    def getMessage(self) -> str:
        raise NotImplementedError

    async def _get_state_data(self):
        raise NotImplementedError

    def _is_valid_state_data(self, state_data):
        raise NotImplementedError

    def _get_stream_data(self, state_data):
        raise NotImplementedError

    def _update_stream_info(self, stream_data, state_data):
        raise NotImplementedError

    def _should_process_online_status(self, change_state):
        raise NotImplementedError

    def _should_process_offline_status(self, change_state):
        raise NotImplementedError

    # 온라인 상태 처리 (뱅온 또는 방제 변경)
    async def _handle_online_status(self, state_data):
        message = self.getMessage()

        self.onLineTime(message)
        self.onLineTitle(message)
        self.record_title(message)
        json_data = await self.getOnAirJson(message, state_data)

        self.data.livePostList.append((message, json_data))

        asyncio.create_task(
            save_profile_data(
                self.init.supabase, self.IDList, self.platform, self.channel_id
            )
        )

        # 상태 업데이트 시간 저장
        if message == "뱅온!":
            self.data.state_update_time["myCheckopenDate"] = datetime.now().isoformat()
        self.data.state_update_time["titleChangeDate"] = datetime.now().isoformat()

    # 프로필 이미지 변경 시 저장
    async def save_profile_image(self):
        if (
            self.IDList[self.platform].loc[self.channel_id, "profile_image"]
            != self.data.profile_image
        ):
            self.IDList[self.platform].loc[
                self.channel_id, "profile_image"
            ] = self.data.profile_image
            asyncio.create_task(
                save_profile_data(
                    self.init.supabase, self.IDList, self.platform, self.channel_id
                )
            )

    async def getOnAirJson(self, message, state_data):
        raise NotImplementedError

    async def _handle_offline_status(self, state_data):
        raise NotImplementedError

    # 시작/종료 시간 ISO 형식으로 반환
    def getStarted_at(self, status: str):
        if (
            status not in self.data.temp_start_at
            or self.data.temp_start_at[status] is None
        ):
            return
        time_str = self.data.temp_start_at[status]
        time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        self.data.temp_start_at[status] = time.isoformat()
        return self.data.temp_start_at[status]

    def get_channel_url(self):
        raise NotImplementedError

    def getViewer_count(self, state_data):
        raise NotImplementedError

    def getCategory(self, state_data):
        raise NotImplementedError

    def getImageURL(self, state_data):
        raise NotImplementedError

    def init_highlight_chat(self):
        try:
            self.stream_start_id = get_stream_start_id(
                self.channel_id, self.data.state_update_time["openDate"]
            )

            # 스트림 ID가 없으면 초기화
            if self.stream_start_id not in self.init.highlight_chat[self.channel_id]:
                self._cleanup_old_highlights()  # 오래된 데이터 정리
                self.init.highlight_chat[self.channel_id][
                    self.stream_start_id
                ] = highlight_chat_Data()

        except Exception as e:
            asyncio.create_task(
                log_error(
                    f"error init_highlight_chat: {str(e)}, channel_id: {self.channel_id}"
                )
            )

    def get_init_last_title(self):
        try:
            if self.stream_start_id in self.init.highlight_chat[self.channel_id]:
                if not self.init.highlight_chat[self.channel_id][
                    self.stream_start_id
                ].last_title:
                    self.init.highlight_chat[self.channel_id][
                        self.stream_start_id
                    ].last_title = self.data.title
        except Exception as e:
            asyncio.create_task(log_error(f"error get_init_last_title: {str(e)}"))

    def _cleanup_old_highlights(self, days_threshold: int = 14):
        """
        현재 채널의 14일 이상 지난 하이라이트 채팅 데이터를 정리하는 메서드

        Args:
            days_threshold: 삭제할 데이터의 기준 일수 (기본값: 14일)
        """
        try:
            current_time = datetime.now()
            threshold_time = current_time - timedelta(days=days_threshold)

            # 현재 채널의 하이라이트 채팅 데이터가 없으면 스킵
            if self.channel_id not in self.init.highlight_chat:
                return 0

            channel_data = self.init.highlight_chat[self.channel_id]
            streams_to_remove = []

            # 각 스트림의 생성 시간 확인
            for stream_id in list(channel_data.keys()):
                try:
                    # stream_id에서 타임스탬프 추출
                    stream_timestamp = get_timestamp_from_stream_id(stream_id)

                    # 14일 이상 지난 데이터인지 확인
                    if stream_timestamp < threshold_time:
                        streams_to_remove.append(stream_id)

                except ValueError as e:
                    # 타임스탬프를 파싱할 수 없는 경우 로그 기록 후 건너뛰기
                    print(
                        f"{current_time} cleanup: 타임스탬프 파싱 실패 - {stream_id}: {str(e)}"
                    )
                    continue

            # 오래된 스트림 데이터 제거
            for stream_id in streams_to_remove:
                del self.init.highlight_chat[self.channel_id][stream_id]

            if streams_to_remove:
                print(
                    f"{current_time} [{self.channel_id}] {len(streams_to_remove)}개의 오래된 하이라이트 데이터 정리"
                )

            return len(streams_to_remove)

        except Exception as e:
            asyncio.create_task(
                log_error(
                    f"_cleanup_old_highlights 오류: {str(e)}, channel_id: {self.channel_id}"
                )
            )
            return 0

    async def get_live_thumbnail_image(self, state_data, message=None):
        raise NotImplementedError


# 치지직 구현 클래스
class chzzk_live_message(base_live_message):
    """치지직 플랫폼 라이브 모니터링 클래스"""

    def __init__(
        self, init_var: initVar, performance_manager: PerformanceManager, chzzk_id
    ):
        """
        초기화 함수

        Args:
            init_var: 초기화 변수
            chzzk_id: 치지직 채널 ID
        """
        super().__init__(init_var, performance_manager, chzzk_id, "chzzk")

    # 치지직 채널 상태 데이터 가져오기
    async def _get_state_data(self):
        return await get_message(
            self.performance_manager,
            "chzzk",
            chzzk_getLink(self.IDList[self.platform].loc[self.channel_id, "uid"]),
        )

    # 치지직 상태 데이터 유효성 검사
    def _is_valid_state_data(self, state_data):
        try:
            return state_data and state_data["code"] == 200
        except Exception as e:
            if len(state_data) > 200:
                state_data = state_data[:200]
            asyncio.create_task(
                log_error(
                    f"{datetime.now()} _is_valid_state_data.{self.channel_id}.{str(e)}.{state_data}"
                )
            )
            return False

    # 치지직 스트림 데이터 추출
    def _get_stream_data(self, state_data):
        return chzzk_getChannelOffStateData(
            state_data["content"],
            self.IDList[self.platform].loc[self.channel_id, "uid"],
            self.IDList[self.platform].loc[self.channel_id, "profile_image"],
        )

    # 치지직 스트림 정보 업데이트
    def _update_stream_info(self, stream_data, state_data):
        def is_recent_stream(status):
            if state_data["content"][status]:
                return datetime.fromisoformat(
                    state_data["content"][status]
                ) > datetime.fromisoformat(self.data.state_update_time[status])

        if not self.data.live:
            self.data.live, self.data.title, self.data.profile_image = stream_data

        _, self.data.title, self.data.profile_image = stream_data

        if (openDate:= is_recent_stream("openDate")) or (closeDate:= is_recent_stream("closeDate")):
            self.data.temp_start_at["openDate"] = state_data["content"]["openDate"]
            self.data.temp_start_at["closeDate"] = state_data["content"]["closeDate"]
            self.getStarted_at("openDate")
            self.getStarted_at("closeDate")
            self.data.live, self.data.title, self.data.profile_image = stream_data
            if openDate: self.data.state_update_time["is_firstConnect"] = True
            return "openDate" if openDate else "closeDate"

    # 치지직 온라인 상태 처리 여부 확인(온라인 상태인지 확인)
    def _should_process_online_status(self, change_state):
        return (
            self.checkStateTransition("OPEN") or (self.ifChangeTitle())
        ) and if_after_time(self.data.state_update_time["myCheckcloseDate"], sec=15) or change_state == "openDate"

    # 치지직 오프라인 상태 처리 여부 확인(오프라인인지 확인)
    def _should_process_offline_status(self, change_state):
        return self.checkStateTransition("CLOSE") and if_after_time(
            self.data.state_update_time["myCheckopenDate"], sec=15
        ) or change_state == "closeDate"

    # 치지직 오프라인 상태 처리
    async def _handle_offline_status(self, state_data):
        message = "뱅종"
        self.offLineTitle()
        self.offLineTime()

        json_data = await self.getOffJson(state_data)
        self.data.livePostList.append((message, json_data))

        self.data.state_update_time["myCheckcloseDate"] = datetime.now().isoformat()
        self.data.state_update_time["titleChangeDate"] = datetime.now().isoformat()

    # 방송 종료 시간 업데이트
    def offLineTime(self):
        self.data.state_update_time["closeDate"] = self.data.temp_start_at["closeDate"]

        stream_end_id = get_stream_start_id(
            self.channel_id, self.data.state_update_time["closeDate"]
        )
        if self.stream_start_id in self.init.highlight_chat[self.channel_id]:
            self.init.highlight_chat[self.channel_id][
                self.stream_start_id
            ].stream_end_id = stream_end_id

    # 치지직 채널 URL 생성
    def get_channel_url(self):
        self.data.channel_url = f'https://chzzk.naver.com/live/{self.IDList[self.platform].loc[self.channel_id, "uid"]}'
        return self.data.channel_url

    # 치지직 시청자 수 가져오기
    def getViewer_count(self, state_data):
        view_count = state_data["content"]["concurrentUserCount"]
        self.data.view_count = view_count

    # 치지직 카테고리 가져오기
    def getCategory(self, state_data):
        category = state_data["content"]["liveCategoryValue"]
        if self.data.category != category:
            self.data.category = category
            self.title_data.loc[self.channel_id, "category"] = category
            asyncio.create_task(
                save_airing_data(
                    self.init.supabase, self.title_data, self.platform, self.channel_id, updated_keys={"category"}
                )
            )

    # 상태 변경 메시지 결정 (뱅온 또는 방제 변경)
    def getMessage(self) -> str:
        return "뱅온!" if (self.checkStateTransition("OPEN")) else "방제 변경"

    # get author json
    def get_author(self):
        avatar_url = self.IDList[self.platform].loc[self.channel_id, "profile_image"]
        channel_code = self.IDList[self.platform].loc[self.channel_id, "uid"]
        video_url = f"https://chzzk.naver.com/{channel_code}"
        author = {"name": self.channel_name, "url": video_url, "icon_url": avatar_url}
        return author

    # 상태 전환 확인 (OPEN 또는 CLOSE)
    def checkStateTransition(self, target_state: str):
        if self.data.live != target_state or self.title_data.loc[
            self.channel_id, "live_state"
        ] != ("CLOSE" if target_state == "OPEN" else "OPEN"):
            return False
        return (
            self.data.temp_start_at[
                "openDate" if target_state == "OPEN" else "closeDate"
            ]
            > self.data.state_update_time[
                "closeDate" if target_state == "OPEN" else "openDate"
            ]
        )

    # 치지직 썸네일 이미지(실시간 방송 화면 이미지로 변환 후) 가져오기
    async def get_live_thumbnail_image(self, state_data, message):
        self.wait_get_live_thumbnail_image = True
        for count in range(50):
            time_difference = (
                datetime.now()
                - datetime.fromisoformat(self.data.state_update_time["openDate"])
            ).total_seconds()

            if (
                message == "뱅온!"
                or self.title_data.loc[self.channel_id, "live_state"] == "CLOSE"
                or time_difference < 15
            ):
                thumbnail_image = ""
                break

            thumbnail_image = await self.get_thumbnail_image(state_data)
            if thumbnail_image is None:
                print(f"{datetime.now()} wait make thumbnail1 {count}")
                await asyncio.sleep(0.1)
                continue
            break

        else:
            thumbnail_image = ""
        self.wait_get_live_thumbnail_image = False

        return thumbnail_image

    # 치지직 썸네일 이미지 처리
    async def get_thumbnail_image(self, state_data):
        try:
            if state_data["content"]["liveImageUrl"] is None:
                return None

            # 이미지 URL 가져오기
            self.getImageURL(state_data)

            return await upload_image_to_imgbb(
                self.init,
                self.performance_manager,
                self.channel_id,
                self.data.thumbnail_url,
                platform_prefix="chzzk",
            )

        except Exception as e:
            asyncio.create_task(
                log_error(f"{datetime.now()} wait make thumbnail2 {str(e)}")
            )
            import traceback

            traceback.print_exc()
            return None

    # 이미지 파일로 저장
    def saveImage(self, state_data):
        urlretrieve(self.getImageURL(state_data), self.image_path)

    # 치지직 이미지 URL 가져오기
    def getImageURL(self, state_data) -> str:
        link = state_data["content"]["liveImageUrl"]
        if link is None:
            return
        link = link.replace("{type", "")
        link = link.replace("}.jpg", "0.jpg")
        self.data.thumbnail_url = link
        return self.data.thumbnail_url

    # 온라인 알림 메시지 JSON 생성
    async def getOnAirJson(self, message, state_data):
        if self.data.live == "CLOSE":
            return self.get_state_data_change_title_json(message)

        self.getViewer_count(state_data)
        thumbnail_url = await self.get_live_thumbnail_image(state_data, message)

        if message == "뱅온!":
            return self.get_online_state_json(message, thumbnail_url)

        return self.get_online_titleChange_state_json(message, thumbnail_url)

    # 뱅온 JSON 데이터 생성
    def get_online_state_json(self, message, thumbnail_url):
        avatar_url = self.IDList[self.platform].loc[self.channel_id, "profile_image"]

        embeds = {
            "color": int(
                self.IDList[self.platform].loc[self.channel_id, "channel_color"]
            ),
            "author": self.get_author(),
            "fields": [
                {"name": "방제", "value": self.data.title, "inline": True},
                # {"name": ':busts_in_silhouette: 시청자수',
                # "value": self.data.view_count, "inline": True}
            ],
            "title": f"{self.channel_name} {message}\n",
            "url": self.get_channel_url(),
            # "image": {"url": thumbnail_url},
            "footer": {
                "text": f"뱅온 시간",
                "inline": True,
                "icon_url": iconLinkData().chzzk_icon,
            },
            "timestamp": changeUTCtime(self.data.state_update_time["openDate"]),
        }

        return {
            "username": self.channel_name,
            "avatar_url": avatar_url,
            "embeds": [embeds],
        }

    # 온라인 상태에서의 방제 변경 JSON 데이터 생성
    def get_online_titleChange_state_json(self, message, thumbnail_url):
        embeds = {
            "color": int(
                self.IDList[self.platform].loc[self.channel_id, "channel_color"]
            ),
            "author": self.get_author(),
            "fields": [
                {"name": "방제", "value": self.data.title, "inline": True},
                {
                    "name": ":busts_in_silhouette: 시청자수",
                    "value": self.data.view_count,
                    "inline": True,
                },
            ],
            "title": f"{self.channel_name} {message}\n",
            "url": self.get_channel_url(),
            "image": {"url": thumbnail_url},
            "footer": {
                "text": f"뱅온 시간",
                "inline": True,
                "icon_url": iconLinkData().chzzk_icon,
            },
            "timestamp": changeUTCtime(self.data.state_update_time["openDate"]),
        }

        self.get_author()
        return {
            "username": self.channel_name,
            "avatar_url": self.IDList[self.platform].loc[
                self.channel_id, "profile_image"
            ],
            "embeds": [embeds],
        }

    # 오프라인 상태에서의 방제 변경 메시지 JSON 데이터 생성
    def get_state_data_change_title_json(self, message):
        embeds = {
            "color": int(
                self.IDList[self.platform].loc[self.channel_id, "channel_color"]
            ),
            "author": self.get_author(),
            "fields": [
                {"name": "이전 방제", "value": str(self._get_title()), "inline": True},
                {"name": "현재 방제", "value": self.data.title, "inline": True},
            ],
            "title": f"{self.channel_name} {message}\n",
            "url": self.get_channel_url(),
            "footer": {"icon_url": iconLinkData().chzzk_icon},
        }

        return {
            "username": self.channel_name,
            "avatar_url": self.IDList[self.platform].loc[
                self.channel_id, "profile_image"
            ],
            "embeds": [embeds],
        }

    # 뱅종 JSON 데이터 생성
    async def getOffJson(self, state_data):
        embeds = {
            "color": int(
                self.IDList[self.platform].loc[self.channel_id, "channel_color"]
            ),
            "author": self.get_author(),
            "title": self.channel_name + " 방송 종료\n",
            "footer": {
                "text": f"방종 시간",
                "inline": True,
                "icon_url": iconLinkData().chzzk_icon,
            },
            "timestamp": changeUTCtime(self.data.state_update_time["closeDate"]),
        }
        # thumbnail_url = await self.get_live_thumbnail_image(state_data, "방종")
        defaultThumbnailImageUrl = state_data["content"]["defaultThumbnailImageUrl"]

        if not defaultThumbnailImageUrl is None:
            embeds["image"] = {"url": defaultThumbnailImageUrl}

        return {
            "username": self.channel_name,
            "avatar_url": self.IDList[self.platform].loc[
                self.channel_id, "profile_image"
            ],
            "embeds": [embeds],
        }


# 아프리카 구현 클래스
class afreeca_live_message(base_live_message):
    """아프리카TV 플랫폼 라이브 모니터링 클래스"""

    def __init__(
        self, init_var: initVar, performance_manager: PerformanceManager, channel_id
    ):
        super().__init__(init_var, performance_manager, channel_id, "afreeca")

    # 아프리카 채널 상태 데이터 가져오기
    async def _get_state_data(self):
        return await get_message(
            self.performance_manager,
            "afreeca",
            afreeca_getLink(self.IDList[self.platform].loc[self.channel_id, "uid"]),
        )

    # 아프리카 상태 데이터 유효성 검사
    def _is_valid_state_data(self, state_data):
        try:
            state_data["station"]["user_id"]
            return True
        except:
            return False

    # 아프리카 스트림 데이터 추출
    def _get_stream_data(self, state_data):
        return afreeca_getChannelOffStateData(
            state_data,
            self.IDList[self.platform].loc[self.channel_id, "uid"],
            self.IDList[self.platform].loc[self.channel_id, "profile_image"],
        )

    # 아프리카 스트림 정보 업데이트
    def _update_stream_info(self, stream_data, state_data):
        def is_recent_stream(status):
            if state_data["station"]["broad_start"] != "0000-00-00 00:00:00":
                return datetime.fromisoformat(
                    state_data["station"]["broad_start"]
                ) > datetime.fromisoformat(self.data.state_update_time[status])
        change_state = None 
        self.update_broad_no(state_data)
        if is_recent_stream("openDate"):
            self.data.temp_start_at["openDate"] = state_data["station"]["broad_start"]
            self.getStarted_at("openDate")
            change_state = "openDate"
        self.data.live, self.data.title, self.data.profile_image = stream_data
        self.IDList[self.platform].loc[
            self.channel_id, "profile_image"
        ] = self.data.profile_image
        return change_state

    # 방송 번호 업데이트(주소 링크에 사용될 번호)
    def update_broad_no(self, state_data):
        if (
            state_data["broad"]
            and state_data["broad"]["broad_no"]
            != int(self.title_data.loc[self.channel_id, "chatChannelId"])
        ):
            self.title_data.loc[self.channel_id, "oldChatChannelId"] = (
                self.title_data.loc[self.channel_id, "chatChannelId"]
            )
            self.title_data.loc[self.channel_id, "chatChannelId"] = str(state_data["broad"][
                "broad_no"
            ])

    # 아프리카 온라인 상태 처리 여부 확인
    def _should_process_online_status(self, change_state):
        return (
            self.turnOnline() or (self.data.title and self.ifChangeTitle())
        ) and if_after_time(self.data.state_update_time["myCheckcloseDate"], sec=15) or change_state == "openDate"

    # 아프리카 오프라인 상태 처리 여부 확인
    def _should_process_offline_status(self, change_state):
        return self.turnOffline() and if_after_time(
            self.data.state_update_time["myCheckopenDate"], sec=15
        ) or change_state == "closeDate"

    # 아프리카 오프라인 상태 처리
    async def _handle_offline_status(self, state_data):
        message = "뱅종"
        self.data.state_update_time["is_firstConnect"] = True
        current_time = datetime.now()
        json_data = self.getOffJson(current_time)

        self.offLineTitle()

        self.data.livePostList.append((message, json_data))

        self.data.state_update_time["myCheckcloseDate"] = current_time.isoformat()
        self.data.state_update_time["titleChangeDate"] = current_time.isoformat()

        stream_end_id = get_stream_start_id(
            self.channel_id, self.data.state_update_time["myCheckcloseDate"]
        )
        self.init.highlight_chat[self.channel_id][
            self.stream_start_id
        ].stream_end_id = stream_end_id

    # 아프리카 채널 URL 생성
    def get_channel_url(self):
        afreecaID = self.IDList[self.platform].loc[self.channel_id, "uid"]
        bno = int(self.title_data.loc[self.channel_id, "chatChannelId"])
        self.data.channel_url = f"https://play.sooplive.co.kr/{afreecaID}/{bno}"
        return self.data.channel_url

    # 아프리카 시청자 수 가져오기
    def getViewer_count(self, state_data):
        view_count = state_data["broad"]["current_sum_viewer"]
        self.data.view_count = view_count

    # 아프리카 카테고리 가져오기
    def getCategory(self, state_data):
        pass

    # 상태 변경 메시지 결정 (뱅온 또는 방제 변경)
    def getMessage(self):
        return "뱅온!" if (self.turnOnline()) else "방제 변경"

    # get author json
    def get_author(self):
        avatar_url = self.IDList[self.platform].loc[self.channel_id, "profile_image"]
        afreeca_id = self.IDList[self.platform].loc[self.channel_id, "uid"]
        video_url = video_url = f"https://www.sooplive.co.kr/station/{afreeca_id}"
        author = {"name": self.channel_name, "url": video_url, "icon_url": avatar_url}
        return author

    # 온라인으로 상태 변경되었는지 확인
    def turnOnline(self):
        now_time = self.data.temp_start_at["openDate"]
        old_time = self.data.state_update_time["openDate"]
        return (
            self.data.live == 1
            and self.title_data.loc[self.channel_id, "live_state"] == "CLOSE"
            and now_time > old_time
        )

    # 오프라인으로 상태 변경되었는지 확인
    def turnOffline(self):
        return (
            self.data.live == 0
            and self.title_data.loc[self.channel_id, "live_state"] == "OPEN"
        )

    # 아프리카 썸네일 이미지 가져오기
    async def get_live_thumbnail_image(self, state_data, message=None):
        self.wait_get_live_thumbnail_image = True
        for count in range(50):
            thumbnail_image = await self.get_thumbnail_image()
            if thumbnail_image is None:
                # print(f"{datetime.now()} wait make thumbnail 1 .{count}.{str(self.getImageURL())}")
                await asyncio.sleep(0.1)
                continue
            break
        else:
            thumbnail_image = ""
        self.wait_get_live_thumbnail_image = False

        return thumbnail_image

    # 아프리카 썸네일 이미지 처리
    async def get_thumbnail_image(self):
        try:
            # 이미지 URL 가져오기
            self.getImageURL()

            return await upload_image_to_imgbb(
                self.init,
                self.performance_manager,
                self.channel_id,
                self.data.thumbnail_url,
                platform_prefix="afreeca",
            )

        except Exception as e:
            print(f"{datetime.now()} 썸네일 이미지 처리 오류: {str(e)}")
            import traceback

            traceback.print_exc()
            return None

    # 이미지 파일로 저장
    def saveImage(self):
        urlretrieve(self.getImageURL(), self.image_path)

    # 아프리카 이미지 URL 가져오기
    def getImageURL(self, state_data="") -> str:
        link = f"http://liveimg.afreecatv.com/m/{self.title_data.loc[self.channel_id, 'chatChannelId']}"
        self.data.thumbnail_url = link
        return self.data.thumbnail_url

    # 온라인 알림 메시지 JSON 생성
    async def getOnAirJson(self, message, state_data):
        self.getViewer_count(state_data)
        thumbnail_url = await self.get_live_thumbnail_image(state_data)

        return self.get_online_state_json(message, thumbnail_url)

    # 뱅온 JSON 데이터 생성
    def get_online_state_json(self, message, thumbnail_url):
        avatar_url = self.IDList[self.platform].loc[self.channel_id, "profile_image"]

        embeds = {
            "color": int(
                self.IDList[self.platform].loc[self.channel_id, "channel_color"]
            ),
            "author": self.get_author(),
            "fields": [
                {"name": "방제", "value": self.data.title, "inline": True},
                {
                    "name": ":busts_in_silhouette: 시청자수",
                    "value": self.data.view_count,
                    "inline": True,
                },
            ],
            "title": f"{self.channel_name} {message}\n",
            "url": self.get_channel_url(),
            "image": {"url": thumbnail_url},
            "footer": {
                "text": f"뱅온 시간",
                "inline": True,
                "icon_url": iconLinkData().soop_icon,
            },
            "timestamp": changeUTCtime(self.data.state_update_time["openDate"]),
        }

        return {
            "username": self.channel_name,
            "avatar_url": avatar_url,
            "embeds": [embeds],
        }

    # 뱅종 JSON 데이터 생성
    def getOffJson(self, current_time: datetime):
        embeds = {
            "color": int(
                self.IDList[self.platform].loc[self.channel_id, "channel_color"]
            ),
            "author": self.get_author(),
            "title": self.channel_name + " 방송 종료\n",
            "footer": {
                "text": f"방종 시간",
                "inline": True,
                "icon_url": iconLinkData().soop_icon,
            },
            "timestamp": changeUTCtime(current_time.isoformat()),
        }

        return {
            "username": self.channel_name,
            "avatar_url": self.IDList[self.platform].loc[
                self.channel_id, "profile_image"
            ],
            "embeds": [embeds],
        }


# 썸네일 이미지를 Imgur에 업로드하는 공통 메서드
async def upload_image_to_imgur(
    stream_status: LiveData, channel_id, image_url, platform_prefix="thumbnail"
):
    try:
        # 비동기 이미지 다운로드
        response = await asyncio.to_thread(get, image_url, timeout=5)

        if response.status_code != 200:
            print(f"{datetime.now()} 이미지 다운로드 실패: {response.status_code}")
            return None

        # Imgur 요청 전 잠시 대기 (혹시 모를 상황 대비)
        await asyncio.sleep(1)

        # 환경 변수에서 Imgur 클라이언트 ID 가져오기
        client_id = environ.get("IMGUR_CLIENT_ID")
        if not client_id:
            print(f"{datetime.now()} Imgur 클라이언트 ID가 설정되지 않았습니다")
            return None

        print(
            f"{datetime.now()} Imgur 업로드 준비 시작 - 이미지 크기: {len(response.content)} bytes"
        )
        print(f"{datetime.now()} Imgur 업로드 준비: {image_url}")

        # 이미지 데이터를 base64로 인코딩
        b64_image = base64.b64encode(response.content).decode("utf-8")

        print(f"{datetime.now()} Base64 인코딩 완료 - 크기: {len(b64_image)} chars")

        # 채널 정보 및 타임스탬프
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Imgur에 이미지 업로드
        headers = {
            "Authorization": f"Client-ID {client_id}",
            "User-Agent": "streamAlert/1.0 (kimboxu@gmail.com)",
            "X-Forwarded-For": "127.0.0.1",  # 선택적
        }

        channel_name = stream_status.IDlist.loc[channel_id, "channelName"]
        data = {
            "image": b64_image,
            "type": "base64",
            "name": f"{platform_prefix}_{channel_id}_{timestamp}.jpg",
            "title": f"{channel_name} {stream_status.platform} 생방송 썸네일",
            "description": f"채널: {channel_name}, 채널ID: {channel_id}, 플랫폼: {stream_status.platform}, 시간: {datetime.now().isoformat()}",
        }

        imgur_response = post(
            "https://api.imgur.com/3/image", headers=headers, data=data, timeout=10
        )

        # 응답 확인
        if imgur_response.status_code == 200:
            imgur_data = imgur_response.json()
            thumbnail_url = imgur_data["data"]["link"]
            delete_hash = imgur_data["data"]["deletehash"]
            print(
                f"{datetime.now()} Imgur 업로드 성공: {thumbnail_url} (삭제 해시: {delete_hash})"
            )

            return thumbnail_url
        else:
            print(f"{datetime.now()} Imgur 업로드 실패: {imgur_response.status_code}")
            print(f"응답: {imgur_response.text}")
            # ,"status":"Too Many Requests"
            if imgur_response.status_code == 429:
                return ""
            return None

    except Exception as e:
        print(f"{datetime.now()} 썸네일 이미지 처리 오류: {str(e)}")
        import traceback

        traceback.print_exc()
        return None


async def upload_image_to_imgbb(
    init: initVar,
    performance_manager: PerformanceManager,
    channel_id: str,
    image_url: str,
    platform_prefix: str = "thumbnail",
) -> str | None:
    # 재시도 설정
    MAX_RETRIES = 3
    BASE_DELAY = 1  # 초
    UPLOAD_TIMEOUT = 20  # 업로드 타임아웃 (초)

    try:
        if not init.is_state_control["is_upload"]:
            return ""
        # API 키 확인
        init.api_key_cnt = (init.api_key_cnt + 1) % len(init.IMGBB_API_KEY_LIST)
        api_key = init.IMGBB_API_KEY_LIST[init.api_key_cnt]
        if not api_key:
            print(f"{datetime.now()} ImgBB API 키가 설정되지 않았습니다")
            return None

        # 1. 이미지 다운로드 (get_message가 자동으로 재시도 처리)
        # print(f"{datetime.now()} 이미지 다운로드 시작: {image_url}")

        response = await get_message(performance_manager, "image", image_url)

        # 다운로드 실패 체크
        if (status_code := response.get("status_code", None)) != 200:
            # print(f"{datetime.now()} 이미지 다운로드 실패: {status_code}")
            return None

        # print(f"{datetime.now()} 이미지 다운로드 성공: {status_code}")

        # 이미지 크기 확인
        content = response.get("content", "")
        image_size = len(content)
        max_size = 32 * 1024 * 1024  # 32MB

        # print(f"{datetime.now()} 이미지 크기: {image_size / 1024 / 1024:.2f}MB")

        if image_size > max_size:
            print(
                f"{datetime.now()} 이미지 크기 초과 ({image_size / 1024 / 1024:.1f}MB > 32MB)"
            )
            return None

        if image_size == 0:
            print(f"{datetime.now()} 이미지 크기가 0바이트입니다")
            return None

        # Base64 인코딩
        try:
            b64_image = base64.b64encode(content).decode("utf-8")
            # print(f"{datetime.now()} Base64 인코딩 완료 - 크기: {len(b64_image)} chars")
        except Exception as e:
            print(f"{datetime.now()} Base64 인코딩 실패: {str(e)}")
            return None

        # 메타데이터 준비
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{platform_prefix}_{channel_id}_{timestamp}"

        # ImgBB API 요청 데이터
        data = {
            "key": api_key,
            "image": b64_image,
            "name": filename,
            "expiration": 0,  # 만료 없음
        }

        # aiohttp 세션으로 재시도 로직 수행
        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            for attempt in range(MAX_RETRIES):
                # 이벤트 루프 양보
                await asyncio.sleep(0.001)
                start_time = datetime.now()

                try:
                    # print(f"{datetime.now()} ImgBB 업로드 시도 {attempt + 1}/{MAX_RETRIES}...")

                    # aiohttp를 사용한 비동기 POST 요청
                    async with session.post(
                        "https://api.imgbb.com/1/upload",
                        data=data,
                        timeout=UPLOAD_TIMEOUT,
                    ) as imgbb_response:

                        end_time = datetime.now()
                        response_time_ms = int(
                            (end_time - start_time).total_seconds() * 1000
                        )

                        # 성능 로깅
                        asyncio.create_task(
                            performance_manager.log_api_performance(
                                api_type="imgbb_upload",
                                response_time_ms=response_time_ms,
                                is_success=imgbb_response.status == 200,
                                http_status_code=imgbb_response.status,
                                retry_count=attempt,
                            )
                        )

                        # 응답 처리
                        if imgbb_response.status == 200:
                            try:
                                result_data = await imgbb_response.json()
                                if result_data.get("success"):
                                    thumbnail_url = result_data["data"]["url"]
                                    print(
                                        f"{datetime.now()} ImgBB 업로드 성공({api_key[:5]}): {thumbnail_url}"
                                    )
                                    return thumbnail_url
                                else:
                                    error_msg = result_data.get("error", {}).get(
                                        "message", "Unknown error"
                                    )
                                    print(
                                        f"{datetime.now()} ImgBB API 오류({api_key[:5]}): {error_msg}"
                                    )

                                    # 마지막 시도에서 실패한 경우
                                    if attempt == MAX_RETRIES - 1:
                                        return None

                            except Exception as e:
                                print(
                                    f"{datetime.now()} ImgBB 응답 파싱 실패({api_key[:5]}): {str(e)}"
                                )

                                # 마지막 시도에서 실패한 경우
                                if attempt == MAX_RETRIES - 1:
                                    return None

                        elif imgbb_response.status == 429:
                            print(
                                f"{datetime.now()} ImgBB 레이트 제한({api_key[:5]}) ({imgbb_response.status})"
                            )
                            return ""  # 빈 문자열로 재시도 방지

                        elif imgbb_response.status == 400:
                            response_text = await imgbb_response.text()
                            print(
                                f"{datetime.now()} ImgBB 잘못된 요청({api_key[:5]}) ({imgbb_response.status}): {response_text[:200]}"
                            )
                            return ""  # 빈 문자열로 재시도 방지

                        elif imgbb_response.status == 503:
                            response_text = await imgbb_response.text()
                            if "Down for maintenance" in response_text:
                                return ""  # 빈 문자열로 재시도 방지

                        else:
                            response_text = await imgbb_response.text()
                            print(
                                f"{datetime.now()} ImgBB 업로드 실패({api_key[:5]}): {imgbb_response.status}"
                            )
                            print(f"응답: {response_text[:200]}")

                            # 마지막 시도에서 실패한 경우
                            if attempt == MAX_RETRIES - 1:
                                return None

                    # 지수 백오프 적용 (재시도가 필요한 경우)
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(BASE_DELAY * (2**attempt))

                except asyncio.TimeoutError:
                    end_time = datetime.now()
                    response_time_ms = int(
                        (end_time - start_time).total_seconds() * 1000
                    )

                    # 타임아웃 로깅
                    asyncio.create_task(
                        performance_manager.log_api_performance(
                            api_type="imgbb_upload",
                            response_time_ms=response_time_ms,
                            is_success=False,
                            error_type="TimeoutError",
                            retry_count=attempt,
                        )
                    )

                    print(
                        f"{datetime.now()} ImgBB 업로드 타임아웃({api_key[:5]}) (시도 {attempt + 1}/{MAX_RETRIES})"
                    )

                    # 마지막 시도에서 실패한 경우
                    if attempt == MAX_RETRIES - 1:
                        return ""  # 빈 문자열로 재시도 방지

                    # 지수 백오프 적용
                    await asyncio.sleep(BASE_DELAY * (2**attempt))

                except ClientError as e:
                    end_time = datetime.now()
                    response_time_ms = int(
                        (end_time - start_time).total_seconds() * 1000
                    )

                    # 연결 오류 로깅
                    asyncio.create_task(
                        performance_manager.log_api_performance(
                            api_type="imgbb_upload",
                            response_time_ms=response_time_ms,
                            is_success=False,
                            error_type=type(e).__name__,
                            error_message=str(e)[:200],
                            retry_count=attempt,
                        )
                    )

                    print(
                        f"{datetime.now()} ImgBB 연결 오류({api_key[:5]}) (시도 {attempt + 1}/{MAX_RETRIES}): {type(e).__name__}"
                    )

                    # 마지막 시도에서 실패한 경우
                    if attempt == MAX_RETRIES - 1:
                        return ""  # 빈 문자열로 재시도 방지

                    # 지수 백오프 적용
                    await asyncio.sleep(BASE_DELAY * (2**attempt))

                except Exception as e:
                    end_time = datetime.now()
                    response_time_ms = int(
                        (end_time - start_time).total_seconds() * 1000
                    )

                    # 기타 예외 로깅
                    asyncio.create_task(
                        performance_manager.log_api_performance(
                            api_type="imgbb_upload",
                            response_time_ms=response_time_ms,
                            is_success=False,
                            error_type=type(e).__name__,
                            error_message=str(e)[:200],
                            retry_count=attempt,
                        )
                    )

                    print(
                        f"{datetime.now()} ImgBB 업로드 오류({api_key[:5]}) (시도 {attempt + 1}/{MAX_RETRIES}): {type(e).__name__}: {str(e)[:100]}"
                    )

                    # 마지막 시도에서 실패한 경우
                    if attempt == MAX_RETRIES - 1:
                        return ""  # 빈 문자열로 재시도 방지

                    # 지수 백오프 적용
                    await asyncio.sleep(BASE_DELAY * (2**attempt))

        # 모든 재시도 실패
        return None

    except Exception as e:
        print(
            f"{datetime.now()} ImgBB 업로드 전체 프로세스 오류({api_key[:5]}): {type(e).__name__}: {str(e)[:100]}"
        )
        import traceback

        traceback.print_exc()
        return None


# 디버깅 용도 실행 함수
async def main_loop(init):

    while True:
        try:
            if init.count % 2 == 0:
                await userDataVar(init)

            # 치지직과 아프리카 스트리머들의 라이브 상태 확인 태스크 생성
            chzzk_live_tasks = [
                asyncio.create_task(chzzk_live_message(init, channel_id).start())
                for channel_id in init.IDList["chzzk"]["channelID"]
            ]
            afreeca_live_tasks = [
                asyncio.create_task(afreeca_live_message(init, channel_id).start())
                for channel_id in init.IDList["afreeca"]["channelID"]
            ]

            tasks = [
                *chzzk_live_tasks,
                *afreeca_live_tasks,
            ]

            # 모든 태스크 실행
            await asyncio.gather(*tasks)
            await fSleep(init)
            fCount(init)

        except Exception as e:
            asyncio.create_task(log_error(f"Error in main loop: {str(e)}"))
            await asyncio.sleep(1)


# 디버깅 용도 메인 함수
async def main():
    from shared_state import StateManager

    state = StateManager.get_instance()
    init = await state.initialize()
    from my_app import initialize_firebase

    initialize_firebase(False)

    await asyncio.create_task(main_loop(init))


if __name__ == "__main__":
    asyncio.run(main())
