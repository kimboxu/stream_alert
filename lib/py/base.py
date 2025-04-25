from os import environ
import logging
import asyncio
import aiohttp
from json import loads
from queue import Queue
import pandas as pd
from requests import post, get
from requests.exceptions import HTTPError, ReadTimeout, ConnectTimeout, SSLError
from http.client import RemoteDisconnected
from timeit import default_timer
from dataclasses import dataclass
from supabase import create_client
from datetime import datetime, timedelta
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from discord_webhook_sender import DiscordWebhookSender

class initVar:
	load_dotenv()
	DO_TEST = False
	
	printCount 		= 100	#every 100 count, print count 
	countTimeList = []
	countTimeList.append(default_timer())	#nomal sleep time
	countTimeList.append(default_timer())	#nomal sleep time
	SEC 			= 1000000  #every 100000 count rejoin
	count 			= 0
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])

	logging.getLogger('httpx').setLevel(logging.WARNING)
	# 모든 로거의 레벨을 높이려면 다음과 같이 할 수 있습니다:
	# logging.getLogger().setLevel(logging.WARNING)
	print("start!")

@dataclass
class iconLinkData:
	chzzk_icon: str = environ['CHZZK_ICON']
	afreeca_icon: str = environ['AFREECA_ICON']
	soop_icon: str = environ['SOOP_ICON']
	black_img: str = environ['BLACK_IMG']
	youtube_icon: str = environ['YOUTUBE_ICON']
	cafe_icon: str = environ['CAFE_ICON']

class AsyncLogger:
	def __init__(self, bot_url, max_workers=3):
		self.bot_url = bot_url
		self.log_queue = Queue()
		self.executor = ThreadPoolExecutor(max_workers=max_workers)
		self.loop = asyncio.get_event_loop()
		self._stop_event = asyncio.Event()

	async def start_logging(self):
		"""로깅 프로세스 시작"""
		self._stop_event.clear()
		await self.loop.run_in_executor(
			self.executor, 
			self._process_log_queue
		)

	def _process_log_queue(self):
		"""백그라운드 스레드에서 로그 큐 처리"""
		while not self._stop_event.is_set():
			try:
				# 0.1초마다 큐 확인
				if not self.log_queue.empty():
					message = self.log_queue.get(timeout=0.1)
					asyncio.run(self._send_log(message))
			except Exception as e:
				print(f"Logging queue processing error: {e}")

	async def _send_log(self, message):
		"""로그 메시지 비동기 전송"""
		max_retries = 3
		for attempt in range(max_retries):
			try:
				async with aiohttp.ClientSession() as session:
					data = {'content': message, "username": "error alarm"}
					async with session.post(
						self.bot_url, 
						json=data, 
						timeout=aiohttp.ClientTimeout(total=5)
					) as response:
						if response.status == 429:
							retry_after = float(response.headers.get('Retry-After', 1))
							await asyncio.sleep(retry_after)
							continue
						return
			except Exception as e:
				print(f"Log sending attempt {attempt + 1} failed: {e}")
				await asyncio.sleep(0.5 * (2 ** attempt))

	def enqueue_log(self, message):
		"""로그 메시지 큐에 추가"""
		self.log_queue.put(message)

	async def stop(self):
		"""로깅 프로세스 정지"""
		self._stop_event.set()
		self.executor.shutdown(wait=True)

async def userDataVar(init: initVar):
	try:
		
		# 1. 업데이트 정보 가져오기
		date_update = await asyncio.to_thread(
			lambda: init.supabase.table('date_update').select("*").execute()
		)
		update_data = date_update.data[0]

		# 단순 속성 설정
		for attr, value in {
			'youtube_TF': update_data['youtube_TF'],
			'chat_json': update_data['chat_json']
		}.items():
			setattr(init, attr, value)

		# 병렬로 필요한 데이터 로드
		tasks = []
		
		if update_data['user_date']:
			tasks.append(load_user_state_data(init))
			
		if update_data['all_date']:
			tasks.append(discordBotDataVars(init))
			
		# 모든 작업 기다리기
		if tasks:
			await asyncio.gather(*tasks)

	except Exception as e:
		error_details = f"Error in userDataVar: {str(e)}"
		if hasattr(e, 'response'):
			error_details += f"\nResponse: {e.response.text}"
		
		if "EOF occurred in violation of protocol" in str(e):
			error_details += "\nSSL connection error occurred"
			
		asyncio.create_task(DiscordWebhookSender._log_error(error_details))

async def load_user_state_data(init: initVar):
	# 사용자 상태 데이터 로드
	userStateData = await asyncio.to_thread(
		lambda: init.supabase.table('userStateData').select("*").execute()
	)
	init.userStateData = make_list_to_dict(userStateData.data)
	init.userStateData.index = list(init.userStateData['discordURL'])
	
	# 플래그 업데이트
	await update_flag('user_date', False)

async def update_flag(field, value):
	# 비동기로 플래그 업데이트
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	await asyncio.to_thread(
		lambda: supabase.table('date_update').upsert({
			"idx": 0,
			field: value
		}).execute()
	)

# async def cached_query(supabase, table, query_func, cache_key, ttl=60):
# 	# 메모리 캐시 초기화
# 	_cache = {}
# 	_cache_expiry = {}
# 	"""캐싱 메커니즘이 있는 쿼리 실행"""
# 	now = datetime.now()
	
# 	# 캐시가 유효한지 확인
# 	if cache_key in _cache and _cache_expiry[cache_key] > now:
# 		return _cache[cache_key]
	
# 	# 캐시가 없거나 만료된 경우 쿼리 실행
# 	result = await asyncio.to_thread(query_func)
	
# 	# 결과 캐싱
# 	_cache[cache_key] = result
# 	_cache_expiry[cache_key] = now + ttl
	
# 	return result

async def discordBotDataVars(init: initVar):
	while True:
		try:
			
			# 모든 테이블 이름을 리스트로 정의
			table_names = [
				'userStateData', 'twitch_titleData', 'chzzk_titleData', 
				'afreeca_titleData', 'twitchIDList', 'chzzkIDList', 
				'afreecaIDList', 'youtubeData', 'twitch_chatFilter',
				'chzzk_chatFilter', 'afreeca_chatFilter', 'chzzk_video', 
				'cafeData'
			]
			
			# 모든 테이블의 데이터를 비동기로 가져오기
			tasks = [fetch_data(init.supabase, name) for name in table_names]
			results = await asyncio.gather(*tasks)
			
			# 결과를 딕셔너리로 변환
			data_dict = {name: make_list_to_dict(result.data)
						for name, result in zip(table_names, results)}
			
			# init 객체에 데이터 할당
			for name, data in data_dict.items():
				setattr(init, name, data)
			
			# index 설정
			index_mappings = {
				'userStateData': 'discordURL',
				'twitchIDList': 'channelID',
				'chzzkIDList': 'channelID',
				'afreecaIDList': 'channelID',
				'twitch_titleData': 'channelID',
				'chzzk_titleData': 'channelID',
				'afreeca_titleData': 'channelID',
				'youtubeData': 'YoutubeChannelID',
				'afreeca_chatFilter': 'channelID',
				'cafeData': 'channelID',
				'chzzk_video': 'channelID'
			}
			
			for table_name, index_col in index_mappings.items():
				data = getattr(init, table_name)
				data.index = list(data[index_col])

			await update_flag('all_date', False)

			break
			
		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error((f"Error in discordBotDataVars: {e}")))
			if init.count != 0: break
			await asyncio.sleep(0.1)

async def fetch_data(supabase, date_name):
	return supabase.table(date_name).select("*").execute()

def make_list_to_dict(data):
	if not data:
		return pd.DataFrame()
		
	# Dictionary comprehension을 사용하여 더 간단하게 표현
	return pd.DataFrame({
		key: [item[key] for item in data]
		for key in data[0].keys()
	})

def fCount(init: initVar): #function to count
	if init.count >= init.SEC:
		init.count = 0

	if init.count % init.printCount == 0: 
		printCount(init)
	init.count += 1

async def fSleep(init: initVar):
	current_time = default_timer()
	init.countTimeList.append(current_time)
	
	# 리스트 길이 관리를 더 효율적으로 수정
	if len(init.countTimeList) > (init.printCount + 1):
		init.countTimeList.pop(0)
	
	# 시간 차이 계산 및 sleep 시간 결정
	time_diff = current_time - init.countTimeList[-2]
	sleepTime = max(0.01, min(1.00, 1.00 - time_diff))
	
	await asyncio.sleep(sleepTime)
	init.countTimeList[-1] += sleepTime

def get_online_count(data, id_column="channelID"):
	return sum(1 for channel_id in data[id_column] if data.loc[channel_id, "live_state"] == "OPEN")

def printCount(init: initVar):
	# 각 플랫폼의 온라인 카운트 계산
	online_counts = {
		'twitch': get_online_count(init.twitch_titleData),
		'chzzk': get_online_count(init.chzzk_titleData),
		'afreeca': get_online_count(init.afreeca_titleData)
	}
	
	# 모든 플랫폼이 오프라인인지 확인
	all_offline = not any(online_counts.values())
	
	# 시간 관련 데이터 계산
	current_time = datetime.now()
	count = str(init.count).zfill(len(str(init.SEC)))
	elapsed_time = round(init.countTimeList[-1] - init.countTimeList[0], 3)
	
	# 결과 출력
	status_prefix = "All offLine, " if all_offline else ""
	print(f"{status_prefix}{current_time} count {count} TIME {elapsed_time:.1f} SEC")

def subjectReplace(subject: str) -> str:
	replacements = {
		'&lt;': '<',
		'&gt;': '>',
		'&amp;': '&',
		'&quot;': '"',
		'&#035;': '#',
		'&#35;': '#',
		'&#039;': "'",
		'&#39;': "'"
	}
	
	for old, new in replacements.items():
		subject = subject.replace(old, new)
	
	return subject

def getTwitchHeaders(): 
	twitch_Client_ID = environ['twitch_Client_ID']
	twitch_Client_secret = environ['twitch_Client_secret']

	oauth_key = post(	"https://id.twitch.tv/oauth2/token?client_id=" +
						twitch_Client_ID + "&client_secret=" +
						twitch_Client_secret +
						"&grant_type=client_credentials")
	authorization = 'Bearer ' + loads(oauth_key.text)["access_token"]
	return {'client-id': twitch_Client_ID, 'Authorization': authorization} #get headers 
def getDefaultHeaders(): return {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'} #get headers 
def getChzzkCookie(): return {'NID_AUT': environ['NID_AUT'],'NID_SES':environ['NID_SES']} 
def cafe_params(cafeNum, page_num):
	return {
			'search.queryType': 'lastArticle',
			'ad': 'False',
			'search.clubid': str(cafeNum),
			'search.page': str(page_num)
		}

# async def should_terminate(sock, ID):
# 	try:
# 		await asyncio.sleep(300)  # 5분 대기
		
# 		if not sock.closed:
# 			await sock.close()
# 		print(f"{datetime.now()} {ID}: 방송 종료 5분 경과, 연결 종료")
		
# 	except asyncio.CancelledError:
# 		# 태스크가 취소된 경우 정상적으로 종료
# 		raise
# 	except Exception as e:
# 		print(f"{datetime.now()} error should_terminate {e}")
	
# 	return "CLOSE"

def changeUTCtime(time_str):
    time = datetime.fromisoformat(time_str)
    time -= timedelta(hours=9)
    return time.isoformat()

def changeGMTtime(time_str):
    time = datetime.fromisoformat(time_str)
    time += timedelta(hours=9)
    return time.isoformat()

def if_after_time(time_str, sec=300):  # 지금 시간이 이전 시간보다 SEC초 만큼 지났는지 확인
    time = datetime.fromisoformat(time_str) + timedelta(seconds=sec)
    return time <= datetime.now()

# async def timer(time): 
# 	await asyncio.sleep(time)  # time 초 대기
# 	return "CLOSE"

def chzzk_getLink(uid: str): 
	return f"https://api.chzzk.naver.com/service/v2/channels/{uid}/live-detail"

def afreeca_getLink(afreeca_id: str): 
	return f"https://chapi.sooplive.co.kr/api/{afreeca_id}/station"

async def get_message(platform, link):
	# 미리 정의된 플랫폼별 API 요청 구성
	platform_config = {
		"afreeca": {
			"needs_cookies": False,
			"needs_params": False,
			"url_formatter": link,
			"response_handler": lambda response: loads(response.text)
		},
		"chzzk": {
			"needs_cookies": True,
			"needs_params": True,
			"url_formatter": link,
			"response_handler": lambda response: loads(response.text)
		},
		"twitch": {
			"needs_cookies": False,
			"needs_params": False,
			"url_formatter": link,
			"response_handler": lambda response: loads(response.text)
		},
		"cafe": {
			"needs_cookies": False,
			"needs_params": True,
			"url_formatter": lambda link, cafe_num: link,
			"response_handler": lambda response: loads(response.text)
		},
		"youtube": {
			"needs_cookies": False,
			"needs_params": False,
			"url_formatter": link,
			"response_handler": lambda response: response.text
		},
	}
	
	try:
		config = platform_config.get(platform)
		if not config:
			raise ValueError(f"지원하지 않는 플랫폼입니다: {platform}")
		
		# 기본 헤더 및 요청 설정
		headers = {}
		request_kwargs = {
			"timeout": 10  # 타임아웃 시간 증가 (3초 → 10초)
		}
		
		# 플랫폼별 헤더 설정
		if platform == "chzzk":
			headers = getDefaultHeaders()
		elif platform == "twitch":
			headers = getTwitchHeaders()  # 트위치 인증 헤더 (별도 구현 필요)
		else:
			headers = getDefaultHeaders()
			
		
		request_kwargs["headers"] = headers
		
		# 쿠키가 필요한 경우 추가
		if config["needs_cookies"]:
			if platform == "chzzk":
				request_kwargs["cookies"] = getChzzkCookie()

		
		# URL 형식 처리
		formatted_url = link
		if "url_formatter" in config:
			if platform == "cafe":
				BASE_URL, cafe_num = [*link.split(",")]  # 링크에서 카페 번호 추출 (가정)
				formatted_url = config["url_formatter"](BASE_URL, cafe_num)
			else:
				formatted_url = config["url_formatter"]
		
		# 파라미터가 필요한 경우 추가
		if config["needs_params"]:
			if platform == "cafe":
				page_num = 1  # 기본값 또는 파라미터로 전달 가능
				cafe_num = link.split(",")[-1]  # 링크에서 카페 번호 추출 (가정)
				request_kwargs["params"] = cafe_params(cafe_num, page_num)
			elif platform == "chzzk":
				# 치지직 파라미터 설정 (필요시)
				pass
		
		# 재시도 설정
		max_retries = 3
		retry_count = 0
		retry_delay = 2  # 초 단위
		
		# 재시도 메커니즘 구현
		while retry_count < max_retries:
			try:
				# API 요청 실행
				response = await asyncio.to_thread(
					get,
					formatted_url,
					**request_kwargs
				)
				
				# 응답 코드 확인
				if response.status_code != 200:
					error_msg = f"API 요청 실패: {response.status_code} - {platform}, {formatted_url}"
					# 에러 로깅은 유지하되 재시도 수행
					if retry_count >= max_retries: asyncio.create_task(DiscordWebhookSender._log_error(f"{error_msg} (시도 {retry_count+1}/{max_retries})"))
					
					# 서버 오류(5xx)의 경우만 재시도
					if 500 <= response.status_code < 600:
						retry_count += 1
						if retry_count < max_retries:
							await asyncio.sleep(retry_delay)
							# 재시도 간격을 지수적으로 증가 (지수 백오프)
							retry_delay *= 2
							continue
						else:
							return {}
					else:
						# 4xx 등의 클라이언트 오류는 재시도하지 않고 바로 종료
						return {}
				
				# 성공적인 응답을 받았으므로 처리 후 반환
				return config["response_handler"](response)
				
			except (ConnectTimeout, ReadTimeout, ConnectionError, HTTPError, RemoteDisconnected) as e:
				# 연결 관련 예외 발생 시 재시도
				retry_count += 1
				error_type = type(e).__name__
				error_msg = f"API 요청 타임아웃/연결 오류 (시도 {retry_count}/{max_retries}): {platform} - {error_type}: {str(e)}"
				if retry_count >= max_retries: asyncio.create_task(DiscordWebhookSender._log_error(error_msg))
				# else: print(error_msg)

				# 연결 종료 에러의 경우 추가 대기 시간 부여
				if "RemoteDisconnected" in error_type or "Connection aborted" in str(e):
					await asyncio.sleep(retry_delay * 1.5)  # 일반 재시도보다 더 길게 대기
				else:
					await asyncio.sleep(retry_delay)
				
				retry_delay *= 2

				if retry_count >= max_retries:
					return {}
				
			except SSLError as ssl_err:
				retry_count += 1
				error_msg = f"SSL Error (시도 {retry_count}/{max_retries}): {platform} - {str(ssl_err)}"
				if retry_count >= max_retries: asyncio.create_task(DiscordWebhookSender._log_error(error_msg))
				# else: print(error_msg)
				
				if retry_count < max_retries:
					if 'requests_kwargs' in locals() and 'verify' in request_kwargs:
						request_kwargs['verify'] = not request_kwargs['verify']
					await asyncio.sleep(retry_delay)
					retry_delay *= 2
				else:
					return {}
			
			except Exception as e:
				# 기타 예외는 바로 반환
				error_msg = f"error get_message: {platform} - {str(e)}"
				asyncio.create_task(DiscordWebhookSender._log_error(error_msg))
				return {}
		
	except Exception as e:
		error_msg = f"error get_message2: {platform} - {str(e)}"
		asyncio.create_task(DiscordWebhookSender._log_error(error_msg))
		return {}
	
def twitch_getChannelOffStateData(offStateList, twitchID):
	try:
		for offState in offStateList:
			if offState["broadcaster_login"] == twitchID:
				return (
					offState["is_live"],
					offState["title"],
					offState["thumbnail_url"]
				)
		return None, None, None
	except Exception as e:
		asyncio.create_task(DiscordWebhookSender._log_error(f"error getChannelOffStateData twitch {e}"))
		return None, None, None

def chzzk_getChannelOffStateData(stateData, chzzkID, profile_image = ""):
	try:
		if stateData["channel"]["channelId"]==chzzkID:
			return (
				stateData["status"],
				stateData["liveTitle"],
				stateData["channel"]["channelImageUrl"]
			)
		return None, None, profile_image
	except Exception as e: 
		asyncio.create_task(DiscordWebhookSender._log_error(f"error getChannelOffStateData chzzk {e}"))
		return None, None, profile_image

def afreeca_getChannelOffStateData(stateData, afreeca_id, profile_image = ""):
	try:
		if stateData["station"]["user_id"] == afreeca_id: 
			live = int(stateData["broad"] is not None)
			title = stateData["broad"]["broad_title"] if live else None
			profile_image = stateData["profile_image"]
			if profile_image.startswith("//"):
				profile_image = f"https:{profile_image}"
			return live, title, profile_image
		return None, None, profile_image
	except Exception as e: 
		asyncio.create_task(DiscordWebhookSender._log_error(f"error getChannelOffStateData afreeca {e}"))

async def save_airing_data(titleData, platform: str, id_):
	
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	table_name = platform + "_titleData"
	data_func = {
				"channelID": id_,
				"live_state": titleData.loc[id_, "live_state"],
				"title1": titleData.loc[id_, "title1"],
				"title2": titleData.loc[id_, "title2"],
				"update_time": titleData.loc[id_, "update_time"],
				"chatChannelId": titleData.loc[id_, "chatChannelId"],
				"oldChatChannelId": titleData.loc[id_, "oldChatChannelId"],
				"state_update_time": titleData.loc[id_, "state_update_time"],
		}

	for _ in range(3):
		try:
			supabase.table(table_name).upsert(data_func).execute()
			break
		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error(f"error saving profile data {e}"))
			await asyncio.sleep(0.1)

async def save_profile_data(IDList, platform: str, id):
	# Platform specific configurations

	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	table_name = platform + "IDList"
	data_func = {
			"channelID": id,
			'profile_image': IDList.loc[id, 'profile_image']
		}

	for _ in range(3):
		try:
			supabase.table(table_name).upsert(data_func).execute()
			break
		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error(f"error saving profile data {e}"))
			await asyncio.sleep(0.1)

async def change_chat_join_state(chat_json, channel_id, chat_rejoin = True):
	chat_json[channel_id] = chat_rejoin
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	for _ in range(3):
		try:
			supabase.table('date_update').upsert({"idx": 0, "chat_json": chat_json}).execute()
			break
		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error(f"echange_chat_join_state {e}"))
			await asyncio.sleep(0.1)
	
async def chzzk_saveVideoData(chzzk_video, _id): #save profile data
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	data = {
		"channelID": _id,
		'VOD_json': chzzk_video.loc[_id, 'VOD_json']
	}
	for _ in range(3):
		try:
			supabase.table('chzzk_video').upsert(data).execute()
			break
		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error(f"error saving profile data {e}"))
			await asyncio.sleep(0.1)

async def saveCafeData(cafeData, _id):
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])

	cafe_data = {
		"channelID": _id,
		"update_time": int(cafeData.loc[_id, 'update_time']),
		"cafe_json": cafeData.loc[_id, 'cafe_json'],
		"cafeNameDict": cafeData.loc[_id, 'cafeNameDict']
	}	
		
	for _ in range(3):
		try:
			supabase.table('cafeData').upsert(cafe_data).execute()
			break
		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error(f"error save cafe time {e}"))
			await asyncio.sleep(0.1)

async def saveYoutubeData(youtubeData, youtubeChannelID):
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	data = {
		"YoutubeChannelID": youtubeChannelID,
		"videoCount": int(youtubeData.loc[youtubeChannelID, "videoCount"]),
		"uploadTime": youtubeData.loc[youtubeChannelID, "uploadTime"],
		"oldVideo": youtubeData.loc[youtubeChannelID, "oldVideo"],
		'thumbnail_link': youtubeData.loc[youtubeChannelID, 'thumbnail_link'],
		'video_count_check': int(youtubeData.loc[youtubeChannelID, "video_count_check"]),
	}

	for _ in range(3):
		try:
			supabase.table('youtubeData').upsert(data).execute()
			break
		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error(f"error saving youtube data {e}"))
			await asyncio.sleep(0.1)

async def saveNotificationsData(supabase, discord_webhook_url, user_data, notification_id, data_fields):
    try:
        # 기존 알림 목록 가져오기
        notifications = user_data.get('notifications', [])
        if not isinstance(notifications, list):
            try:
                notifications = loads(notifications)
            except:
                notifications = []
        
        # id 확인 - 이미 있는 알림인지 체크
        is_duplicate = False
        for idx, notification in enumerate(notifications):
            # 동일한 ID의 알림이 있는지 확인
            if notification.get('id') == notification_id:
                # 중복 발견 - 기존 항목 업데이트
                notifications[idx] = data_fields
                is_duplicate = True
                break
                
        if not is_duplicate:
            # 새 알림 추가
            notifications.append(data_fields)
            
        # 최대 10000개까지만 유지 (오래된 알림 삭제)
        if len(notifications) > 10000:
            notifications = notifications[-10000:]
        
        # DB 업데이트 (배치 작업의 일부)
        supabase.table('userStateData').update({
            'notifications': notifications
        }).eq('discordURL', discord_webhook_url).execute()

    except Exception as e:
        print(f"알림 데이터 저장 중 오류: {e}")