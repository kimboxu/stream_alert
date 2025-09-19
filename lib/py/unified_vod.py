import asyncio
from pathlib import Path
from json import loads, load
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from notification_service import send_push_notification
from live_message import highlight_chat_Data
from make_log_api_performance import PerformanceManager
from base import (
    changeUTCtime, 
    get_message, 
    iconLinkData, 
    initVar, 
    save_video_data, 
    log_error,
    getChzzkCookie,
    getDefaultHeaders,
    calculate_stream_duration,
    format_time_for_comment,
)

@dataclass
class VOD_Data:
    """플랫폼 공통 VOD 데이터를 저장하는 클래스"""
    videoNo: int = 0                           # 비디오 번호/ID
    videoTitle: str = ""                       # 비디오 제목
    publishDate: datetime = datetime.now()     # 게시 날짜
    thumbnailImageUrl: str = ""                # 썸네일 이미지 URL
    videoCategoryValue: str = ""               # 비디오 카테고리
    video_alarm_List: list = field(default_factory=list)
    duration: int = 0                          # 비디오 길이(초)
    platform_name: str = ""                   # 플랫폼 이름

class base_vod(ABC):
    """모든 VOD 처리 플랫폼에 공통으로 사용되는 기본 클래스"""
    
    def __init__(self, init_var: initVar, performance_manager: PerformanceManager, channel_id):
        """
        초기화 함수
        
        Args:
            init_var: 초기화 변수들이 포함된 객체
            performance_manager: 성능 관리자
            channel_id: 채널 ID
            platform_name: 플랫폼 이름
        """
        self.init = init_var
        self.performance_manager = performance_manager
        self.DiscordWebhookSender_class = DiscordWebhookSender()
        self.DO_TEST = init_var.DO_TEST
        self.userStateData = init_var.userStateData
        self.video_data = self.init.video_data
        self.platform_name = self.video_data.loc[channel_id, 'platform_name']
        self.channel_id = channel_id
        self.time_offset = 20
        self.duration_diff = 0
        self.thumb_check_times = {}
        self.max_check_thumb_min = 3
        self.fun_difference1 = 15
        self.fun_difference2 = 30
        self.fun_difference3 = 40
        self.fun_difference4 = 60
        self.fun_difference5 = 70
        
        # 플랫폼별 데이터 초기화
        self._initialize_platform_data()
        
        self.data = VOD_Data(platform_name=self.platform_name)

    @abstractmethod
    def _initialize_platform_data(self):
        """플랫폼별 데이터 초기화 (추상 메서드)"""
        pass

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
            asyncio.create_task(log_error(f"error get video data {self.platform_name}.{self.channel_id}.{e}"))

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
        asyncio.create_task(save_video_data(self.video_data, self.platform_name, self.channel_id))

        # 알림 목록에 추가
        self.data.video_alarm_List.append(json_data)

    def _check_new_video(self):
        """새 비디오인지 확인하는 공통 로직"""
        old_publish_date = self.video_data.loc[self.channel_id, 'VOD_json']["publishDate"]
        video_list = self.video_data.loc[self.channel_id, 'VOD_json']["videoNo_list"]

        # 이미 등록된 비디오거나 이전 날짜의 비디오인 경우 건너뛰기
        if (changeUTCtime(self.data.publishDate) <= old_publish_date or 
            self.data.videoNo in video_list):
            return False

        # 썸네일 검증
        return self._validate_thumbnail()

    def _validate_thumbnail(self):
        """썸네일 검증 공통 로직"""
        print(f"{datetime.now()} {self.channel_id}, 썸네일 검증: {self.data.thumbnailImageUrl}")
        
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
            print(f"{datetime.now()} {self.channel_id} 비디오 {self.data.videoNo} 썸네일 체크 시작")
            return False
        
        check_start_time = self.thumb_check_times[self.data.videoNo]
        time_passed = current_time - check_start_time
        
        if time_passed >= timedelta(minutes=self.max_check_thumb_min):
            print(f"{datetime.now()} {self.channel_id} 비디오 {self.data.videoNo} 썸네일 없이 {self.max_check_thumb_min}분 경과, 알림 전송")
            del self.thumb_check_times[self.data.videoNo]
            return True
        else:
            remaining_time = timedelta(minutes=self.max_check_thumb_min) - time_passed
            print(f"{datetime.now()} {self.channel_id} 비디오 {self.data.videoNo} 썸네일 대기 중 (남은 시간: {remaining_time})")
            return False

    async def post_video(self):
        """비디오 알림 전송 공통 함수"""
        try:
            if not self.data.video_alarm_List:
                return
            
            json_data = self.data.video_alarm_List.pop(0)
            channel_name = self.id_list.loc[self.channel_id, 'channelName']
            print(f"{datetime.now()} VOD upload {channel_name} {self.data.videoTitle}")

            if self.init.is_vod_json[self.channel_id]:
                # 알림을 보낼 웹훅 URL들 가져오기
                list_of_urls = get_list_of_urls(
                    self.DO_TEST, 
                    self.userStateData, 
                    channel_name, 
                    self.channel_id, 
                    "VOD 알림"
                )

                # 푸시 알림 및 디스코드 웹훅 전송
                asyncio.create_task(send_push_notification(list_of_urls, json_data))
                asyncio.create_task(self.DiscordWebhookSender_class.send_messages(list_of_urls, json_data))

            if self.init.is_vod_chat_json[self.channel_id]:
                # 하이라이트 채팅 처리
                asyncio.create_task(self._process_highlight_chat())

        except Exception as e:
            asyncio.create_task(log_error(f"post video message error: {e}"))

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
            if current_file.parent.name == 'py':
                project_root = current_file.parent.parent
            else:
                project_root = current_file.parent
            
            highlight_dir = project_root / "data" / "highlight_chats"
            
            if not highlight_dir.exists():
                return None
            
            # 채널의 모든 하이라이트 파일 검색
            channel_name = self.id_list.loc[self.channel_id, 'channelName']
            pattern = f"highlight_chat_{channel_name}_*.json"
            files = reversed(list(highlight_dir.glob(pattern)))
            
            # VOD 제목과 지속시간으로 매칭
            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = load(f)
                    
                    # 제목 매칭 확인
                    if data.get('last_title') != self.data.videoTitle:
                        continue
                    
                    # 지속시간 매칭 확인 (stream_start_id와 stream_end_id 이용)
                    stream_start_id = data.get('stream_start_id', '')
                    stream_end_id = data.get('stream_end_id', '')
                    saved_at = data.get('saved_at', '')
                    
                    if stream_start_id and stream_end_id:
                        broadcast_duration = calculate_stream_duration(stream_start_id, stream_end_id)
                        duration_diff = abs(broadcast_duration - self.data.duration)
                        
                        # 지속시간 차이가 1분 미만이면 매칭된 것으로 판단
                        if duration_diff < 60:
                            self.duration_diff = max(broadcast_duration - self.data.duration, 0)
                            return data
                        
                    # if self.platform_name == 'chzzk' and saved_at:
                    #     timestamp = datetime.fromisoformat(str(saved_at).replace('Z', '+00:00'))
                            
                except Exception as e:
                    print(f"하이라이트 파일 처리 오류 {file_path}: {e}")
                    continue
            
            return None
            
        except Exception as e:
            await log_error(f"하이라이트 파일 로딩 오류: {e}")
            return None

    def _get_highlight_msg_from_file(self, highlight_data):
        """파일에서 로드된 하이라이트 데이터를 VOD 댓글로 변환"""
        timeline_comments = highlight_data.get('timeline_comments', [])
        
        if not timeline_comments or not isinstance(timeline_comments, list):
            return []
        
        timeline_comments.sort(key=lambda x: x.get('comment_after_openDate', ''))
        comment_lines = []
        
        auto_notice = "🤖 이 댓글은 방송 하이라이트를 자동 분석하여 생성된 타임라인입니다."
        comment_lines.append(auto_notice)

        for comment in timeline_comments:
            time_str = comment.get('comment_after_openDate', '')
            description = comment.get('description', '') or comment.get('text', '')
            score_difference = float(comment.get('score_difference', 0))
            
            if not time_str or not description:
                continue
                
            del_sec = int(self.time_offset + (self.duration_diff - 10))
            formatted_time = format_time_for_comment(time_str, del_sec)
            
            if not formatted_time:
                continue
            
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

            comment_line = f"{formatted_time}- 재미 점수:{fun_score} - {description}"
            comment_lines.append(comment_line)

            chunks = self._split_comments_with_notice(comment_lines)
        
        return chunks

    def _split_comments_with_notice(self, comment_lines, split_len = 100):
        """댓글 분할"""
        chunks = []
        current_chunk = []
        for line in comment_lines:
            current_chunk.append(line)
            if len(current_chunk) >= split_len:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
        else:
            chunks.append("\n\n".join(current_chunk))
            
        return chunks

    @abstractmethod
    async def _get_video_json(self):
        """플랫폼별 비디오 JSON 데이터 생성 (추상 메서드)"""
        pass

    def _update_video_list(self):
        """ 비디오 번호 목록 업데이트"""
        chzzk_video_json = self.video_data.loc[self.channel_id, 'VOD_json']
        
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
    def __init__(self, init_var: initVar, performance_manager: PerformanceManager, channel_id):
        super().__init__(init_var, performance_manager, channel_id)
    
    def _initialize_platform_data(self):
        """치지직 플랫폼 데이터 초기화"""
        self.id_list = self.init.chzzkIDList
        
    async def _get_video_data(self):
        """치지직 비디오 API 데이터 가져오기"""
        def get_link(uid):
            return f"https://api.chzzk.naver.com/service/v1/channels/{uid}/videos"
        
        uid = self.id_list.loc[self.channel_id, 'channel_code']
        return await get_message(self.performance_manager, "chzzk", get_link(uid))

    def _should_process_video(self, state_data):
        """치지직 비디오 데이터 처리 여부 확인"""
        return state_data and state_data["code"] == 200
    
    def _check_video_data_exists(self, state_data):
        """치지직 비디오 데이터 존재 여부 확인"""
        return bool(state_data.get("content", {}).get("data", []))

    def _extract_video_info(self, state_data):
        """치지직 비디오 정보 추출"""
        def get_started_at(date_str) -> str | None:
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str).isoformat()
            except ValueError:
                return None

        data = state_data["content"]["data"][0]
        
        self.data.duration = data["duration"]
        self.data.videoNo = data["videoNo"]
        self.data.videoTitle = data["videoTitle"]
        self.data.publishDate = get_started_at(data.get("publishDate"))
        self.data.thumbnailImageUrl = data["thumbnailImageUrl"]
        self.data.videoCategoryValue = data["videoCategoryValue"]

    def _has_valid_thumbnail(self):
        """치지직 유효한 썸네일 확인"""
        return (self.data.thumbnailImageUrl and 
                ("https://video-phinf.pstatic.net" in self.data.thumbnailImageUrl or 
                 "https://livecloud-thumb.akamaized.net" in self.data.thumbnailImageUrl))

    async def _get_video_json(self):
        """치지직 비디오 웹훅 JSON 데이터 생성"""
        videoTitle = "|" + (self.data.videoTitle if self.data.videoTitle != " " else "                                                  ") + "|"
        
        channel_data = self.id_list.loc[self.channel_id]
        username = channel_data['channelName']
        avatar_url = channel_data['profile_image']
        video_url = f"https://chzzk.naver.com/{channel_data['channel_code']}/video"
        
        embed = {
            "color": 65443,
            "author": {
                "name": username,
                "url": video_url,
                "icon_url": avatar_url
            },
            "title": videoTitle,
            "url": f"https://chzzk.naver.com/video/{self.data.videoNo}",
            "description": f"{username} 치지직 영상 업로드!",
            "fields": [
                {"name": 'Category', "value": self.data.videoCategoryValue}
            ],
            "thumbnail": {"url": avatar_url},
            "image": {"url": self.data.thumbnailImageUrl},
            "footer": {
                "text": "Chzzk",
                "inline": True,
                "icon_url": iconLinkData.chzzk_icon
            },
            "timestamp": changeUTCtime(self.data.publishDate)
        }
        
        # 최종 웹훅 JSON 데이터 반환
        return {
            "username": f"[치지직 알림] {username}",
            "avatar_url": avatar_url,
            "embeds": [embed]
        }

    async def _send_comment(self, message_list):
        """치지직 댓글 전송"""
        try:
            comment_id = await self._first_send_comment(message_list[0])
            if comment_id:
                await self._send_reply_comments(comment_id, message_list[1:])
                        
        except Exception as e:
            await log_error(f"치지직 댓글 전송 오류: {e}")

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
                    "secret": False
                }
            
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    get_link(), 
                    json=get_VOD_chat_json(), 
                    headers=getDefaultHeaders(), 
                    cookies=getChzzkCookie()
                ) as response:
                    
                    print(f"{datetime.now()} 첫 번째 댓글 응답 상태: {response.status}")
                    response_text = await response.text()
                    
                    if response.status == 200:
                        try:
                            response_data = loads(response_text)
                            if response_data.get('code') == 200 and 'content' in response_data:
                                comment_id = response_data['content'].get('comment',{}).get('commentId')
                                print(f"{datetime.now()} 첫 번째 댓글 작성 성공! ID: {comment_id}")
                                return comment_id
                            else:
                                print(f"{datetime.now()} 첫 번째 댓글 실패: {response_data}")
                                return None
                        except Exception as parse_error:
                            print(f"{datetime.now()} 응답 파싱 오류: {parse_error}")
                            return None
                    else:
                        print(f"{datetime.now()} 첫 번째 댓글 HTTP 오류: {response.status}")
                        return None
                        
        except Exception as e:
            await log_error(f"치지직 댓글 전송 오류: {e}")

    async def _send_reply_comments(self, parent_comment_id: int, reply_messages: list):
        """
        치지직 대댓글 전송
        
        Args:
            parent_comment_id: 부모 댓글 ID
            reply_messages: 답글 메시지 리스트
        """
        try:
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
                    "secret": False
                }
            
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                for i, message in enumerate(reply_messages):
                    try:
                        async with session.post(
                            get_link(),
                            json=get_reply_json(message),
                            headers=getDefaultHeaders(),
                            cookies=getChzzkCookie()
                        ) as response:
                            
                            print(f"{datetime.now()} 답글 {i+1} 응답 상태: {response.status}")
                            response_text = await response.text()
                            await asyncio.sleep(5.1)
                            if response.status == 200:
                                try:
                                    response_data = loads(response_text)
                                    if response_data.get('code') == 200:
                                        print(f"{datetime.now()} 답글 {i+1} 작성 성공!")
                                    else:
                                        print(f"{datetime.now()} 답글 {i+1} 실패: {response_data}")
                                except Exception as parse_error:
                                    print(f"{datetime.now()} 답글 {i+1} 파싱 오류: {parse_error}")
                            else:
                                print(f"{datetime.now()} 답글 {i+1} HTTP 오류: {response.status}")
                        
                        # 답글 간 간격 (너무 빠르게 보내지 않도록)
                        await asyncio.sleep(5)
                        
                    except Exception as reply_error:
                        print(f"{datetime.now()} 답글 {i+1} 전송 오류: {reply_error}")
                        continue
                        
        except Exception as e:
            await log_error(f"_send_reply_comments 오류: {e}")

class afreeca_vod(base_vod):
    """아프리카TV VOD 처리 클래스"""
    def __init__(self, init_var: initVar, performance_manager: PerformanceManager, channel_id):
        super().__init__(init_var, performance_manager, channel_id)
    
    def _initialize_platform_data(self):
        """아프리카TV 플랫폼 데이터 초기화"""
        self.id_list = self.init.afreecaIDList

    async def _get_video_data(self):
        """아프리카TV 비디오 API 데이터 가져오기"""
        afreeca_id = self.id_list.loc[self.channel_id, "afreecaID"]
        link = f"https://chapi.sooplive.co.kr/api/{afreeca_id}/vods"
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
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S').isoformat()
            except ValueError:
                return None
            
        current_time = [None, 0]
        for i, data in enumerate(state_data["data"]):
            publishDate = get_started_at(data.get("reg_date"))
            if current_time[0] is None:
                current_time = publishDate, i
            
            else:
                if current_time[0] < publishDate:
                    current_time = publishDate, i

        data = state_data["data"][current_time[1]]
        self.data.duration = data["ucc"]["total_file_duration"] // 1000  # 밀리초를 초로 변환
        self.data.videoNo = data["title_no"]
        self.data.videoTitle = data["title_name"]
        self.data.publishDate = get_started_at(data.get("reg_date"))
        self.data.videoCategoryValue = ','.join(data["ucc"].get("category_tags", []))
        
        # 썸네일 URL 생성 (https: 접두사 추가)
        thumb_url = data["ucc"].get("thumb", "")
        self.data.thumbnailImageUrl = f"https:{thumb_url}" if thumb_url.startswith("//") else thumb_url
        

    def _has_valid_thumbnail(self):
        """아프리카TV 유효한 썸네일 확인"""
        return (self.data.thumbnailImageUrl and 
                self.data.thumbnailImageUrl.startswith("https://"))

    async def _get_video_json(self):
        """아프리카TV 비디오 웹훅 JSON 데이터 생성"""
        videoTitle = "|" + (self.data.videoTitle if self.data.videoTitle != " " else "                                                  ") + "|"
        
        channel_data = self.id_list.loc[self.channel_id]
        username = channel_data['channelName']
        avatar_url = channel_data['profile_image']
        afreeca_id = channel_data['afreecaID']
        video_url = f"https://www.sooplive.co.kr/station/{afreeca_id}"
        
        embed = {
            "color": 629759,
            "author": {
                "name": username,
                "url": video_url,
                "icon_url": avatar_url
            },
            "title": videoTitle,
            "url": f"https://vod.sooplive.co.kr/player/{self.data.videoNo}",
            "description": f"{username} 아프리카TV 영상 업로드!",
            "fields": [
                {"name": 'Category', "value": self.data.videoCategoryValue}
            ],
            "thumbnail": {"url": avatar_url},
            "image": {"url": self.data.thumbnailImageUrl},
            "footer": {
                "text": "AfreecaTV",
                "inline": True,
                "icon_url": iconLinkData.soop_icon
            },
            "timestamp": changeUTCtime(self.data.publishDate)
        }
        
        return {
            "username": f"[아프리카TV 알림] {username}",
            "avatar_url": avatar_url,
            "embeds": [embed]
        }

    async def _send_comment(self, message_list):
        """아프리카TV 댓글 전송"""
        try:
            import aiohttp
            from base import getAfreecaCookie, getDefaultHeaders
            
            # 쿠키와 헤더 준비
            headers = getDefaultHeaders()
            cookies = getAfreecaCookie()
            
            # 아프리카TV VOD 댓글 작성을 위한 데이터 준비
            vod_info = {
                'title_no': str(self.data.videoNo),
                'bj_id': self.id_list.loc[self.channel_id, 'afreecaID']
            }
            
            message = "\n\n".join(message_list)
            
            post_data = {
                'nTitleNo': vod_info['title_no'],
                'bj_id': vod_info['bj_id'],
                'nBoardType': '105',
                'szContent': message,
                'szAction': 'write',
                'nParentCommentNo': '0',
                'nCommentPhotoType': '1',
                'szCommentPhoto': '',
                'szFileType': 'REVIEW'
            }
            
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://stbbs.sooplive.co.kr/api/bbs_memo_action.php',
                    data=post_data,
                    headers=headers,
                    cookies=cookies,
                    timeout=15
                ) as response:
                    
                    if response.status == 200:
                        response_text = await response.text()
                        response_text = response_text.strip()
                        
                        try:
                            # JSON 응답 파싱 시도
                            json_resp = loads(response_text)
                            if 'CHANNEL' in json_resp:
                                result = json_resp['CHANNEL'].get('RESULT', 0)
                                msg = json_resp['CHANNEL'].get('MSG', '')
                                
                                if result == 1:
                                    print(f"{datetime.now()} 아프리카TV 댓글 작성 성공!")
                                    return True
                                elif result == -10:
                                    print(f"{datetime.now()} 아프리카TV 댓글 실패: 로그인이 필요합니다")
                                    return False
                                else:
                                    print(f"{datetime.now()} 아프리카TV 댓글 실패: {msg} (코드: {result})")
                                    return False
                                    
                        except Exception:
                            # JSON이 아닌 응답의 경우 - 단순 성공 응답 체크
                            if response_text in ['1', 'success', 'ok']:
                                print(f"{datetime.now()} 아프리카TV 댓글 작성 성공!")
                                return True
                            else:
                                print(f"{datetime.now()} 아프리카TV 댓글 알 수 없는 응답: {response_text}")
                                return False
                    else:
                        print(f"{datetime.now()} 아프리카TV 댓글 HTTP 오류: {response.status}")
                        return False
                        
        except Exception as e:
            await log_error(f"아프리카TV 댓글 전송 오류: {e}")
            return False