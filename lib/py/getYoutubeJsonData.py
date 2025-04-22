import asyncio
import aiohttp
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError, Error
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from base import subjectReplace, iconLinkData, initVar, get_message, saveYoutubeData
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from my_app import send_push_notification

from dataclasses import dataclass
from typing import List, Optional

@dataclass
class YouTubeVideo:
    video_title: str
    thumbnail_link: str
    publish_time: str
    video_link: str
    description: str = ""

@dataclass 
class YouTubeVideoBatch:
    videos: List[YouTubeVideo]
    
    def __getitem__(self, idx: int) -> YouTubeVideo:
        return self.videos[idx]
    
    def sort_by_publish_time(self):
        def parse_time(time_str: str) -> datetime:
            return datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%SZ")
            
        self.videos.sort(
            key=lambda x: parse_time(x.publish_time),
            reverse=True
        )

class getYoutubeJsonData:
	def __init__(self, init_var: initVar, developerKey, youtubeChannelID):
		self.developerKey = developerKey
		self.init = init_var
		self.DO_TEST = init_var.DO_TEST
		self.userStateData = init_var.userStateData
		self.youtubeData = init_var.youtubeData
		self.chzzkIDList = init_var.chzzkIDList
		self.afreecaIDList = init_var.afreecaIDList
		self.twitchIDList = init_var.twitchIDList
		self.youtubeChannelID = youtubeChannelID
		self.youtubechannelName = init_var.youtubeData.loc[youtubeChannelID, 'channelName']
		self.channel_id = init_var.youtubeData.loc[youtubeChannelID, 'channelID']

	async def start(self):
		try:
			self.new_video_json_data_list = []
			await self.check_youtube()
			await self.post_youtube()
	
		except Exception as e:
			if "RetryError" not in str(e):
				asyncio.create_task(DiscordWebhookSender._log_error(f"error Youtube {self.youtubeChannelID}: {str(e)}"))
			
	async def check_youtube(self):
		youtube_build = self.get_youtube_build()
		if youtube_build is None: 
			return
		
		channel_response = await self.get_youtube_channels_response(youtube_build)

		# 응답이 없거나 items가 비어있는 경우 처리
		if not self.check_item((channel_response)):
			print(f"{datetime.now()} No valid response for channel {self.youtubeChannelID}")
			return

		video_count = self.get_video_count(channel_response)

		if self.check_none_new_video():
			self.youtubeData.loc[self.youtubeChannelID, "videoCount"] += 1
			self.youtubeData.loc[self.youtubeChannelID, "video_count_check"] = 0
			#videoCount, video_count_check 만 저장하도록 수정하기
			await saveYoutubeData(self.youtubeData, self.youtubeChannelID)
			
		if self.check_new_video(video_count):
			self.youtubeData.loc[self.youtubeChannelID, "video_count_check"] += 1
			await self.get_youtube_thumbnail_url()

			search_response = await self.get_youtube_search_response(youtube_build)
			await self.filter_video(search_response, video_count)
		
		elif self.check_del_video(video_count):
			if video_count - self.youtubeData.loc[self.youtubeChannelID, "videoCount"] < 3:
				self.youtubeData.loc[self.youtubeChannelID, "videoCount"] -= 1
				#videoCount 만 저장하도록 수정하기
				await saveYoutubeData(self.youtubeData, self.youtubeChannelID)

	async def post_youtube(self):
		if self.new_video_json_data_list:
			self.youtubeData.loc[self.youtubeChannelID, "video_count_check"] = 0

			for json_data in reversed(self.new_video_json_data_list):
				if json_data is not None:
					list_of_urls= get_list_of_urls(self.DO_TEST, self.userStateData, self.youtubechannelName, self.channel_id, "유튜브 알림")

					asyncio.create_task(send_push_notification(list_of_urls, json_data))
					await DiscordWebhookSender().send_messages(list_of_urls, json_data)
					print(f'{datetime.now()} {json_data["username"]}: {json_data["embeds"][0]["title"]}')
					await asyncio.sleep(0.5)
			# 다 저장 하도록 수정하기
			await saveYoutubeData(self.youtubeData, self.youtubeChannelID) #save video count
			
	@retry(stop=stop_after_attempt(5), 
		wait=wait_exponential(multiplier=1, min=2, max=5),
		retry=retry_if_exception_type((asyncio.TimeoutError, ConnectionError)))
	def get_youtube_build(self):
		try:
			youtube_build = build('youtube', 'v3', 
							developerKey=self.developerKey,
							cache_discovery=False)
			# API 객체 생성 성공
			return youtube_build
		except HttpError as e:
			# HTTP 관련 오류 (403 Forbidden, 429 Too Many Requests 등)
			asyncio.create_task(DiscordWebhookSender._log_error(f"YouTube API HTTP 오류: {e.resp.status} {e.content}"))
			if e.resp.status in [403, 429]:
				asyncio.create_task(DiscordWebhookSender._log_error("API 키 할당량이 초과되었거나 권한이 없습니다."))
			return None
		except Error as e:
			# Google API 클라이언트 관련 오류
			asyncio.create_task(DiscordWebhookSender._log_error(f"Google API 클라이언트 오류: {e}"))
			return None
		except Exception as e:
			# 기타 예상치 못한 오류
			asyncio.create_task(DiscordWebhookSender._log_error(f"YouTube API build 오류: {e}"))
			return None

	@retry(stop=stop_after_attempt(5), 
		wait=wait_exponential(multiplier=1, min=2, max=5),
		retry=retry_if_exception_type((asyncio.TimeoutError, ConnectionError)))
	async def get_youtube_channels_response(self, youtube_build):
		try:
			channel_response = await asyncio.wait_for(
				asyncio.get_event_loop().run_in_executor(
					None,
					youtube_build.channels().list(
						part='statistics', 
						id=self.youtubeData.loc[self.youtubeChannelID, "channelCode"]
					).execute
				),
				timeout=3
			)
			return channel_response
		except HttpError as e:
			if e.resp.status == 503:
				# 503 에러는 일시적인 서버 문제
				print(f"{datetime.now()} YouTube API 일시적 오류 (채널: {self.youtubeChannelID})")
			raise  # 다른 HTTP 에러는 그대로 발생
		except asyncio.TimeoutError:
			print(f"{datetime.now()} Channel response timeout for {self.youtubeChannelID}")
			raise
		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error(f"error channel_response {e}"))
			return

	@retry(stop=stop_after_attempt(5), 
		wait=wait_exponential(multiplier=1, min=2, max=5), 
		retry=retry_if_exception_type((asyncio.TimeoutError, ConnectionError, HttpError)))
	async def get_youtube_search_response(self, youtube_build):
		try:
			search_response = await asyncio.wait_for(
				asyncio.get_event_loop().run_in_executor(
					None,
					youtube_build.search().list(
						part="id,snippet", 
						channelId=self.youtubeData.loc[self.youtubeChannelID, "channelCode"], 
						order="date", 
						type="video", 
						maxResults=3
					).execute
				),
				timeout=3
			)
			return search_response
		except HttpError as e:
			if e.resp.status == 503:
				print(f"{datetime.now()} YouTube API 일시적 오류 (채널 검색: {self.youtubeChannelID})")
			raise  # 모든 HTTP 에러는 재시도를 위해 다시 발생시킴
		except asyncio.TimeoutError:
			print(f"{datetime.now()} Search response timeout for {self.youtubeChannelID}")
			raise
		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error(f"error search_response {e}"))
			return

	def check_item(self, channel_response):
		return channel_response or 'items' not in channel_response or not channel_response['items']

	def get_video_count(self, channel_response):
		return int(channel_response['items'][0]['statistics']['videoCount'])

	def check_none_new_video(self):
		return self.youtubeData.loc[self.youtubeChannelID, "video_count_check"] > 3
	
	def check_new_video(self, video_count):
		return self.youtubeData.loc[self.youtubeChannelID, "videoCount"] < video_count
	
	def check_del_video(self, video_count):
		return self.youtubeData.loc[self.youtubeChannelID, "videoCount"] > video_count

	async def filter_video(self, response, video_count: int):
		try:
			newVideoNum = video_count - self.youtubeData.loc[self.youtubeChannelID, "videoCount"]
			tasks = [self.getYoutubeVars(response, i) for i in range(3)]
			videos = await asyncio.gather(*tasks)
			batch = YouTubeVideoBatch(videos=list(videos))
			batch.sort_by_publish_time()

			# 새로운 비디오 수
			newVideo = self.get_new_video_num(batch, newVideoNum)

			# 비디오 설명 가져오기
			for num in range(newVideo):
				batch.videos[num].description = await self.getDescription(
					str(batch.videos[num].video_link).replace("https://www.youtube.com/watch?v=", "")
			)
				
			self.new_video_json_data_list = [self.getYoutubeJson(video) for video in batch.videos[:newVideo]]

			if newVideo > 0:
				self._update_youtube_data(newVideoNum, batch, newVideo)

		except Exception as e:
			return
		
	def _update_youtube_data(self, newVideoNum, batch, newVideo):
		# 데이터 업데이트
		self.youtubeData.loc[self.youtubeChannelID, "videoCount"] += newVideoNum
		self.youtubeData.loc[self.youtubeChannelID, "uploadTime"] = batch.videos[0].publish_time
		
		# oldVideo 링크 업데이트
		old_links = [str(self.youtubeData.loc[self.youtubeChannelID, "oldVideo"][f"link{i}"]) 
					for i in range(1, 6)]
		new_links = [video.video_link for video in batch.videos[:newVideo]]
		
		updated_links = new_links + old_links[:-newVideo]
		for i, link in enumerate(updated_links[:5], 1):
			self.youtubeData.loc[self.youtubeChannelID, "oldVideo"][f"link{i}"] = link

	def get_new_video_num(self, batch, newVideoNum):
		# 새로운 비디오 체크를 위한 두 조건 배열 생성
		TF1 = [i < newVideoNum for i in range(3)]
		TF2 = [video.video_link not in self.youtubeData.loc[self.youtubeChannelID, "oldVideo"].values() 
			for video in batch.videos[:3]]
		if all(TF1) and all(TF2):
			newVideo = 3
		elif all(TF1[:2]) and all(TF2[:2]):
			newVideo = 2
		elif TF1[0] and TF2[0] and newVideoNum == 1:
			newVideo = 1
		else:
			newVideo = 0
		return newVideo

	async def getYoutubeVars(self, response, num) -> YouTubeVideo:
		title = subjectReplace(response['items'][num]['snippet']['title'])
		thumbnail = response['items'][num]['snippet']['thumbnails']["medium"]["url"].replace("mqdefault", "maxresdefault")
		
		# thumbnail URL 체크 로직
		async with aiohttp.ClientSession() as session:
			for i in range(10):
				if i == 4:
					thumbnail = response['items'][num]['snippet']['thumbnails']["medium"]["url"].replace("mqdefault", "sddefault")
				elif i == 9:
					thumbnail = response['items'][num]['snippet']['thumbnails']["medium"]["url"]
					
				async with session.get(thumbnail) as resp:
					if resp.status != 404:
						break
					await asyncio.sleep(0.05)
		
		channelName = response['items'][num]['snippet']['channelTitle']
		# channelCode = response['items'][0]['snippet']['channelId']
		publish_time = response['items'][num]['snippet']['publishTime']
		video_id = response['items'][num]['id']['videoId']
		video_link = f"https://www.youtube.com/watch?v={video_id}"
		
		return YouTubeVideo(
			video_title=title,
			thumbnail_link=thumbnail,
			publish_time=publish_time,
			video_link=video_link
		)
	
	async def getDescription(self, video_id: str) -> str:
		try:
			youtube = build(
				'youtube', 
				'v3', 
				developerKey=self.developerKey, 
				cache_discovery=False
			)
			
			result = await asyncio.wait_for(
				asyncio.get_running_loop().run_in_executor(
					None,
					lambda: youtube.videos().list(
						part='snippet',
						id=video_id
					).execute()
				),
				timeout=5
			)
			
			if not result.get('items'):
				return ""
				
			description = result['items'][0]['snippet']['description']
			return subjectReplace(description.split('\n')[0])
			
		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error(f"error youtube getDescription {e}"))
			return ""

	def get_user_data(self):
		channelID = self.youtubeData.loc[self.youtubeChannelID, "channelID"]
		
		# 플랫폼별 ID 리스트를 딕셔너리로 관리
		platform_lists = {
			'chzzk': self.chzzkIDList,
			'afreeca': self.afreecaIDList,
			'twitch': self.twitchIDList
		}
		
		# 채널 정보 찾기
		username = None
		avatar_url = None
		for platform_list in platform_lists.values():
			try:
				username = platform_list.loc[channelID, 'channelName']
				avatar_url = platform_list.loc[channelID, 'profile_image']
				break
			except Exception as e:
				continue
				
		if username is None or avatar_url is None:
			asyncio.create_task(DiscordWebhookSender._log_error(f"Channel information not found for channelID: {channelID}"))

		return username, avatar_url

	def getYoutubeJson(self, video) -> dict:
		username, avatar_url = self.get_user_data()
		youtube_data = self.youtubeData.loc[self.youtubeChannelID]
		
		return {
			"username": f" [유튜브 알림] {username}",
			"avatar_url": avatar_url,
			"embeds": [{
				"color": 16711680,
				"author": {
					"name": youtube_data['channelName'],
					"url": f"https://www.youtube.com/@{self.youtubeChannelID}",
					"icon_url": youtube_data['thumbnail_link']
				},
				"title": video.video_title,
				"url": video.video_link,
				"description": f"{youtube_data['channelName']} 유튜브 영상 업로드!",
				"fields": [{"name": 'Description', "value": video.description}],
				"thumbnail": {"url": youtube_data['thumbnail_link']},
				"image": {"url": video.thumbnail_link},
				"footer": {"text": "YouTube", "inline": True, "icon_url": iconLinkData().youtube_icon},
				"timestamp": video.publish_time
			}]
		}

	def get_index(self, channel_list, target_id):
			return {id: idx for idx, id in enumerate(channel_list)}[target_id]
	
	async def get_youtube_thumbnail_url(self):
		response = await get_message("youtube", f"https://www.youtube.com/@{self.youtubeChannelID}")
		if not response:
			asyncio.create_task(DiscordWebhookSender._log_error(f"error Youtube get_youtube_thumbnail_url.{self.youtubeChannelID}:"))
			return
		start_idx = response.find("https://yt3.googleusercontent.com")
		end_str = "no-rj"
		end_idx = response[start_idx:].find(end_str)
		thumbnail_url = response[start_idx:start_idx + end_idx + len(end_str)]
		if 110 < len(thumbnail_url) < 150:
			self.youtubeData.loc[self.youtubeChannelID, 'thumbnail_link'] = thumbnail_url
