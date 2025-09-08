import asyncio
from json import loads
from datetime import datetime
from dataclasses import dataclass, field
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from notification_service import send_push_notification
from live_message import highlight_chat_Data
from base import (
    changeUTCtime, 
    get_message, 
    iconLinkData, 
    initVar, 
    chzzk_saveVideoData, 
    log_error,
    getChzzkCookie,
    getDefaultHeaders,
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
    def __init__(self, init_var: initVar, chzzk_id):
        self.init = init_var
        self.DO_TEST = init_var.DO_TEST  # 테스트 모드 여부
        self.chzzkIDList = init_var.chzzkIDList  # 치지직 채널 ID 리스트
        self.chzzk_video = init_var.chzzk_video  # 치지직 비디오 데이터
        self.userStateData = init_var.userStateData  # 사용자 상태 데이터
        self.chzzk_id = chzzk_id  # 현재 처리할 치지직 채널 ID
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
            stateData = await get_message("chzzk", get_link(uid))

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
            # 다시보기에 하이라이트 댓글 달기
            for stream_start_id in self.init.highlight_chat[self.chzzk_id]:
                stream_end_id = self.init.highlight_chat[self.chzzk_id][stream_start_id].stream_end_id
                if abs(int(self.data.duration - (stream_end_id - stream_start_id))) < 60 and self.init.highlight_chat[self.chzzk_id][stream_start_id].last_title == self.data.videoTitle:
                    highlight_chat = self.init.highlight_chat[self.chzzk_id].pop(stream_start_id, [])

            if highlight_chat:
                # 하이라이트 메시지들을 여러 댓글로 분할
                highlight_messages = self.get_highlight_msg(highlight_chat)
                
                if highlight_messages:
                    # 첫 번째 댓글 작성
                    first_comment_id = await self._send_comment(highlight_messages[0])
                    
                    # 나머지 메시지들을 답글로 작성
                    if first_comment_id and len(highlight_messages) > 1:
                        await self._send_reply_comments(first_comment_id, highlight_messages[1:])

        except Exception as e:
            asyncio.create_task(log_error(f"postLiveMSG {e}"))

    # 치지직 비디오 웹훅 JSON 데이터 생성 함수
    def getChzzk_video_json(self):
        # 비디오 정보 가져오기

        
        # 제목 포맷팅
        self.data.videoTitle = "|" + (self.data.videoTitle if self.data.videoTitle != " " else "                                                  ") + "|"
        
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
            "title": self.data.videoTitle,
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
        
        응답 형식:
        [시간] 댓글 내용
        [시간] 댓글 내용
        
        Args:
            highlight_chat: highlight_chat_Data 객체
            
        Returns:
            str: VOD에 작성할 댓글 문자열 (최대 500자)
        """
        timeline_comments = highlight_chat.timeline_comments
        
        if not timeline_comments or not isinstance(timeline_comments, list):
            return ""
        
        # 시간순으로 정렬
        timeline_comments.sort(key=lambda x: x.get('after_openDate', ''))
        
        # 댓글 라인들을 저장할 리스트
        comment_lines = []
        
        for comment in timeline_comments:
            time_str = comment.get('after_openDate', '')
            text = comment.get('text', '')
            
            if not time_str or not text:
                continue
                
            # 시간 형식 정리 (HH:MM:SS -> MM:SS 또는 H:MM:SS -> M:SS)
            formatted_time = self.format_time_for_comment(time_str)
            if not formatted_time:
                continue
                
            # 댓글 라인 생성: **시간** 내용
            comment_line = f"**{formatted_time}** {text}"
            comment_lines.append(comment_line)
        
        if not comment_lines:
            return ""
        
        # 모든 댓글을 하나의 문자열로 합치기
        full_comment = "".join(comment_lines)
        
        # 500자 제한 확인 및 조정
        if len(full_comment) <= 500:
            return full_comment
        
        # 500자를 초과하는 경우 댓글 수를 줄여가며 조정
        return self.trim_comment_to_limit(comment_lines, 500)
    
    def format_time_for_comment(self, time_str: str) -> str:
        """
        시간 문자열을 댓글용 형식으로 변환
        
        Args:
            time_str: "0:04:24" 또는 "4:24" 또는 "1:23:45" 형식의 시간
            
        Returns:
            str: "4:24" 형식의 시간 문자열
        """
        try:
            # 콜론으로 분리
            parts = time_str.strip().split(':')
            
            if len(parts) == 2:
                # MM:SS 형식
                minutes, seconds = parts
                return f"{int(minutes)}:{seconds.zfill(2)}"
                
            elif len(parts) == 3:
                # HH:MM:SS 형식
                hours, minutes, seconds = parts
                hours, minutes = int(hours), int(minutes)
                
                if hours == 0:
                    # 1시간 미만: MM:SS
                    return f"{minutes}:{seconds.zfill(2)}"
                else:
                    # 1시간 이상: H:MM:SS
                    return f"{hours}:{minutes:02d}:{seconds.zfill(2)}"
            
            return ""
            
        except (ValueError, IndexError):
            return ""
            
    def trim_comment_to_limit(self, comment_lines: list, max_length: int) -> str:
        """
        댓글 라인들을 최대 길이에 맞춰 조정
        
        Args:
            comment_lines: 댓글 라인 리스트
            max_length: 최대 허용 길이
            
        Returns:
            str: 길이 제한에 맞춘 댓글 문자열
        """
        if not comment_lines:
            return ""
        
        # 우선순위: 앞쪽 댓글들을 우선적으로 포함
        result_lines = []
        current_length = 0
        
        for line in comment_lines:
            # 현재 라인을 추가했을 때의 길이 계산
            if current_length == 0:
                new_length = len(line)
            else:
                new_length = current_length + len(line)
            
            # 제한을 초과하지 않으면 추가
            if new_length <= max_length:
                result_lines.append(line)
                current_length = new_length
            else:
                # 제한을 초과하면 중단
                break
        
        # 아무것도 포함할 수 없다면 첫 번째 댓글만 잘라서 포함
        if not result_lines and comment_lines:
            first_line = comment_lines[0]
            if len(first_line) > max_length:
                # 첫 번째 라인도 너무 길면 잘라내기
                # "**시간** " 부분은 보존하고 텍스트 부분만 자르기
                if "** " in first_line:
                    time_part = first_line.split("** ")[0] + "** "
                    text_part = first_line.split("** ", 1)[1]
                    available_length = max_length - len(time_part) - 3  # "..." 고려
                    if available_length > 0:
                        trimmed_text = text_part[:available_length] + "..."
                        result_lines.append(time_part + trimmed_text)
            else:
                result_lines.append(first_line)
        
        return "".join(result_lines)

    async def _send_comment(self, message):
        """댓글 전송"""
        try:
            # POST API 엔드포인트
            def get_link():
                return f"https://apis.naver.com/nng_main/nng_comment_api/v1/type/STREAMING_VIDEO/id/{self.data.videoNo}/comments"
            
            def get_VOD_chat_json():
                comment_data = {
                    "attach": False,
                    "commentAttaches": [],
                    "commentType": "COMMENT",
                    "content": message,
                    "deviceType": "PC",
                    "mentionedUserIdHash": "",
                    "parentCommentId": 0,
                    "secret": False
                }
                return comment_data
            
            async with self.data.session.post(get_link(), json=get_VOD_chat_json(), headers=getDefaultHeaders(), cookies=getChzzkCookie()) as response:
                print(f"응답 상태: {response.status}")
                response_text = await response.text()
                print(f"응답: {response_text}")
                
                if response.status == 200:
                    try:
                        response_data = loads(response_text)
                        # 성공 여부 확인
                        if response_data.get('code') == 200 or response_data.get('success') == True:
                            print("댓글 작성 성공!")
                            return True
                        else:
                            print(f"실패: {response_data}")
                            await log_error(f"댓글 작성 실패: {response_data}")
                            return False
                    except Exception as parse_error:
                        print(f"파싱 오류: {parse_error}")
                        await log_error(f"응답 파싱 오류: {parse_error}")
                        return False
                        
                elif response.status == 401:
                    await log_error("인증 오류 - 로그인 필요")
                    return False
                elif response.status == 403:
                    await log_error("권한 없음")
                    return False
                elif response.status == 500:
                    await log_error(f"서버 내부 오류 - 응답: {response_text}")
                    return False
                else:
                    await log_error(f"기타 오류: {response.status} - {response_text}")
                    return False
                    
        except Exception as e:
            await log_error(f"_send_comment 오류: {e}")
            return False