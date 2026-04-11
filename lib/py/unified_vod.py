import asyncio
import aiohttp
from os import environ
from pathlib import Path
from json import loads, load
from abc import ABC, abstractmethod
from shared_state import StateManager
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from improved_get_message import get_message
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from notification_service import send_push_notification
from make_log_api_performance import PerformanceManager
from base import (
    changeUTCtime,
    iconLinkData,
    initVar,
    save_video_data,
    if_after_time,
    log_error,
    getChzzkCookie,
    getDefaultHeaders,
    getAfreecaCookie,
    calculate_stream_duration,
    format_time_for_comment,
    get_timestamp_from_stream_id,
)


@dataclass
class VOD_Data:
    """플랫폼 공통 VOD 데이터를 저장하는 클래스"""

    videoNo: int = 0  # 비디오 번호/ID
    videoTitle: str = ""  # 비디오 제목
    publishDate: datetime = datetime.now()  # 게시 날짜
    thumbnailImageUrl: str = ""  # 썸네일 이미지 URL
    videoCategoryValue: str = ""  # 비디오 카테고리
    video_alarm_List: list = field(default_factory=list)
    duration: int = 0  # 비디오 길이(초)
    platform: str = ""  # 플랫폼 이름


class base_vod(ABC):
    """모든 VOD 처리 플랫폼에 공통으로 사용되는 기본 클래스"""

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
            performance_manager: 성능 관리자
            channel_id: 채널 ID
            platform: 플랫폼 이름
        """
        self.init = init_var
        self.performance_manager = performance_manager
        self.DiscordWebhookSender_class = DiscordWebhookSender()
        self.DO_TEST = init_var.DO_TEST
        self.userStateData = init_var.userStateData
        self.video_data = self.init.video_data
        self.platform = platform
        self.channel_id = channel_id
        self.IDList = init_var.IDList
        self.uid = self.IDList[self.platform].loc[self.channel_id, "uid"]
        self.time_offset = 25
        self.duration_diff = 10
        self.thumb_check_times = {}
        self.max_check_thumb_min = 10
        self.fun_difference1 = 20
        self.fun_difference2 = 35
        self.fun_difference3 = 45
        self.fun_difference4 = 60
        self.fun_difference5 = 75

        self.title_data = self.init.titleData[self.platform]

        self.data = VOD_Data(platform=self.platform)

    async def start(self):
        """VOD 처리 시작점"""
        await self.check_video()
        await self.post_video()

    async def check_video(self):
        """비디오 데이터 확인 메인 함수"""
        try:
            # API 데이터 가져오기
            state_data = await self._get_video_data()

            if not self._should_process_video(state_data):
                return

            if not self._check_video_data_exists(state_data):
                return

            await self._process_video_data(state_data)

        except Exception as e:
            asyncio.create_task(
                log_error(
                    f"error get video data {self.platform}.{self.channel_id}.{str(e)}"
                )
            )

    @abstractmethod
    async def _get_video_data(self):
        """플랫폼별 비디오 데이터 가져오기 (추상 메서드)"""
        pass

    @abstractmethod
    def _should_process_video(self, state_data):
        """비디오 데이터 처리 여부 확인 (추상 메서드)"""
        pass

    @abstractmethod
    def _check_video_data_exists(self, state_data):
        """비디오 데이터 존재 여부 확인 (추상 메서드)"""
        pass

    @abstractmethod
    def _extract_video_info(self, state_data):
        """플랫폼별 비디오 정보 추출 (추상 메서드)"""
        pass

    async def _process_video_data(self, state_data):
        """비디오 데이터 처리 공통 로직"""
        # 비디오 정보 가져오기
        self._extract_video_info(state_data)

        # 새 비디오인지 확인
        if not self._check_new_video():
            return

        # 비디오 데이터 JSON 생성 및 저장
        json_data = await self._get_video_json()
        self._update_video_list()
        if not self.init.DO_TEST:
            asyncio.create_task(
                save_video_data(
                    self.init.supabase, self.video_data, self.channel_id, self.platform
                )
            )

        # 알림 목록에 추가
        self.data.video_alarm_List.append(json_data)

    def _check_new_video(self):
        """새 비디오인지 확인하는 공통 로직"""
        old_publish_date = self.video_data[self.platform].loc[
            self.channel_id, "VOD_json"
        ]["publishDate"]
        video_list = self.video_data[self.platform].loc[self.channel_id, "VOD_json"][
            "videoNo_list"
        ]

        # 이미 등록된 비디오거나 이전 날짜의 비디오인 경우 건너뛰기
        if (
            changeUTCtime(self.data.publishDate) <= old_publish_date
            or self.data.videoNo in video_list
        ):
            return False

        # 썸네일 검증
        return self._validate_thumbnail()

    def _validate_thumbnail(self):
        """썸네일 검증 공통 로직"""
        # print(f"{datetime.now()} {self.channel_id}, 썸네일 검증: {self.data.thumbnailImageUrl}")

        # 썸네일이 있는 경우 - 바로 통과
        if self._has_valid_thumbnail():
            if self.data.videoNo in self.thumb_check_times:
                del self.thumb_check_times[self.data.videoNo]
            return True

        # 썸네일이 없는 경우 시간 기반 검증
        return self._handle_missing_thumbnail()

    @abstractmethod
    def _has_valid_thumbnail(self):
        """플랫폼별 유효한 썸네일 확인 (추상 메서드)"""
        pass

    def _handle_missing_thumbnail(self):
        """썸네일이 없을 때의 처리 로직"""
        current_time = datetime.now()

        if self.data.videoNo not in self.thumb_check_times:
            self.thumb_check_times[self.data.videoNo] = current_time
            print(
                f"{datetime.now()} {self.channel_id} 비디오 {self.data.videoNo} 썸네일 체크 시작"
            )
            return False

        check_start_time = self.thumb_check_times[self.data.videoNo]
        time_passed = current_time - check_start_time

        if time_passed >= timedelta(minutes=self.max_check_thumb_min):
            print(
                f"{datetime.now()} {self.channel_id} 비디오 {self.data.videoNo} 썸네일 없이 {self.max_check_thumb_min}분 경과, 알림 전송"
            )
            del self.thumb_check_times[self.data.videoNo]
            return True
        else:
            remaining_time = timedelta(minutes=self.max_check_thumb_min) - time_passed
            # print(f"{datetime.now()} {self.channel_id} 비디오 {self.data.videoNo} 썸네일 대기 중 (남은 시간: {remaining_time})")
            return False

    async def post_video(self):
        """비디오 알림 전송 공통 함수"""
        try:
            if not self.data.video_alarm_List:
                return

            json_data = self.data.video_alarm_List.pop(0)
            channel_name = self.IDList[self.platform].loc[
                self.channel_id, "channelName"
            ]
            print(f"{datetime.now()} VOD upload {channel_name} {self.data.videoTitle}")

            if self.init.is_vod_json[self.channel_id]:
                # 일반 VOD 알림 전송
                await self._send_vod_notification(json_data, channel_name)

            if self.init.is_vod_chat_json[self.channel_id]:
                # 하이라이트 채팅 대기 및 처리
                await self._wait_and_process_highlight_chat(channel_name)

        except Exception as e:
            await log_error(f"post_video 오류: {str(e)}")

    async def _send_vod_notification(self, json_data, channel_name):
        """VOD 알림 전송"""
        list_of_urls = get_list_of_urls(
            self.DO_TEST, self.userStateData, channel_name, self.channel_id, "VOD 알림"
        )

        # 푸시 알림 및 디스코드 웹훅 전송
        asyncio.create_task(send_push_notification(list_of_urls, json_data))
        asyncio.create_task(
            self.DiscordWebhookSender_class.send_messages(list_of_urls, json_data)
        )

    async def _wait_and_process_highlight_chat(self, channel_name):
        """하이라이트 채팅 대기 및 처리"""
        max_wait_time = 300  # 5분
        check_interval = 2  # 2초마다 체크
        wait_count = 0
        max_checks = max_wait_time // check_interval

        print(f"{datetime.now()} 하이라이트 처리 대기 시작: {channel_name}")
        # await change_field_state("is_save_highlight_data", self.init.is_save_highlight_data, self.channel_id)
        await self.run_highlight_processing()

        await asyncio.sleep(10)

        while wait_count < max_checks:
            # 하이라이트 처리가 완료되었는지 확인
            state_update_time = self.title_data.loc[
                self.channel_id, "state_update_time"
            ]

            if not self.init.wait_make_highlight_chat.get(
                self.channel_id, False
            ) and if_after_time(state_update_time["closeDate"], sec=30):
                print(
                    f"{datetime.now()} 하이라이트 처리 완료 감지, 채팅 처리 시작: {channel_name}"
                )
                await self._process_highlight_chat()
                return

            # 2초 대기
            await asyncio.sleep(check_interval)
            wait_count += 1

            if wait_count % 30 == 0:  # 1분마다 로그
                remaining_time = max_wait_time - (wait_count * check_interval)
                print(
                    f"{datetime.now()} 하이라이트 대기 중: {channel_name} (남은 시간: {remaining_time}초)"
                )

        # 타임아웃 시 기본 처리
        print(f"{datetime.now()} 하이라이트 대기 시간 초과, 기본 처리: {channel_name}")
        await self._process_highlight_chat()

    async def run_highlight_processing(self):
        state_manager = StateManager.get_instance()

        # StateManager에서 하이라이트가 있는 챗 인스턴스들 가져오기
        instances_with_highlights = state_manager.get_chat_instances_with_highlights()
        for instance_info in instances_with_highlights:
            channel_id = instance_info["channel_id"]
            channel_name = instance_info["channel_name"]
            platform = instance_info["platform"]
            highlights_count = instance_info["highlights_count"]
            chat_instance = instance_info["instance"]

            if self.channel_id == channel_id:
                await chat_instance.highlight_processing()

    async def _process_highlight_chat(self):
        """하이라이트 채팅 처리 - 파일에서 직접 로드"""

        # 파일에서 하이라이트 데이터 검색 및 로드
        highlight_data = await self._load_matching_highlight_file()

        if highlight_data:
            highlight_message_list = self._get_highlight_msg_from_file(highlight_data)
            if highlight_message_list:
                await self._send_comment(highlight_message_list)

    async def _load_matching_highlight_file(self):
        """VOD와 매칭되는 하이라이트 파일을 찾아서 로드"""
        try:
            # 하이라이트 파일 디렉토리 경로
            current_file = Path(__file__)
            if current_file.parent.name == "py":
                project_root = current_file.parent.parent
            else:
                project_root = current_file.parent

            channel_name = str(
                self.IDList[self.platform].loc[self.channel_id, "channelName"]
            )

            highlight_dir = project_root / "data" / "highlight_chats" / channel_name

            if not highlight_dir.exists():
                return None

            # 채널의 모든 하이라이트 파일 검색
            pattern = f"highlight_chat_{channel_name}_*.json"
            files = sorted(highlight_dir.glob(pattern), reverse=True)[:20]
            duration_diff = 0

            # VOD 제목과 지속시간으로 매칭
            for file_path in files:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = load(f)

                    # 지속시간 매칭 확인 (stream_start_id와 stream_end_id 이용)
                    stream_start_id = data.get("stream_start_id", "")
                    stream_end_id = data.get("stream_end_id", "")
                    # print(f"{datetime.now()} stream_time,{stream_start_id}, {stream_end_id}")

                    if stream_start_id and stream_end_id:
                        broadcast_duration = calculate_stream_duration(
                            stream_start_id, stream_end_id
                        )
                        duration_diff = abs(broadcast_duration - self.data.duration)

                        # 지속시간 차이가 1분 미만이면 매칭된 것으로 판단
                        if duration_diff < 60:
                            print(
                                f"{datetime.now()} duration,{broadcast_duration}, {self.data.duration}"
                            )
                            self.duration_diff = max(
                                broadcast_duration - self.data.duration, 0
                            )
                            return data

                    # 제목 매칭 확인
                    if data.get("last_title") not in self.data.videoTitle:
                        continue

                    # 치지직 방송 중인데, 방송 시간이 길어서 VOD가 분할 된 경우
                    segment_duration = 17 * 3600
                    if self.platform == "chzzk" and (
                        not stream_end_id or duration_diff >= segment_duration
                    ):
                        if (
                            data := await self._match_chzzk_vod_segment(data)
                        ) is not None:
                            return data
                        continue

                except Exception as e:
                    print(f"하이라이트 파일 처리 오류 {file_path}: {str(e)}")
                    continue

            print(f"{datetime.now()} {self.channel_id} 매칭 실패!")
            return None

        except Exception as e:
            await log_error(f"하이라이트 파일 로딩 오류: {str(e)}")
            return None

    async def uptime_command(self):
        start_time_str = self.title_data.loc[self.channel_id, "state_update_time"][
            "openDate"
        ]
        current_time = datetime.now()
        start_time = datetime.fromisoformat(start_time_str)
        uptime = current_time - start_time
        return int(uptime.total_seconds()) + 30

    async def _match_chzzk_vod_segment(self, data):
        """치지직 17시간 이상 장시간 방송 VOD 세그먼트 매칭 로직"""

        try:
            segment_duration = 17 * 3600

            if await self.uptime_command() < segment_duration:
                return None

            stream_start_id = data.get("stream_start_id", "")
            start_time = get_timestamp_from_stream_id(stream_start_id)

            timestamp = datetime.fromisoformat(str(data.get("last_updated", "")))
            live_state = self.init.titleData[self.platform].loc[self.channel_id, "live_state"]

            abs_duration_diff = abs(self.data.duration - segment_duration)
            tolerance = timedelta(minutes=30) if (
                abs_duration_diff < 30
            ) else timedelta(seconds=30)

            is_done = False

            for i in range(1, 60):  # 최대 60개 세그먼트 (1000시간)
                hours_threshold = 17 * i
                threshold_time = timestamp - timedelta(hours=hours_threshold)

                if threshold_time >= start_time:
                    is_done = True

                adjusted_time = timestamp - timedelta(hours=hours_threshold) - tolerance

                if adjusted_time < start_time:
                    data["vod_segment_start_offset"] = (i - 1) * segment_duration
                    data["vod_segment_number"] = i - 1
                    break

            if not is_done:
                await log_error(f"{self.channel_id} 매칭 실패!")
                print(data)
                return None

            print(f"{datetime.now()} {self.channel_id} 성공!")
            return data

        except Exception as e:
            print(f"치지직 VOD 세그먼트 매칭 오류: {str(e)}")
            return None

    def _get_highlight_msg_from_file(self, highlight_data):
        """파일에서 로드된 하이라이트 데이터를 VOD 댓글로 변환"""
        timeline_comments = highlight_data.get("timeline_comments", [])
        # print(f"{datetime.now()} [DEBUG] timeline_comments 수: {len(timeline_comments)}")

        if not timeline_comments or not isinstance(timeline_comments, list):
            print(
                f"{datetime.now()} [DEBUG] timeline_comments가 비어있거나 리스트가 아님"
            )
            return []

        # VOD 세그먼트 정보 가져오기
        segment_start_offset = highlight_data.get(
            "vod_segment_start_offset", 0
        )  # 초 단위
        segment_number = highlight_data.get("vod_segment_number", 0)

        timeline_comments.sort(key=lambda x: x.get("comment_after_openDate", ""))
        comment_lines = []

        auto_notice = (
            "🤖 이 댓글은 방송 하이라이트를 자동 분석하여 생성된 타임라인입니다."
        )

        comment_lines.append(auto_notice)

        processed_count = 0

        for comment in timeline_comments:
            time_str = comment.get("comment_after_openDate", "")
            text = comment.get("image_text", "") or comment.get("text", "")
            score_difference = float(comment.get("score_difference", 0))

            if not time_str or not text:
                continue

            # 하이라이트 시간을 초로 변환 (방송 시작부터의 누적 시간)
            comment_absolute_seconds = self._parse_time_to_seconds(time_str)

            # 이 VOD 세그먼트 범위 내의 댓글인지 확인
            segment_end_offset = segment_start_offset + self.data.duration

            # 세그먼트 범위를 벗어나는 댓글은 제외
            if (
                comment_absolute_seconds < segment_start_offset
                or comment_absolute_seconds >= segment_end_offset + self.duration_diff
            ):
                continue

            # VOD 내에서의 상대적 시간 계산
            comment_relative_seconds = comment_absolute_seconds - segment_start_offset

            # 상대적 시간을 문자열로 변환
            # relative_time_str = self._seconds_to_time_string(comment_relative_seconds)

            # 기존 오프셋 적용
            del_sec = int(self.time_offset + min((self.duration_diff - 10), 0))
            formatted_time = format_time_for_comment(comment_relative_seconds, del_sec)

            if not formatted_time:
                continue

            # 재미 점수 계산
            fun_score = 0
            if score_difference > self.fun_difference1:
                fun_score += 1
            if score_difference > self.fun_difference2:
                fun_score += 1
            if score_difference > self.fun_difference3:
                fun_score += 1
            if score_difference > self.fun_difference4:
                fun_score += 1
            if score_difference > self.fun_difference5:
                fun_score += 1

            if score_difference != 0:
                text = f"재미 점수:{fun_score} - {text}"

            comment_line = f"{formatted_time}- {text}"
            comment_lines.append(comment_line)
            processed_count += 1

        # print(f"{datetime.now()} 세그먼트 {segment_number} 댓글 처리 완료:")
        # print(f"  - 전체 하이라이트: {len(timeline_comments)}개")
        # print(f"  - 이 세그먼트 해당: {processed_count}개")
        # print(f"  - 세그먼트 범위: {segment_start_offset}초 ~ {segment_start_offset + self.data.duration}초")

        if processed_count == 0:
            # 해당 세그먼트에 댓글이 없는 경우
            comment_lines.append("🤖 이 구간에는 하이라이트가 없습니다.")

        chunks = self._split_comments_with_notice(comment_lines)

        return chunks

    def _parse_time_to_seconds(self, time_str):
        """시간 문자열을 초로 변환 (예: "1:23:45" -> 5025초)"""
        try:
            parts = time_str.split(":")
            if len(parts) == 3:  # HH:MM:SS
                hours, minutes, seconds = map(int, parts)
                return hours * 3600 + minutes * 60 + seconds
            elif len(parts) == 2:  # MM:SS
                minutes, seconds = map(int, parts)
                return minutes * 60 + seconds
            else:  # SS
                return int(parts[0])
        except (ValueError, IndexError):
            return 0

    def _seconds_to_time_string(self, seconds):
        """초를 시간 문자열로 변환 (예: 5025초 -> "1:23:45")"""
        try:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)

            if hours > 0:
                return f"{hours}:{minutes:02d}:{secs:02d}"
            else:
                return f"{minutes}:{secs:02d}"
        except:
            return "0:00"

    def _split_comments_with_notice(self, comment_lines, split_len=90):
        """댓글 분할"""
        chunks = []
        current_chunk = []
        for line in comment_lines:
            current_chunk.append(line)
            if len(current_chunk) >= split_len:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    @abstractmethod
    async def _get_video_json(self):
        """플랫폼별 비디오 JSON 데이터 생성 (추상 메서드)"""
        pass

    def _update_video_list(self):
        """비디오 번호 목록 업데이트"""
        chzzk_video_json = self.video_data[self.platform].loc[
            self.channel_id, "VOD_json"
        ]

        if len(chzzk_video_json["videoNo_list"]) >= 10:
            chzzk_video_json["videoNo_list"][:-1] = chzzk_video_json["videoNo_list"][1:]
            chzzk_video_json["videoNo_list"][-1] = self.data.videoNo
        else:
            chzzk_video_json["videoNo_list"].append(self.data.videoNo)

        chzzk_video_json["publishDate"] = changeUTCtime(self.data.publishDate)

    @abstractmethod
    async def _send_comment(self, message_list):
        """플랫폼별 댓글 전송 (추상 메서드)"""
        pass


class chzzk_vod(base_vod):
    """치지직 VOD 처리 클래스"""

    def __init__(
        self, init_var: initVar, performance_manager: PerformanceManager, channel_id
    ):
        super().__init__(init_var, performance_manager, channel_id, "chzzk")

    async def _get_video_data(self):
        """치지직 비디오 API 데이터 가져오기"""

        def get_link():
            return f"https://api.chzzk.naver.com/service/v1/channels/{self.uid}/videos"

        return await get_message(self.performance_manager, "chzzk", get_link())

    def _should_process_video(self, state_data):
        """치지직 비디오 데이터 처리 여부 확인"""
        return state_data and state_data["code"] == 200

    def _check_video_data_exists(self, state_data):
        """치지직 비디오 데이터 존재 여부 확인"""
        return bool(state_data.get("content", {}).get("data", []))

    def _extract_video_info(self, state_data, videoNo = None):
        """치지직 비디오 정보 추출"""

        def get_started_at(date_str) -> str | None:
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str).isoformat()
            except ValueError:
                return None
            
        if videoNo is not None:
            data = next(
                (item for item in state_data["content"]["data"] if item["videoNo"] == videoNo),
                None
            )
            if data is None:
                data = state_data["content"]["data"][0]
        else:
            data = state_data["content"]["data"][0]

        self.data.duration = data["duration"]
        self.data.videoNo = data["videoNo"]
        self.data.videoTitle = data["videoTitle"]
        self.data.publishDate = get_started_at(data.get("publishDate"))
        self.data.thumbnailImageUrl = data["thumbnailImageUrl"]
        self.data.videoCategoryValue = data["videoCategoryValue"]

    def _has_valid_thumbnail(self):
        """치지직 유효한 썸네일 확인"""
        return self.data.thumbnailImageUrl and "https://" in self.data.thumbnailImageUrl

    async def _get_video_json(self):
        """치지직 비디오 웹훅 JSON 데이터 생성"""
        videoTitle = (
            "|"
            + (
                self.data.videoTitle
                if self.data.videoTitle != " "
                else "                                                  "
            )
            + "|"
        )

        channel_data = self.IDList[self.platform].loc[self.channel_id]
        username = channel_data["channelName"]
        avatar_url = channel_data["profile_image"]
        video_url = f"https://chzzk.naver.com/{self.uid}/video"

        embed = {
            "color": 65443,
            "author": {"name": username, "url": video_url, "icon_url": avatar_url},
            "title": videoTitle,
            "url": f"https://chzzk.naver.com/video/{self.data.videoNo}",
            "description": f"{username} 치지직 영상 업로드!",
            "fields": [{"name": "Category", "value": self.data.videoCategoryValue}],
            "thumbnail": {"url": avatar_url},
            "image": {"url": self.data.thumbnailImageUrl},
            "footer": {
                "text": "Chzzk",
                "inline": True,
                "icon_url": iconLinkData.chzzk_icon,
            },
            "timestamp": changeUTCtime(self.data.publishDate),
        }

        # 최종 웹훅 JSON 데이터 반환
        return {
            "username": f"[치지직 알림] {username}",
            "avatar_url": avatar_url,
            "embeds": [embed],
        }

    async def _send_comment(self, message_list):
        try:
            last_time = self.init.platform_vod_last_chat_send_time.get(self.platform)

            if last_time and not if_after_time(last_time, sec=20):
                await asyncio.sleep(20)

            max_retry = 3
            comment_id = None

            for attempt in range(1, max_retry + 1):
                comment_id = await self._first_send_comment(message_list[0])

                if comment_id:
                    self.init.platform_vod_last_chat_send_time[self.platform] = datetime.now().isoformat()
                    break

                if attempt < max_retry:
                    await asyncio.sleep(2)

            if comment_id:
                await self._send_reply_comments(comment_id, message_list[1:])

            return comment_id

        except Exception as e:
            await log_error(f"치지직 댓글 전송 오류: {str(e)}")
            return None

    async def _first_send_comment(self, message):
        """치지직 댓글 전송"""
        try:

            def get_link():
                return f"https://apis.naver.com/nng_main/nng_comment_api/v1/type/STREAMING_VIDEO/id/{self.data.videoNo}/comments"

            def get_VOD_chat_json():
                return {
                    "attach": False,
                    "commentAttaches": [],
                    "commentType": "COMMENT",
                    "content": message,
                    "deviceType": "PC",
                    "mentionedUserIdHash": "",
                    "parentCommentId": 0,
                    "secret": False,
                }

            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    get_link(),
                    json=get_VOD_chat_json(),
                    headers=getDefaultHeaders(),
                    cookies=getChzzkCookie(),
                ) as response:

                    # print(f"{datetime.now()} 첫 번째 댓글 응답 상태: {response.status}")
                    response_text = await response.text()

                    if response.status == 200:
                        try:
                            response_data = loads(response_text)
                            if (
                                response_data.get("code") == 200
                                and "content" in response_data
                            ):
                                comment_id = (
                                    response_data["content"]
                                    .get("comment", {})
                                    .get("commentId")
                                )
                                # print(f"{datetime.now()} 첫 번째 댓글 작성 성공! ID: {comment_id}")
                                return comment_id
                            else:
                                print(
                                    f"{datetime.now()} 첫 번째 댓글 실패: {response_data}"
                                )
                                return None
                        except Exception as parse_error:
                            print(f"{datetime.now()} 응답 파싱 오류: {parse_error}")
                            return None
                    else:
                        await log_error(
                            f"{datetime.now()} {self.data.videoNo} {self.data.videoNo}, 첫 번째 댓글 HTTP 오류: {response_text}"
                        )
                        return None

        except Exception as e:
            await log_error(f"치지직 첫 번째 댓글 전송 오류: {str(e)}")

    async def _send_reply_comments(self, parent_comment_id: int, reply_messages: list):
        """
        치지직 대댓글 전송

        Args:
            parent_comment_id: 부모 댓글 ID
            reply_messages: 답글 메시지 리스트
        """
        try:
            # 쿠키와 헤더 준비
            headers = getDefaultHeaders()
            cookies = getChzzkCookie()

            def get_link():
                return f"https://apis.naver.com/nng_main/nng_comment_api/v1/type/STREAMING_VIDEO/id/{self.data.videoNo}/comments"

            def get_reply_json(message):
                return {
                    "attach": False,
                    "commentAttaches": [],
                    "commentType": "REPLY",
                    "content": message,
                    "deviceType": "PC",
                    "mentionedUserIdHash": "",
                    "parentCommentId": parent_comment_id,
                    "secret": False,
                }

            async with aiohttp.ClientSession() as session:
                for i, message in enumerate(reply_messages):
                    try:
                        # 답글 간 간격 (너무 빠르게 보내지 않도록)
                        await asyncio.sleep(6)
                        async with session.post(
                            get_link(),
                            json=get_reply_json(message),
                            headers=headers,
                            cookies=cookies,
                        ) as response:

                            # print(f"{datetime.now()} 답글 {i+1} 응답 상태: {response.status}")
                            response_text = await response.text()
                            if response.status == 200:
                                try:
                                    response_data = loads(response_text)
                                    if response_data.get("code") == 200:
                                        # print(f"{datetime.now()} 답글 {i+1} 작성 성공!")
                                        pass
                                    else:
                                        print(
                                            f"{datetime.now()} 답글 {i+1} 실패: {response_data}"
                                        )
                                except Exception as parse_error:
                                    print(
                                        f"{datetime.now()} 답글 {i+1} 파싱 오류: {parse_error}"
                                    )
                            else:
                                print(
                                    f"{datetime.now()} 답글 {i+1} HTTP 오류: {response_data}"
                                )

                    except Exception as reply_error:
                        print(f"{datetime.now()} 답글 {i+1} 전송 오류: {reply_error}")
                        continue

        except Exception as e:
            await log_error(f"chzzk _send_reply_comments 오류: {str(e)}")


class afreeca_vod(base_vod):
    """아프리카TV VOD 처리 클래스"""

    def __init__(
        self, init_var: initVar, performance_manager: PerformanceManager, channel_id
    ):
        super().__init__(init_var, performance_manager, channel_id, "afreeca")
        self.base_url = "https://stbbs.sooplive.co.kr/api/bbs_memo_action.php"

    async def _get_video_data(self):
        """아프리카TV 비디오 API 데이터 가져오기"""
        link = f"https://chapi.sooplive.co.kr/api/{self.uid}/vods/review?keyword=&orderby=reg_date&perPage=20&field=title,contents,user_nick,user_id&page={1}&start_date=&end_date="
        return await get_message(self.performance_manager, "afreeca", link)

    def _should_process_video(self, state_data):
        """아프리카TV 비디오 데이터 처리 여부 확인"""
        return state_data and "data" in state_data

    def _check_video_data_exists(self, state_data):
        """아프리카TV 비디오 데이터 존재 여부 확인"""
        return bool(state_data.get("data", []))

    def _extract_video_info(self, state_data):
        """아프리카TV 비디오 정보 추출"""

        def get_started_at(date_str) -> str | None:
            if not date_str:
                return None
            try:
                # 아프리카TV는 "2025-09-05 23:48:37" 형식
                return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").isoformat()
            except ValueError:
                return None

        data = state_data["data"][0]
        self.data.duration = (
            data["ucc"]["total_file_duration"] // 1000
        )  # 밀리초를 초로 변환
        self.data.videoNo = data["title_no"]
        self.data.videoTitle = data["title_name"]
        self.data.publishDate = get_started_at(data.get("reg_date"))
        self.data.videoCategoryValue = ",".join(data["ucc"].get("category_tags", []))

        # 썸네일 URL 생성 (https: 접두사 추가)
        default_thumb = "https://res.sooplive.co.kr/images/thumb/vod/0082_480x270_dark.png"
        thumb_url = data["ucc"].get("thumb", default_thumb)
        if thumb_url is None :
            thumb_url = default_thumb
        self.data.thumbnailImageUrl = (
            f"https:{thumb_url}" if thumb_url.startswith("//") else thumb_url
        )

    def _has_valid_thumbnail(self):
        """아프리카TV 유효한 썸네일 확인"""
        return self.data.thumbnailImageUrl and self.data.thumbnailImageUrl.startswith(
            "https://"
        )

    async def _get_video_json(self):
        """아프리카TV 비디오 웹훅 JSON 데이터 생성"""
        videoTitle = (
            "|"
            + (
                self.data.videoTitle
                if self.data.videoTitle != " "
                else "                                                  "
            )
            + "|"
        )

        channel_data = self.IDList[self.platform].loc[self.channel_id]
        username = channel_data["channelName"]
        avatar_url = channel_data["profile_image"]
        video_url = f"https://www.sooplive.co.kr/station/{self.uid}"

        embed = {
            "color": 629759,
            "author": {"name": username, "url": video_url, "icon_url": avatar_url},
            "title": videoTitle,
            "url": f"https://vod.sooplive.co.kr/player/{self.data.videoNo}",
            "description": f"{username} 아프리카TV 영상 업로드!",
            "fields": [{"name": "Category", "value": self.data.videoCategoryValue}],
            "thumbnail": {"url": avatar_url},
            "image": {"url": self.data.thumbnailImageUrl},
            "footer": {
                "text": "AfreecaTV",
                "inline": True,
                "icon_url": iconLinkData.soop_icon,
            },
            "timestamp": changeUTCtime(self.data.publishDate),
        }

        return {
            "username": f"[아프리카TV 알림] {username}",
            "avatar_url": avatar_url,
            "embeds": [embed],
        }

    async def get_recent_comments(self, page: int = 1):
        try:
            headers = getDefaultHeaders()
            cookies = getAfreecaCookie()

            vod_info = {"title_no": str(self.data.videoNo), "bj_id": self.uid}

            post_data = {
                "nTitleNo": vod_info["title_no"],
                "bj_id": vod_info["bj_id"],
                "nPageNo": str(page),
                "nOrderNo": "1",
                "nBoardType": "105",
                "szAction": "get",
                "nVod": "1",
                "nLastNo": "0",
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.base_url,
                    data=post_data,
                    headers=headers,
                    cookies=cookies,
                    timeout=15,
                ) as response:

                    if response.status == 200:
                        response_text = await response.text()
                        response_text = response_text.strip()
                        data = loads(response_text)

                        # print(f"[DEBUG] 댓글 조회 응답: {str(data)[:500]}")

                        # API 응답 구조에 따라 댓글 리스트 추출
                        if "CHANNEL" in data and "DATA" in data["CHANNEL"]:
                            channel_data = data["CHANNEL"]["DATA"]
                            if isinstance(channel_data, dict):
                                memo_list = channel_data.get("list_data", [])
                                if isinstance(memo_list, list):
                                    # print(f"[DEBUG] 댓글 {len(memo_list)}개 조회됨")
                                    return memo_list

                        # print("[DEBUG] 댓글 목록을 찾을 수 없음")
                        return []

                    print(f"[DEBUG] HTTP 오류: {response.status}")
                    return None

        except Exception as e:
            print(f"댓글 조회 오류: {str(e)}")
            return None

    async def find_comment_by_content(self, max_wait: int = 10):
        # 댓글이 반영될 때까지 잠시 대기
        my_afreeca_id = environ.get("MY_afreeca_ID")
        if not my_afreeca_id:
            print("[ERROR] 환경변수 MY_afreeca_ID가 설정되지 않았습니다")
            return None

        for attempt in range(max_wait):
            # 이벤트 루프 양보
            await asyncio.sleep(0.001)
            comments = await self.get_recent_comments()

            if comments:
                for comment in comments:
                    # 댓글 찾기
                    comment_user = comment.get("user_id", "")
                    comment_text = comment.get("comment", "")
                    if comment_user == my_afreeca_id and "🤖" in comment_text:
                        # 댓글 ID 추출
                        comment_id = comment.get("p_comment_no")
                        if comment_id:
                            # print(f"  ✓ 댓글 ID 찾음: {comment_id}")
                            return int(comment_id)

            if attempt < max_wait - 1:
                # print(f"  댓글 검색 중... ({attempt + 1}/{max_wait})")
                await asyncio.sleep(1)

        print(f"  ✗ 댓글 ID를 찾지 못했습니다 (최대 {max_wait}회 시도)")
        return None

    async def _send_comment(self, message_list):
        """아프리카TV 댓글 전송"""
        try:
            is_success = await self._first_send_comment(message_list[0])
            if is_success:
                comment_id = await self.find_comment_by_content()
                if comment_id:
                    await self._send_reply_comments(comment_id, message_list[1:])
                return comment_id
            return None

        except Exception as e:
            await log_error(f"아프리카TV 댓글 전송 오류: {str(e)}")
            return None

    async def _first_send_comment(self, message):

        try:
            # 쿠키와 헤더 준비
            headers = getDefaultHeaders()
            cookies = getAfreecaCookie()

            post_data = {
                "nTitleNo": str(self.data.videoNo),
                "bj_id": self.uid,
                "nBoardType": "105",
                "szContent": message,
                "szAction": "write",
                "nParentCommentNo": "0",
                "nCommentPhotoType": "1",
                "szCommentPhoto": "",
                "szFileType": "REVIEW",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.base_url,
                    data=post_data,
                    headers=headers,
                    cookies=cookies,
                    timeout=15,
                ) as response:
                    # print(f"{datetime.now()} 첫 번째 댓글 응답 상태: {response.status}")

                    if response.status == 200:
                        response_text = await response.text()
                        response_text = response_text.strip()

                        try:
                            # JSON 응답 파싱 시도
                            json_resp = loads(response_text)
                            if "CHANNEL" in json_resp:
                                result = json_resp["CHANNEL"].get("RESULT", 0)
                                msg = json_resp["CHANNEL"].get("MSG", "")

                                if result == 1:
                                    # print(f"{datetime.now()} 아프리카TV 댓글 작성 성공!")
                                    return True
                                elif result == -10:
                                    print(
                                        f"{datetime.now()} 아프리카TV 댓글 실패: 로그인이 필요합니다"
                                    )
                                    return False
                                else:
                                    print(
                                        f"{datetime.now()} 아프리카TV 댓글 실패: {msg} (코드: {result})"
                                    )
                                    return False

                        except Exception:
                            # JSON이 아닌 응답의 경우 - 단순 성공 응답 체크
                            if response_text in ["1", "success", "ok"]:
                                print(f"{datetime.now()} 아프리카TV 댓글 작성 성공!")
                                return True
                            else:
                                print(
                                    f"{datetime.now()} 아프리카TV 댓글 알 수 없는 응답: {response_text}"
                                )
                                return False
                    else:
                        print(
                            f"{datetime.now()} 아프리카TV 댓글 HTTP 오류: {response.status}"
                        )
                        return False

        except Exception as e:
            await log_error(f"아프리카TV 댓글 전송 오류: {str(e)}")
            return False

    async def _send_reply_comments(self, parent_comment_id: int, reply_messages: str):
        # 쿠키와 헤더 준비
        headers = getDefaultHeaders()
        cookies = getAfreecaCookie()

        def get_reply_json(message):
            return {
                "nTitleNo": str(self.data.videoNo),
                "bj_id": self.uid,
                "nBoardType": "105",
                "szContent": message,
                "szAction": "write",
                "nParentCommentNo": str(parent_comment_id),
                "nCommentPhotoType": "1",
                "szCommentPhoto": "",
                "szFileType": "REVIEW",
            }

        try:
            async with aiohttp.ClientSession() as session:
                for i, message in enumerate(reply_messages):
                    await asyncio.sleep(6)
                    try:
                        async with session.post(
                            self.base_url,
                            data=get_reply_json(message),
                            headers=headers,
                            cookies=cookies,
                            timeout=15,
                        ) as response:
                            # print(f"{datetime.now()} 답글 {i+1} 응답 상태: {response.status}")

                            if response.status == 200:
                                response_text = await response.text()
                                response_text = response_text.strip()
                                try:
                                    # JSON 응답 파싱 시도
                                    response_data = loads(response_text)
                                    if "CHANNEL" in response_data:
                                        if (
                                            response_data["CHANNEL"].get("RESULT", 0)
                                            == 1
                                        ):
                                            # print(f"{datetime.now()} 답글 {i+1} 작성 성공!")
                                            pass
                                        else:
                                            print(
                                                f"{datetime.now()} 답글 {i+1} 실패: {response_data}"
                                            )
                                except Exception as parse_error:
                                    print(
                                        f"{datetime.now()} 답글 {i+1} 파싱 오류: {parse_error}"
                                    )
                            else:
                                print(
                                    f"{datetime.now()} 답글 {i+1} HTTP 오류: {response.status}"
                                )
                    except Exception as reply_error:
                        print(f"{datetime.now()} 답글 {i+1} 전송 오류: {reply_error}")
                        continue

        except Exception as e:
            await log_error(f"afreeca _send_reply_comments 오류: {str(e)}")
