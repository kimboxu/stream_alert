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
	# 초기화 클래스: 프로그램의 기본 설정값과 상태를 관리함
	load_dotenv()
	DO_TEST = False
	
	printCount 		= 100	# 100회마다 카운트 출력
	countTimeList = []
	countTimeList.append(default_timer())	# 실행 시간 측정용
	countTimeList.append(default_timer())
	SEC 			= 1000000  # 까지만 표시(넘어서면 0부터)
	count 			= 0
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])  # Supabase DB 클라이언트

	logging.getLogger('httpx').setLevel(logging.WARNING)  # httpx 로깅 수준 조정

	# 모든 로거의 레벨을 높이려면
	# logging.getLogger().setLevel(logging.WARNING)
	print("start!")

# 각 플랫폼의 아이콘 URL을 저장하는 데이터 클래스
@dataclass
class iconLinkData:
	
	chzzk_icon: str = environ['CHZZK_ICON']
	afreeca_icon: str = environ['AFREECA_ICON']
	soop_icon: str = environ['SOOP_ICON']
	black_img: str = environ['BLACK_IMG']
	youtube_icon: str = environ['YOUTUBE_ICON']
	cafe_icon: str = environ['CAFE_ICON']

## 오류 로깅 함수: Discord 웹훅을 통해 오류 메시지 전송
async def log_error(message, webhook_url = environ.get('errorPostBotURL')):
    await DiscordWebhookSender._log_error(message, webhook_url)

# 사용자 데이터 업데이트 함수
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
			tasks.append(DataBaseVars(init))
			
		# 모든 작업 기다리기
		if tasks:
			await asyncio.gather(*tasks)

	except Exception as e:
		error_details = f"Error in userDataVar: {str(e)}"
		if hasattr(e, 'response'):
			error_details += f"\nResponse: {e.response.text}"
		
		if "EOF occurred in violation of protocol" in str(e):
			error_details += "\nSSL connection error occurred"
			
		asyncio.create_task(log_error(error_details))

## 사용자 상태 데이터 로드
async def load_user_state_data(init: initVar):
	userStateData = await asyncio.to_thread(
		lambda: init.supabase.table('userStateData').select("*").execute()
	)
	init.userStateData = make_list_to_dict(userStateData.data)
	init.userStateData.index = list(init.userStateData['discordURL'])
	
	# 플래그 업데이트
	await update_flag('user_date', False)

# 비동기로 플래그 업데이트
async def update_flag(field, value):
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	await asyncio.to_thread(
		lambda: supabase.table('date_update').upsert({
			"idx": 0,
			field: value
		}).execute()
	)

## db 초기화 함수
async def DataBaseVars(init: initVar):
	
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
			asyncio.create_task(log_error((f"Error in DataBaseVars: {e}")))
			if init.count != 0: break
			await asyncio.sleep(0.1)

# db에서 데이터 가져오는 함수
async def fetch_data(supabase, date_name):
	return supabase.table(date_name).select("*").execute()

# 리스트를 딕셔너리로 변환하는 함수
def make_list_to_dict(data):
	if not data:
		return pd.DataFrame()
		
	# Dictionary comprehension을 사용하여 더 간단하게 표현
	return pd.DataFrame({
		key: [item[key] for item in data]
		for key in data[0].keys()
	})

# 카운트 증가 및 주기적 출력 함수
def fCount(init: initVar): 
	if init.count >= init.SEC:
		init.count = 0

	if init.count % init.printCount == 0: 
		printCount(init)
	init.count += 1

## 스레드 수행 시간 조절 함수(너무 빨리 돌지 않게 하기 위해)
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

# 온라인 채널이 있는지 여부 확인하는 함수
def get_online_count(data, id_column="channelID"):
	return sum(1 for channel_id in data[id_column] if data.loc[channel_id, "live_state"] == "OPEN")

# 각 플랫폼의 온라인 카운트 계산
def printCount(init: initVar):
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

# HTML 엔티티를 일반 문자로 변환하는 함수
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

# 트위치 API 요청용 헤더 생성 함수(트위치 관련 기능들은 전부 현재는 사용 안함)
def getTwitchHeaders(): 
	twitch_Client_ID = environ['twitch_Client_ID']
	twitch_Client_secret = environ['twitch_Client_secret']

	oauth_key = post(	"https://id.twitch.tv/oauth2/token?client_id=" +
						twitch_Client_ID + "&client_secret=" +
						twitch_Client_secret +
						"&grant_type=client_credentials")
	authorization = 'Bearer ' + loads(oauth_key.text)["access_token"]
	return {'client-id': twitch_Client_ID, 'Authorization': authorization} # 헤더 반환

# 기본 HTTP 요청 헤더 반환
def getDefaultHeaders(): 
	return {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}

# 치지직 사이트 접속용 쿠키 반환
def getChzzkCookie(): 
	return {'NID_AUT': environ['NID_AUT'],'NID_SES':environ['NID_SES']} 

# 카페 검색 파라미터 설정 함수
def cafe_params(cafeNum, page_num):
	return {
			'search.queryType': 'lastArticle',
			'ad': 'False',
			'search.clubid': str(cafeNum),
			'search.page': str(page_num)
		}

# ISO 시간을 UTC로 변환하는 함수 (한국시간 -9시간)
def changeUTCtime(time_str):
    time = datetime.fromisoformat(time_str)
    time -= timedelta(hours=9)
    return time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

# 지정된 시간 이후인지 확인하는 함수 (기본 300초/5분)
def if_after_time(time_str, sec=300):  
	try:
		time = datetime.fromisoformat(time_str) + timedelta(seconds=sec)
		return time <= datetime.now()
	except Exception as e: 
		return time <= datetime.now().astimezone()

# 치지직 API URL 생성 함수
def chzzk_getLink(uid: str): 
	return f"https://api.chzzk.naver.com/service/v2/channels/{uid}/live-detail"

# 아프리카 API URL 생성 함수
def afreeca_getLink(afreeca_id: str): 
	return f"https://chapi.sooplive.co.kr/api/{afreeca_id}/station"

# 플랫폼별 API 요청 처리 함수
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
			headers = getTwitchHeaders()  # 트위치 인증 헤더
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
				BASE_URL, cafe_num = [*link.split(",")]  # 링크에서 카페 번호 추출
				formatted_url = config["url_formatter"](BASE_URL, cafe_num)
			else:
				formatted_url = config["url_formatter"]
		
		# 파라미터가 필요한 경우 추가
		if config["needs_params"]:
			if platform == "cafe":
				page_num = 1  # 기본값
				cafe_num = link.split(",")[-1]  # 링크에서 카페 번호 추출
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
					if retry_count >= max_retries: asyncio.create_task(log_error(f"{error_msg} (시도 {retry_count+1}/{max_retries})"))
					
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
				if retry_count >= max_retries: asyncio.create_task(log_error(error_msg))
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
				if retry_count >= max_retries: asyncio.create_task(log_error(error_msg))
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
				asyncio.create_task(log_error(error_msg))
				return {}
		
	except Exception as e:
		error_msg = f"error get_message2: {platform} - {str(e)}"
		asyncio.create_task(log_error(error_msg))
		return {}

# 트위치 채널 상태 데이터 추출 함수
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
		asyncio.create_task(log_error(f"error getChannelOffStateData twitch {e}"))
		return None, None, None

# 치지직 채널 상태 데이터 추출 함수
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
		asyncio.create_task(log_error(f"error getChannelOffStateData chzzk {e}"))
		return None, None, profile_image

# 아프리카 채널 상태 데이터 추출 함수
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
		asyncio.create_task(log_error(f"error getChannelOffStateData afreeca {e}"))

# 방송 정보 데이터 저장 함수
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

	for _ in range(3):  # 최대 3번 시도
		try:
			supabase.table(table_name).upsert(data_func).execute()
			break
		except Exception as e:
			asyncio.create_task(log_error(f"error saving profile data {e}"))
			await asyncio.sleep(0.1)

# 프로필 이미지 url 저장 함수
async def save_profile_data(IDList, platform: str, id):
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	table_name = platform + "IDList"
	data_func = {
			"channelID": id,
			'profile_image': IDList.loc[id, 'profile_image']
		}

	for _ in range(3):  # 최대 3번 시도
		try:
			supabase.table(table_name).upsert(data_func).execute()
			break
		except Exception as e:
			asyncio.create_task(log_error(f"error saving profile data {e}"))
			await asyncio.sleep(0.1)

# 채팅 연결 상태 변경 함수
async def change_chat_join_state(chat_json, channel_id, chat_rejoin = True):
	chat_json[channel_id] = chat_rejoin
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	for _ in range(3):  # 최대 3번 시도
		try:
			supabase.table('date_update').upsert({"idx": 0, "chat_json": chat_json}).execute()
			break
		except Exception as e:
			asyncio.create_task(log_error(f"echange_chat_join_state {e}"))
			await asyncio.sleep(0.1)
	
# 치지직 비디오 데이터 저장 함수
async def chzzk_saveVideoData(chzzk_video, _id): 
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	data = {
		"channelID": _id,
		'VOD_json': chzzk_video.loc[_id, 'VOD_json']
	}
	for _ in range(3):  # 최대 3번 시도
		try:
			supabase.table('chzzk_video').upsert(data).execute()
			break
		except Exception as e:
			asyncio.create_task(log_error(f"error saving profile data {e}"))
			await asyncio.sleep(0.1)

# 카페 데이터 저장 함수
async def saveCafeData(cafeData, _id):
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])

	data = {
		"channelID": _id,
		"update_time": int(cafeData.loc[_id, 'update_time']),
		"cafe_json": cafeData.loc[_id, 'cafe_json'],
		"cafeNameDict": cafeData.loc[_id, 'cafeNameDict']
	}	
		
	for _ in range(3):  # 최대 3번 시도
		try:
			supabase.table('cafeData').upsert(data).execute()
			break
		except Exception as e:
			asyncio.create_task(log_error(f"error save cafe time {e}"))
			await asyncio.sleep(0.1)

# 유튜브 데이터 저장 함수
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

	for _ in range(3):  # 최대 3번 시도
		try:
			supabase.table('youtubeData').upsert(data).execute()
			break
		except Exception as e:
			asyncio.create_task(log_error(f"error saving youtube data {e}"))
			await asyncio.sleep(0.1)

# 사용자 알림 데이터 저장 함수
async def save_user_notifications(supabase, webhook_url, notifications, last_db_save_time):
    for _ in range(3):  # 최대 3번 시도
        try:
            await asyncio.to_thread(
                lambda: supabase.table('userStateData')
                    .upsert({
                        'discordURL': webhook_url, 
                        'notifications': notifications,
                        'last_db_save_time': last_db_save_time
                    })
                    .execute()
            )
            print(f"{datetime.now()} 알림을 DB에 저장함 - URL: {webhook_url}")
            return True
        except Exception as e:
            print(f"{datetime.now()} 알림 저장 중 오류: {e} - URL: {webhook_url}")
            await asyncio.sleep(0.1)  # 잠시 대기 후 재시도
    
    return False  # 모든 시도 실패