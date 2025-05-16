import asyncio
import aiohttp
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError, Error
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from base import subjectReplace, iconLinkData, initVar, get_message, saveYoutubeData, log_error
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from notification_service import send_push_notification

from dataclasses import dataclass
from typing import List, Optional

@dataclass
class YouTubeVideo:
    video_title: str       # 비디오 제목
    thumbnail_link: str    # 썸네일 링크
    publish_time: str      # 게시 시간
    video_link: str        # 비디오 링크
    description: str = ""  # 비디오 설명 (기본값은 빈 문자열)

# 여러 유튜브 비디오를 묶어서 처리하는 배치 클래스
@dataclass 
class YouTubeVideoBatch:
    videos: List[YouTubeVideo]  # 유튜브 비디오 목록
    
    # 인덱스로 videos에 접근할 수 있도록 설정
    def __getitem__(self, idx: int) -> YouTubeVideo:
        return self.videos[idx]
    
    # 발행 시간 기준으로 정렬하는 메서드
    def sort_by_publish_time(self):
        def parse_time(time_str: str) -> datetime:
            return datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%SZ")
            
        # 최신 비디오가 앞에 오도록 역순 정렬
        self.videos.sort(
            key=lambda x: parse_time(x.publish_time),
            reverse=True
        )

# 유튜브 데이터를 처리하는 메인 클래스
class getYoutubeJsonData:
	# 초기화 함수
	def __init__(self, init_var: initVar, developerKey, youtubeChannelID):
		self.developerKey = developerKey         # YouTube API 키
		self.DO_TEST = init_var.DO_TEST          # 테스트 모드 여부
		self.userStateData = init_var.userStateData  # 사용자 상태 데이터
		self.youtubeData = init_var.youtubeData  # 유튜브 데이터
		self.chzzkIDList = init_var.chzzkIDList  # 치지직 ID 목록
		self.afreecaIDList = init_var.afreecaIDList  # 아프리카 ID 목록
		self.twitchIDList = init_var.twitchIDList    # 트위치 ID 목록
		self.youtubeChannelID = youtubeChannelID     # 처리할 유튜브 채널 ID
		self.youtubechannelName = init_var.youtubeData.loc[youtubeChannelID, 'channelName']  # 채널 이름
		self.channel_id = init_var.youtubeData.loc[youtubeChannelID, 'channelID']  # 내부 채널 ID

	async def start(self):
		try:
			self.new_video_json_data_list = []  # 새 비디오 데이터 목록
			await self.check_youtube()  # 유튜브 채널 확인
			await self.post_youtube()   # 새 비디오 알림 전송
	
		except Exception as e:
			if "RetryError" not in str(e):
				asyncio.create_task(log_error(f"error Youtube {self.youtubeChannelID}: {str(e)}"))
			
	# 유튜브 채널의 새 비디오를 확인하는 함수
	async def check_youtube(self):
		# YouTube API 클라이언트 생성
		youtube_build = self.get_youtube_build()
		if youtube_build is None: 
			return
		
		# 채널 정보 요청
		channel_response = await self.get_youtube_channels_response(youtube_build)

		# 응답 유효성 검사
		if not self.check_item((channel_response)):
			asyncio.create_task(log_error(f"No valid response for channel {self.youtubeChannelID}"))
			print(f"{datetime.now()} {channel_response}")
			return

		# 비디오 수 가져오기
		video_count = self.get_video_count(channel_response)

		# 새 비디오가 없지만 확인 횟수가 임계값을 넘은 경우(기존 유튜브 영상 갯수 보다 현재의 영상 갯수가 많지 만 새 영상이 일정 횟수 동안 확인이 되지 않는 경우)
		#유튜브 api 과하게 사용하는 경우에 문제가 생길 수 있으므로
		if self.check_none_new_video():
			self.youtubeData.loc[self.youtubeChannelID, "videoCount"] += 1
			self.youtubeData.loc[self.youtubeChannelID, "video_count_check"] = 0
			# 데이터 저장
			await saveYoutubeData(self.youtubeData, self.youtubeChannelID)
			
		# 새 비디오가 있는 경우
		if self.check_new_video(video_count):
			self.youtubeData.loc[self.youtubeChannelID, "video_count_check"] += 1
			await self.get_youtube_thumbnail_url()  # 채널 썸네일 이미지 확인 및 가져오기 

			# 검색 API로 최신 비디오 정보 가져오기
			search_response = await self.get_youtube_search_response(youtube_build)
			await self.filter_video(search_response, video_count)
		
		# 비디오가 삭제된 경우
		elif self.check_del_video(video_count):
			if video_count - self.youtubeData.loc[self.youtubeChannelID, "videoCount"] < 3:
				self.youtubeData.loc[self.youtubeChannelID, "videoCount"] -= 1
				# 데이터 저장
				await saveYoutubeData(self.youtubeData, self.youtubeChannelID)

	# 새 비디오 알림을 전송하는 함수
	async def post_youtube(self):
		if self.new_video_json_data_list:
			self.youtubeData.loc[self.youtubeChannelID, "video_count_check"] = 0

			# 오래된 비디오부터 처리 (역순으로 처리)
			for json_data in reversed(self.new_video_json_data_list):
				if json_data is not None:
					# 알림을 보낼 웹훅 URL 목록 가져오기
					list_of_urls= get_list_of_urls(self.DO_TEST, self.userStateData, self.youtubechannelName, self.channel_id, "유튜브 알림")

					# 푸시 알림 및 디스코드 웹훅 전송
					asyncio.create_task(send_push_notification(list_of_urls, json_data))
					await DiscordWebhookSender().send_messages(list_of_urls, json_data)
					print(f'{datetime.now()} {json_data["username"]}: {json_data["embeds"][0]["title"]}')
					await asyncio.sleep(0.5)  # 웹훅 전송 간 딜레이
					
			# 데이터 저장
			await saveYoutubeData(self.youtubeData, self.youtubeChannelID)
			
	# YouTube API 클라이언트 생성 함수 (재시도 로직 포함)
	@retry(stop=stop_after_attempt(5), 
		wait=wait_exponential(multiplier=1, min=2, max=5),
		retry=retry_if_exception_type((asyncio.TimeoutError, ConnectionError)))
	def get_youtube_build(self):
		try:
			# YouTube API v3 클라이언트 생성
			youtube_build = build('youtube', 'v3', 
							developerKey=self.developerKey,
							cache_discovery=False)
			return youtube_build
		except HttpError as e:
			# HTTP 관련 오류 처리
			asyncio.create_task(log_error(f"YouTube API HTTP 오류: {e.resp.status} {e.content}"))
			if e.resp.status in [403, 429]:
				asyncio.create_task(log_error("API 키 할당량이 초과되었거나 권한이 없습니다."))
			return None
		except Error as e:
			# Google API 클라이언트 관련 오류
			asyncio.create_task(log_error(f"Google API 클라이언트 오류: {e}"))
			return None
		except Exception as e:
			# 기타 예상치 못한 오류
			asyncio.create_task(log_error(f"YouTube API build 오류: {e}"))
			return None

	# 채널 정보 요청 함수 (재시도 로직 포함)
	@retry(stop=stop_after_attempt(5), 
		wait=wait_exponential(multiplier=1, min=2, max=5),
		retry=retry_if_exception_type((asyncio.TimeoutError, ConnectionError)))
	async def get_youtube_channels_response(self, youtube_build):
		try:
			# 채널 통계 정보 요청
			channel_response = await asyncio.wait_for(
				asyncio.get_event_loop().run_in_executor(
					None,
					youtube_build.channels().list(
						part='statistics', 
						id=self.youtubeData.loc[self.youtubeChannelID, "channelCode"]
					).execute
				),
				timeout=10  # 10초 타임아웃
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
			asyncio.create_task(log_error(f"error channel_response {e}"))
			return

	# 비디오 검색 요청 함수 (재시도 로직 포함)
	@retry(stop=stop_after_attempt(5), 
		wait=wait_exponential(multiplier=1, min=2, max=5), 
		retry=retry_if_exception_type((asyncio.TimeoutError, ConnectionError, HttpError)))
	async def get_youtube_search_response(self, youtube_build):
		try:
			# 채널의 최신 비디오 검색
			search_response = await asyncio.wait_for(
				asyncio.get_event_loop().run_in_executor(
					None,
					youtube_build.search().list(
						part="id,snippet", 
						channelId=self.youtubeData.loc[self.youtubeChannelID, "channelCode"], 
						order="date",
						type="video",
						maxResults=3   # 최대 3개
					).execute
				),
				timeout=3  # 3초 타임아웃
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
			asyncio.create_task(log_error(f"error search_response {e}"))
			return

	# 응답에 유효한 항목이 있는지 확인하는 함수
	def check_item(self, channel_response):
		return channel_response and 'items' in channel_response and channel_response['items']

	# 비디오 수를 가져오는 함수
	def get_video_count(self, channel_response):
		return int(channel_response['items'][0]['statistics']['videoCount'])

	# 새 비디오가 없지만 확인 횟수가 임계값을 넘은 경우(기존 유튜브 영상 갯수 보다 현재의 영상 갯수가 많지 만 새 영상이 일정 횟수 동안 확인이 되지 않는 경우)
	def check_none_new_video(self):
		return self.youtubeData.loc[self.youtubeChannelID, "video_count_check"] > 3
	
	# 새 비디오가 있는지 확인하는 함수
	def check_new_video(self, video_count):
		return self.youtubeData.loc[self.youtubeChannelID, "videoCount"] < video_count
	
	# 비디오가 삭제되었는지 확인하는 함수
	def check_del_video(self, video_count):
		return self.youtubeData.loc[self.youtubeChannelID, "videoCount"] > video_count

	# 비디오 필터링 및 처리 함수
	async def filter_video(self, response, video_count: int):
		try:
			# 새 비디오 수 계산
			newVideoNum = video_count - self.youtubeData.loc[self.youtubeChannelID, "videoCount"]
			
			# 최대 3개의 비디오 정보를 병렬로 가져오기
			tasks = [self.getYoutubeVars(response, i) for i in range(3)]
			videos = await asyncio.gather(*tasks)
			batch = YouTubeVideoBatch(videos=list(videos))
			batch.sort_by_publish_time()  # 발행 시간 기준 정렬

			# 실제 새 비디오 수 확인
			newVideo = self.get_new_video_num(batch, newVideoNum)

			# 비디오 설명 가져오기
			for num in range(newVideo):
				batch.videos[num].description = await self.getDescription(
					str(batch.videos[num].video_link).replace("https://www.youtube.com/watch?v=", "")
			)
				
			# 웹훅 JSON 데이터 생성
			self.new_video_json_data_list = [self.getYoutubeJson(video) for video in batch.videos[:newVideo]]

			# 실제 새 비디오가 있는 경우 데이터 업데이트
			if newVideo > 0:
				self._update_youtube_data(newVideoNum, batch, newVideo)

		except Exception as e:
			return
		
	# 유튜브 데이터 업데이트 함수
	def _update_youtube_data(self, newVideoNum, batch, newVideo):
		# 비디오 수 업데이트
		self.youtubeData.loc[self.youtubeChannelID, "videoCount"] += newVideoNum
		self.youtubeData.loc[self.youtubeChannelID, "uploadTime"] = batch.videos[0].publish_time
		
		# 이전 비디오 링크 목록 가져오기
		old_links = [str(self.youtubeData.loc[self.youtubeChannelID, "oldVideo"][f"link{i}"]) 
					for i in range(1, 6)]
		# 새 비디오 링크 목록
		new_links = [video.video_link for video in batch.videos[:newVideo]]
		
		# 링크 목록 업데이트 (최대 5개 유지)
		updated_links = new_links + old_links[:-newVideo]
		for i, link in enumerate(updated_links[:5], 1):
			self.youtubeData.loc[self.youtubeChannelID, "oldVideo"][f"link{i}"] = link

	# 실제 새 비디오 수를 계산하는 함수
	def get_new_video_num(self, batch, newVideoNum):
		# 새로운 비디오 체크를 위한 두 조건 배열 생성
		# 1. 비디오 수 조건: 인덱스가 새 비디오 수보다 작은지
		TF1 = [i < newVideoNum for i in range(3)]
		# 2. 중복 체크 조건: 링크가 이미 저장된 비디오에 없는지(실제로 사용자에게 보낸적 없는 영상인지 확인하는 용도)
		TF2 = [video.video_link not in self.youtubeData.loc[self.youtubeChannelID, "oldVideo"].values() 
			for video in batch.videos[:3]]
			
		# 조건에 따라 실제 새 비디오 수 결정
		if all(TF1) and all(TF2):
			newVideo = 3
		elif all(TF1[:2]) and all(TF2[:2]):
			newVideo = 2
		elif TF1[0] and TF2[0] and newVideoNum == 1:
			newVideo = 1
		else:
			newVideo = 0
		return newVideo

	# 유튜브 비디오 정보를 가져오는 함수
	async def getYoutubeVars(self, response, num) -> YouTubeVideo:
		# 제목 가져오기 및 정제
		title = subjectReplace(response['items'][num]['snippet']['title'])
		# 썸네일 URL (고화질 버전으로 시도)
		thumbnail = response['items'][num]['snippet']['thumbnails']["medium"]["url"].replace("mqdefault", "maxresdefault")
		
		# 썸네일 URL 유효성 체크 (404 에러 시 다른 해상도 시도)
		async with aiohttp.ClientSession() as session:
			for i in range(10):
				if i == 4:
					# 다섯 번째 시도에서 표준 해상도로 변경
					thumbnail = response['items'][num]['snippet']['thumbnails']["medium"]["url"].replace("mqdefault", "sddefault")
				elif i == 9:
					# 마지막 시도에서 원본 URL 사용
					thumbnail = response['items'][num]['snippet']['thumbnails']["medium"]["url"]
					
				async with session.get(thumbnail) as resp:
					if resp.status != 404:
						break  # 유효한 URL 찾음
					await asyncio.sleep(0.05)  # 짧은 대기 후 재시도
		
		# 기타 정보 가져오기
		channelName = response['items'][num]['snippet']['channelTitle']
		publish_time = response['items'][num]['snippet']['publishTime']
		video_id = response['items'][num]['id']['videoId']
		video_link = f"https://www.youtube.com/watch?v={video_id}"
		
		# YouTubeVideo 객체 반환
		return YouTubeVideo(
			video_title=title,
			thumbnail_link=thumbnail,
			publish_time=publish_time,
			video_link=video_link
		)
	
	# 비디오 설명을 가져오는 함수
	async def getDescription(self, video_id: str) -> str:
		try:
			# YouTube API 클라이언트 생성
			youtube = build(
				'youtube', 
				'v3', 
				developerKey=self.developerKey, 
				cache_discovery=False
			)
			
			# 비디오 상세 정보 요청
			result = await asyncio.wait_for(
				asyncio.get_running_loop().run_in_executor(
					None,
					lambda: youtube.videos().list(
						part='snippet',
						id=video_id
					).execute()
				),
				timeout=5  # 5초 타임아웃
			)
			
			# 결과가 없으면 빈 문자열 반환
			if not result.get('items'):
				return ""
				
			# 설명의 첫 줄만 추출하여 반환
			description = result['items'][0]['snippet']['description']
			return subjectReplace(description.split('\n')[0])
			
		except Exception as e:
			asyncio.create_task(log_error(f"error youtube getDescription {e}"))
			return ""

	# 사용자 데이터(채널 이름, 프로필 이미지)를 가져오는 함수
	def get_user_data(self):
		channelID = self.youtubeData.loc[self.youtubeChannelID, "channelID"]
		
		# 플랫폼별 ID 리스트를 딕셔너리로 관리
		platform_lists = {
			'chzzk': self.chzzkIDList,
			'afreeca': self.afreecaIDList,
			'twitch': self.twitchIDList
		}
		
		# 각 플랫폼에서 채널 정보 찾기
		username = None
		avatar_url = None
		for platform_list in platform_lists.values():
			try:
				username = platform_list.loc[channelID, 'channelName']
				avatar_url = platform_list.loc[channelID, 'profile_image']
				break  # 정보를 찾으면 반복 중단
			except Exception as e:
				continue
				
		# 채널 정보를 찾지 못한 경우 로그 기록
		if username is None or avatar_url is None:
			asyncio.create_task(log_error(f"Channel information not found for channelID: {channelID}"))

		return username, avatar_url

	# 유튜브 웹훅 JSON 데이터를 생성하는 함수
	def getYoutubeJson(self, video) -> dict:
		# 사용자 데이터 가져오기
		username, avatar_url = self.get_user_data()
		youtube_data = self.youtubeData.loc[self.youtubeChannelID]
		
		# 디스코드 웹훅 JSON 데이터 생성
		return {
			"username": f" [유튜브 알림] {username}",
			"avatar_url": avatar_url,
			"embeds": [{
				"color": 16711680,  # 빨간색 (유튜브 색상)
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

	# 채널 목록에서 특정 ID의 인덱스를 찾는 함수
	def get_index(self, channel_list, target_id):
			return {id: idx for idx, id in enumerate(channel_list)}[target_id]
	
	# 채널 썸네일 이미지 확인 및 가져오기 
	async def get_youtube_thumbnail_url(self):
		# 유튜브 채널 페이지 요청
		response = await get_message("youtube", f"https://www.youtube.com/@{self.youtubeChannelID}")
		if not response:
			asyncio.create_task(log_error(f"error Youtube get_youtube_thumbnail_url.{self.youtubeChannelID}:"))
			return
			
		# HTML에서 썸네일 URL 추출
		start_idx = response.find("https://yt3.googleusercontent.com")
		end_str = "no-rj"
		end_idx = response[start_idx:].find(end_str)
		thumbnail_url = response[start_idx:start_idx + end_idx + len(end_str)]
		
		# 추출된 URL이 유효한지 길이로 확인 (경험적 검증)
		if 110 < len(thumbnail_url) < 150:
			self.youtubeData.loc[self.youtubeChannelID, 'thumbnail_link'] = thumbnail_url