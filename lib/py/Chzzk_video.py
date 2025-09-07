import asyncio
from json import loads
from datetime import datetime
from dataclasses import dataclass, field
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from notification_service import send_push_notification
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

        except Exception as e:
            asyncio.create_task(log_error(f"postLiveMSG {e}"))

    # 치지직 비디오 웹훅 JSON 데이터 생성 함수
    def getChzzk_video_json(self):
        # 비디오 정보 가져오기

        
        # 제목 포맷팅
        videoTitle = "|" + (videoTitle if videoTitle != " " else "                                                  ") + "|"
        
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

        self.data.videoNo = data["videoNo"]
        self.data.videoTitle = ["videoTitle"]
        self.data.publishDate = get_started_at(data.get("publishDate"))
        self.data.thumbnailImageUrl = data["thumbnailImageUrl"]
        self.data.videoCategoryValue = data["videoCategoryValue"]

    # 비디오 번호 목록 업데이트 함수 (최대 10개 유지)
    def _update_videoNo_list(self, chzzk_video_json):
        # 목록이 이미 10개 이상인 경우 가장 오래된 항목 제거
        if len(chzzk_video_json["videoNo_list"]) >= 10:
            chzzk_video_json["videoNo_list"][:-1] = chzzk_video_json["videoNo_list"][1:]
            chzzk_video_json["videoNo_list"][-1] = self.videoNo
        else:
            # 목록에 추가
            chzzk_video_json["videoNo_list"].append(self.videoNo)

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