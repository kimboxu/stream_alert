import asyncio
from json import loads
from datetime import datetime
from dataclasses import dataclass, field
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from notification_service import send_push_notification
from live_message import highlight_chat_Data
from make_log_api_performance import PerformanceManager
from base import (
    changeUTCtime, 
    get_message, 
    iconLinkData, 
    initVar, 
    chzzk_saveVideoData, 
    log_error,
    getChzzkCookie,
    getDefaultHeaders,
    calculate_stream_duration,
)

@dataclass
class ChzzkVOD_Data:
    """ chzzk Vod 데이터를 저장하는 클래스"""
    videoNo : int = 0                           # 비디오 숫자
    videoTitle : str = ""                       # 비디오 제목
    publishDate : datetime = datetime.now()     # 게시 날짜
    thumbnailImageUrl : str = ""                # 썸네일 이미지 URL
    videoCategoryValue : str = ""               # 비디오 카테고리
    video_alarm_List: list = field(default_factory=list)
    duration: int = 0                           # 비디오 길이(초)

class chzzk_video:
    # 초기화 함수: 필요한 데이터와 채널 ID 설정
    def __init__(self, init_var: initVar, performance_manager: PerformanceManager, chzzk_id):
        self.init = init_var
        self.performance_manager = performance_manager
        self.DO_TEST = init_var.DO_TEST  # 테스트 모드 여부
        self.chzzkIDList = init_var.chzzkIDList  # 치지직 채널 ID 리스트
        self.chzzk_video = init_var.chzzk_video  # 치지직 비디오 데이터
        self.userStateData = init_var.userStateData  # 사용자 상태 데이터
        self.chzzk_id = chzzk_id  # 현재 처리할 치지직 채널 ID
        self.time_offset = 20   # window_size 만큼의 길이 - 10초
        self.duration_diff = 0  # 실제 방송시간과 VOD 길이 와의 차이
        self.small_fun_difference = 50
        self.big_fun_difference = 70
        self.data = ChzzkVOD_Data()

    async def start(self):
        await self.check_chzzk_video()  # 비디오 데이터 확인
        await self.post_chzzk_video()  # 비디오 알림 전송

    # 치지직 비디오 데이터 확인 함수
    async def check_chzzk_video(self):
        try:
            # 채널 비디오 API 링크 생성
            def get_link(uid):
                return f"https://api.chzzk.naver.com/service/v1/channels/{uid}/videos"
            
            # 채널 코드 가져오기 및 API 요청
            uid = self.chzzkIDList.loc[self.chzzk_id, 'channel_code']
            stateData = await get_message(self.performance_manager, "chzzk", get_link(uid))

            # 비디오 데이터 처리 여부 확인
            if not self._should_process_video(stateData):
                return
            
            # 비디오 데이터 존재 여부 확인
            if not self.check_video_data(stateData):
                return
            
            # 비디오 데이터 처리
            await self._process_video_data(stateData)

        except Exception as e:
            asyncio.create_task(log_error(f"error get stateData chzzk video.{self.chzzk_id}.{e}."))

    # API 응답이 유효한지 확인하는 함수
    def _should_process_video(self, stateData):
        return stateData and stateData["code"] == 200
    
    # 비디오 데이터가 존재하는지 확인하는 함수
    def check_video_data(self, stateData):
        if not stateData.get("content", {}).get("data", []):
            return False
        return True

    # 비디오 데이터 처리 함수
    async def _process_video_data(self, stateData):
        # 비디오 정보 가져오기
        self.getChzzkState(stateData)
        
        # 새 비디오인지 확인
        if not self.check_new_video():
            return
        
        # 비디오 데이터 JSON 생성 및 저장
        json_data = self.getChzzk_video_json()
        self._update_videoNo_list(self.chzzk_video.loc[self.chzzk_id, 'VOD_json'])
        self.chzzk_video.loc[self.chzzk_id, 'VOD_json']["publishDate"] = changeUTCtime(self.data.publishDate)

        # 알림 목록에 추가
        self.data.video_alarm_List.append((json_data))
        await chzzk_saveVideoData(self.chzzk_video, self.chzzk_id)

    # 새 비디오인지 확인하는 함수
    def check_new_video(self):
        # 이미 처리된 비디오 정보
        old_publishDate = self.chzzk_video.loc[self.chzzk_id, 'VOD_json']["publishDate"]
        videoNo_list = self.chzzk_video.loc[self.chzzk_id, 'VOD_json']["videoNo_list"]

        # 이미 등록된 비디오거나 이전 날짜의 비디오인 경우 건너뛰기
        if (changeUTCtime(self.data.publishDate) <= old_publishDate or 
            self.data.videoNo in videoNo_list):
            return False

        # 썸네일 URL 검증
        if not self.data.thumbnailImageUrl or "https://video-phinf.pstatic.net" not in self.data.thumbnailImageUrl:
            return False
        return True
 
    # 비디오 알림 전송 함수
    async def post_chzzk_video(self):
        try:
            # 알림 목록이 비어있으면 종료
            if not self.data.video_alarm_List:
                return
            
            # 알림 목록에서 항목 가져오기
            json_data = self.data.video_alarm_List.pop(0)
            channel_name = self.chzzkIDList.loc[self.chzzk_id, 'channelName']
            print(f"{datetime.now()} VOD upload {channel_name} {self.data.videoTitle}")

            # 알림을 보낼 웹훅 URL들 가져오기
            list_of_urls = get_list_of_urls(self.DO_TEST, self.userStateData, channel_name, self.chzzk_id, "치지직 VOD")

            # 푸시 알림 및 디스코드 웹훅 전송
            asyncio.create_task(send_push_notification(list_of_urls, json_data))
            asyncio.create_task(DiscordWebhookSender().send_messages(list_of_urls, json_data))

            highlight_chat = None
            print(f"{datetime.now()} self.init.highlight_chat[self.chzzk_id],{self.init.highlight_chat[self.chzzk_id]}")
            print(f"{datetime.now()} self.data,{self.data}")
            # 다시보기에 하이라이트 댓글 달기
            for stream_start_id in self.init.highlight_chat[self.chzzk_id]:
                highlight_chat_data = self.init.highlight_chat[self.chzzk_id][stream_start_id]
                
                # stream_end_id가 설정되어 있는지 확인
                if not hasattr(highlight_chat_data, 'stream_end_id') or not highlight_chat_data.stream_end_id:
                    continue
                    
                try:
                    # 방송 지속시간 계산
                    broadcast_duration = calculate_stream_duration(stream_start_id, highlight_chat_data.stream_end_id)
                    
                    # VOD 길이와 방송 시간 차이가 60초 이내이고 제목이 일치하는지 확인
                    self.duration_diff = min(broadcast_duration - self.data.duration, 0)
                    title_matches = highlight_chat_data.last_title == self.data.videoTitle
                    print(f"{datetime.now()} duration_diff,{self.duration_diff}")
                    if self.duration_diff < 60 and title_matches:
                        highlight_chat = self.init.highlight_chat[self.chzzk_id].pop(stream_start_id, None)
                        break
                        
                except ValueError as e:
                    asyncio.create_task(log_error(f"방송 지속시간 계산 오류: {e}, broadcast_duration:{broadcast_duration}"))
                    continue

            if highlight_chat:
                # 하이라이트 메시지들을 여러 댓글로 분할
                highlight_message = self.get_highlight_msg(highlight_chat)
                
                if highlight_message:
                    # 첫 번째 댓글 작성
                    first_comment_id = await self._send_comment(highlight_message, self.data.videoNo)
                    
                    # # 나머지 메시지들을 답글로 작성
                    # if first_comment_id and len(highlight_message) > 1:
                    #     await self._send_reply_comments(first_comment_id, highlight_message)

        except Exception as e:
            asyncio.create_task(log_error(f"postLiveMSG {e}"))

    # 치지직 비디오 웹훅 JSON 데이터 생성 함수
    def getChzzk_video_json(self):
        # 제목 포맷팅
        videoTitle = "|" + (self.data.videoTitle if self.data.videoTitle != " " else "                                                  ") + "|"
        
        # 채널 정보 가져오기
        channel_data = self.chzzkIDList.loc[self.chzzk_id]
        username = channel_data['channelName']
        avatar_url = channel_data['profile_image']
        video_url = f"https://chzzk.naver.com/{channel_data['channel_code']}/video"
        
        # 디스코드 임베드 생성
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
    
    # 치지직 API 응답에서 비디오 정보 추출 함수
    def getChzzkState(self, stateData):
        # 날짜 포맷 변환 함수
        def get_started_at(date_str) -> str | None:
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str).isoformat()
            except ValueError:
                return None

        # 첫 번째 비디오 데이터 가져오기
        data = stateData["content"]["data"][0]

        self.data.duration = data["duration"]
        self.data.videoNo = data["videoNo"]
        self.data.videoTitle = data["videoTitle"]
        self.data.publishDate = get_started_at(data.get("publishDate"))
        self.data.thumbnailImageUrl = data["thumbnailImageUrl"]
        self.data.videoCategoryValue = data["videoCategoryValue"]

    # 비디오 번호 목록 업데이트 함수 (최대 10개 유지)
    def _update_videoNo_list(self, chzzk_video_json):
        # 목록이 이미 10개 이상인 경우 가장 오래된 항목 제거
        if len(chzzk_video_json["videoNo_list"]) >= 10:
            chzzk_video_json["videoNo_list"][:-1] = chzzk_video_json["videoNo_list"][1:]
            chzzk_video_json["videoNo_list"][-1] = self.data.videoNo
        else:
            # 목록에 추가
            chzzk_video_json["videoNo_list"].append(self.data.videoNo)

    def get_highlight_msg(self, highlight_chat: highlight_chat_Data):
        """
        하이라이트 채팅 데이터를 VOD 댓글 형식으로 변환
        
        Returns:
            list: VOD에 작성할 댓글 문자열 리스트 (각각 최대 500자)
        """
        timeline_comments = highlight_chat.timeline_comments
        
        if not timeline_comments or not isinstance(timeline_comments, list):
            return []
        
        # 시간순으로 정렬
        timeline_comments.sort(key=lambda x: x.get('after_openDate', ''))
        
        # 댓글 라인들을 저장할 리스트
        comment_lines = []

        # 자동 생성 안내 문구 먼저 추가
        auto_notice = "🤖 이 댓글은 방송 하이라이트를 자동 분석하여 생성된 타임라인입니다."
        comment_lines.append(auto_notice)

        for comment in timeline_comments:
            time_str = comment.get('after_openDate', '')
            text = comment.get('text', '')
            description = comment.get('description', '')
            score_difference = float(comment.get('score_difference', 0))
            
            if not time_str or not description:
                continue
                
            # 시간 형식 정리 (HH:MM:SS 형식으로 통일)
            formatted_time = self._format_time_for_comment(time_str)
            if not formatted_time:
                continue
                
            # 댓글 라인 생성: **HH:MM:SS**- 내용
            if score_difference > self.small_fun_difference:
                description = f"*{description}"
            if score_difference > self.big_fun_difference:
                description = f"*{description}"

            comment_line = f"{formatted_time}- {description}"
            comment_lines.append(comment_line)
        
        if not comment_lines:
            return []
        
        highlight_message = "\n\n".join(comment_lines)
        
        return highlight_message
    
    def _format_time_for_comment(self, time_str: str) -> str:
        """시간 문자열을 댓글용 HH:MM:SS 형식으로 변환"""
        try:
            parts = time_str.strip().split(':')
            
            # 총 초 계산
            if len(parts) == 2:
                minutes, seconds = map(int, parts)
                total_seconds = minutes * 60 + seconds
            elif len(parts) == 3:
                hours, minutes, seconds = map(int, parts)
                total_seconds = hours * 3600 + minutes * 60 + seconds
            else:
                return ""
            
            # 오프셋 적용 (음수 방지)
            adjusted_seconds = max(0, total_seconds - (self.time_offset + self.duration_diff//2))
            
            # 시:분:초로 변환
            h, remainder = divmod(adjusted_seconds, 3600)
            m, s = divmod(remainder, 60)
            
            return f"{h:02d}:{m:02d}:{s:02d}"
            
        except (ValueError, IndexError):
            return ""       

    async def _send_comment(self, message, videoNo):
        """
        첫 번째 댓글 전송
        
        Returns:
            int: 성공 시 댓글 ID, 실패 시 None
        """
        try:
            def get_link():
                return f"https://apis.naver.com/nng_main/nng_comment_api/v1/type/STREAMING_VIDEO/id/{videoNo}/comments"
            
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
            
            # aiohttp를 사용한 비동기 요청
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
                                comment_id = response_data['content'].get('commentId')
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
            await log_error(f"_send_comment 오류: {e}")
            return None
        
    async def _send_reply_comments(self, parent_comment_id: int, reply_messages: list):
        """
        답글들을 순차적으로 전송
        
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
                        await asyncio.sleep(1)
                        
                    except Exception as reply_error:
                        print(f"{datetime.now()} 답글 {i+1} 전송 오류: {reply_error}")
                        continue
                        
        except Exception as e:
            await log_error(f"_send_reply_comments 오류: {e}")