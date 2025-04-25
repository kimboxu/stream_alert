import asyncio
from datetime import datetime
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from base import (changeUTCtime, get_message, iconLinkData, initVar, chzzk_saveVideoData)
from my_app import send_push_notification


class chzzk_video:
    def __init__(self, init_var: initVar, chzzk_id):
        self.DO_TEST = init_var.DO_TEST
        self.chzzkIDList = init_var.chzzkIDList
        self.chzzk_video = init_var.chzzk_video
        self.userStateData = init_var.userStateData
        self.chzzk_id = chzzk_id

    async def start(self):
        self.video_alarm_List: list = []
        await self.check_chzzk_video()
        await self.post_chzzk_video()

    async def check_chzzk_video(self):
        try:
            def get_link(uid):
                return f"https://api.chzzk.naver.com/service/v1/channels/{uid}/videos"
            
            uid = self.chzzkIDList.loc[self.chzzk_id, 'channel_code']
            stateData = await get_message("chzzk", get_link(uid))

            if not self._should_process_video(stateData):
                return
            
            if not self.check_video_data(stateData):
                return
            
            await self._process_video_data(stateData)

        except Exception as e:
            asyncio.create_task(DiscordWebhookSender._log_error(f"error get stateData chzzk video.{self.chzzk_id}.{e}."))

    def _should_process_video(self, stateData):
        return stateData and stateData["code"] == 200
    
    def check_video_data(self, stateData):
        if not stateData.get("content", {}).get("data", []):
            return False
        return True


    async def _process_video_data(self, stateData):
        videoNo, videoTitle, publishDate, thumbnailImageUrl, _ = self.getChzzkState(stateData)
        
        if not self.check_new_video(videoNo, publishDate, thumbnailImageUrl):
            return
        # 비디오 데이터 처리 및 저장
        json_data = self.getChzzk_video_json(stateData)
        self._update_videoNo_list(self.chzzk_video.loc[self.chzzk_id, 'VOD_json'], videoNo)
        self.chzzk_video.loc[self.chzzk_id, 'VOD_json']["publishDate"] = publishDate

        self.video_alarm_List.append((json_data, videoTitle))
        await chzzk_saveVideoData(self.chzzk_video, self.chzzk_id)

    def check_new_video(self, videoNo, publishDate, thumbnailImageUrl):
        # 이미 처리된 비디오 건너뛰기
        old_publishDate = self.chzzk_video.loc[self.chzzk_id, 'VOD_json']["publishDate"]
        videoNo_list = self.chzzk_video.loc[self.chzzk_id, 'VOD_json']["videoNo_list"]

        if (publishDate <= old_publishDate or 
            videoNo in videoNo_list):
            return False

        # 썸네일 URL 검증
        if not thumbnailImageUrl or "https://video-phinf.pstatic.net" not in thumbnailImageUrl:
            return False
        return True
 
    async def post_chzzk_video(self):
        try:
            if not self.video_alarm_List:
                return
            json_data, videoTitle = self.video_alarm_List.pop(0)
            channel_name = self.chzzkIDList.loc[self.chzzk_id, 'channelName']
            print(f"{datetime.now()} VOD upload {channel_name} {videoTitle}")

            list_of_urls = get_list_of_urls(self.DO_TEST, self.userStateData, channel_name, self.chzzk_id, "치지직 VOD")

            asyncio.create_task(send_push_notification(list_of_urls, json_data))
            asyncio.create_task(DiscordWebhookSender().send_messages(list_of_urls, json_data))

        except Exception as e:
            asyncio.create_task(DiscordWebhookSender._log_error(f"postLiveMSG {e}"))

    def getChzzk_video_json(self, stateData):
        videoNo, videoTitle, publishDate, thumbnailImageUrl, videoCategoryValue = self.getChzzkState(stateData)
        
        videoTitle = "|" + (videoTitle if videoTitle != " " else "                                                  ") + "|"
        
        channel_data = self.chzzkIDList.loc[self.chzzk_id]
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
            "url": f"https://chzzk.naver.com/video/{videoNo}",
            "description": f"{username} 치지직 영상 업로드!",
            "fields": [
                {"name": 'Category', "value": videoCategoryValue}
            ],
            "thumbnail": {"url": avatar_url},
            "image": {"url": thumbnailImageUrl},
            "footer": {
                "text": "Chzzk",
                "inline": True,
                "icon_url": iconLinkData.chzzk_icon
            },
            "timestamp": changeUTCtime(publishDate)
        }
        
        return {
            "username": f"[치지직 알림] {username}",
            "avatar_url": avatar_url,
            "embeds": [embed]
        }
    
    def getChzzkState(self, stateData):
        def get_started_at(date_str) -> str | None:
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str).isoformat()
            except ValueError:
                return None

        data = stateData["content"]["data"][0]
        return (
            data["videoNo"],
            data["videoTitle"],
            get_started_at(data.get("publishDate")),
            data["thumbnailImageUrl"],
            data["videoCategoryValue"]
        )

    def _update_videoNo_list(self, chzzk_video_json, videoNo):
        if len(chzzk_video_json["videoNo_list"]) >= 10:
            chzzk_video_json["videoNo_list"][:-1] = chzzk_video_json["videoNo_list"][1:]
            chzzk_video_json["videoNo_list"][-1] = videoNo
        else:
            chzzk_video_json["videoNo_list"].append(videoNo)