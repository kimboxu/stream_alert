from os import environ
import logging
import asyncio
import aiohttp
from json import loads
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
from make_log_api_performance import PerformanceManager

import google.generativeai as genai

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

	stream_status = {}
	highlight_chat = {}
	system_instruction = '''
		방송 하이라이트 상세 분석 데이터를 바탕으로 VOD 타임라인 댓글을 생성해주세요.

		응답 형식:
		[
		{"comment_after_openDate": "VOD_타임라인_시간", "score_difference": "재미도 점수 차이","text": "댓글 내용", "description": "방송 썸네일을 포함한 상세 분석 댓글"}
		]

		분석 우선순위:
		1. 비슷한 의미·표현의 채팅은 하나의 그룹으로 묶어 대표적으로 해석	
		- 예: "ㅋㅋㅋ", "ㅋㅋㅋㅋ", "ㅋㅋㅋㅋㅋ" → 동일 반응 그룹
		- 예: "와 대박", "헐 대박", "대박ㅋㅋ" → 동일 반응 그룹
		- 반복·의미 유사 채팅은 합산하여 상황의 강도를 반영
		2. "최근 채팅" 내용으로 구체적 상황 파악 (게임, 행동, 사건)
		3. "하이라이트 이유"로 반응 유형 확인
		4. 점수 데이터로 상황의 특성 분석:
		- 채팅 급증 점수 높음 → 갑작스러운 사건
		- 리액션 점수 높음 → 강한 감정 반응
		- 시청자 급증 점수 높음 → 화제성 있는 순간
		- 다양성 점수 높음 → 다양한 시청자 참여

		댓글 작성 방식:
		1. 채팅 그룹에서 명확한 상황(게임명, 행동)이 보이면 구체적으로 표현
		2. 점수 패턴으로 상황의 성격 파악:
		- 리액션 점수 > 채팅 급증 점수 → 감정적 반응 중심
		- 채팅 급증 점수 > 리액션 점수 → 사건/상황 중심
		- 시청자 급증 있음 → 주목받는 순간
		3. "큰 하이라이트 여부"가 true면 더 임팩트 있게 표현
		4. 필드별 작성 규칙:
		- text: 채팅 그룹과 점수 데이터만으로 분석한 기본 댓글
		- description: 방송 썸네일이 있다면 이미지까지 분석하여 더 구체적이고 정확한 시청자 반응으로 작성. 썸네일이 없다면 채팅 그룹과 점수 데이터만으로 분석한 기본 댓글
		5. 모든 댓글은 실제 시청자 톤으로 20자 이내, 자연스럽게 작성

		**중요: text와 description 모두 실제 시청자가 쓴 댓글처럼 자연스럽고 짧게 작성해야 합니다.**
		
		예시:
		- 리액션 중심: "ㅋㅋㅋ 개웃김", "미친 반응 ㄷㄷ"
		- 상황 중심: "레전드 플레이", "데드락 일퀘 시작"
		- 화제성: "시청자들 몰려옴", "클립감 ㄷㄷ"
		- 썸네일 분석 예시:
		text: "섬광탄으로 어그로 끄는 중"
		description: "아서스 또 있네 ㅋㅋㅋ" (썸네일에서 특정 캐릭터 확인시)
	'''
	genai.configure(api_key=environ['GOOGLE_API_KEY'])
	model = genai.GenerativeModel("gemini-2.0-flash", system_instruction=system_instruction, generation_config={"response_mime_type": "application/json"})
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

# 오류 로깅 함수: Discord 웹훅을 통해 오류 메시지 전송
async def log_error(message, webhook_url = environ.get('errorPostBotURL')):
	await DiscordWebhookSender()._log_error(message, webhook_url)

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
			'is_youtube': update_data['is_youtube'],
			'chat_json': update_data['chat_json'],
			'is_vod_json': update_data['is_vod_json'],
			'is_vod_chat_json': update_data['is_vod_chat_json'],
			'is_hot_clip': update_data['is_hot_clip'],
		}.items():
			setattr(init, attr, value)

		# 병렬로 필요한 데이터 로드
		tasks = []
		
		if update_data['user_date']:
			tasks.append(load_user_state_data(init))
			
		if update_data['all_date']:
			tasks.append(DataBaseVars(init))

		if update_data['save_highlight_data']:
			asyncio.create_task(save_highlight_data(init))
			
		# 모든 작업 기다리기
		if tasks:
			await asyncio.gather(*tasks)

	except Exception as e:
		error_details = f"Error in userDataVar: {str(e)}"
		if "Server disconnected" in str(e):
			return 
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
				'chzzk_chatFilter', 'afreeca_chatFilter', 'video_data',
				'cafeData', 'hot_clip_data',
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
				'video_data': 'channelID',
				'hot_clip_data': 'channelID',
			}
			
			for table_name, index_col in index_mappings.items():
				data = getattr(init, table_name)
				if not data.empty:  # 데이터가 있을 때만 인덱스 설정
					data.index = list(data[index_col])

			await update_flag('all_date', False)

			break
			
		except Exception as e:
			asyncio.create_task(log_error((f"Error in DataBaseVars: {e}")))
			if init.count != 0: break
			await asyncio.sleep(0.1)

# 하이라이트 챗 캐시 데이터 저장 (메모리 관리), 프로그램 종료 직전에만 사용하기
async def save_highlight_data(init):
	# StateManager에서 init과 하이라이트 인스턴스들 가져오기
	from shared_state import StateManager
	state_manager = StateManager.get_instance()
	
	if not init:
		return {
			"status": "error",
			"message": "시스템 초기화가 완료되지 않았습니다."
		}

	save_results = {
		"processed_channels": [],
		"total_highlights_saved": 0,
		"errors": []
	}
	try:
		# StateManager에서 하이라이트가 있는 챗 인스턴스들 가져오기
		instances_with_highlights = state_manager.get_chat_instances_with_highlights()
		
		print(f"{datetime.now()} 하이라이트 데이터가 있는 채널 {len(instances_with_highlights)}개 발견")
		
		# 각 인스턴스에 대해 highlight_processing 실행
		for instance_info in instances_with_highlights:
			try:
				channel_id = instance_info['channel_id']
				channel_name = instance_info['channel_name']
				platform = instance_info['platform']
				highlights_count = instance_info['highlights_count']
				chat_instance = instance_info['instance']
				
				print(f"{datetime.now()} [{platform}] {channel_name}: {highlights_count}개 하이라이트 저장 중...")
				
				# highlight_processing 실행하여 하이라이트 저장
				await chat_instance.highlight_processing()
				
				save_results["processed_channels"].append({
					"channel_id": channel_id,
					"channel_name": channel_name,
					"platform": platform,
					"highlights_saved": highlights_count
				})
				save_results["total_highlights_saved"] += highlights_count
				
				print(f"{datetime.now()} [{platform}] {channel_name}: 하이라이트 저장 완료")
				
			except Exception as channel_error:
				error_msg = f"채널 {instance_info.get('channel_name', 'Unknown')} 처리 중 오류: {str(channel_error)}"
				save_results["errors"].append(error_msg)
				print(f"{datetime.now()} {error_msg}")
				continue
		
		# 결과 반환
		if save_results["total_highlights_saved"] > 0:
			print(f"{datetime.now()} 하이라이트 챗 캐시 데이터 저장 완료: 총 {save_results['total_highlights_saved']}개 하이라이트 저장")
			print(f"save_results:{save_results}")
		else:
			print(f"{datetime.now()} 저장할 하이라이트 데이터가 없습니다")

		await update_flag('save_highlight_data', False)
	
	except Exception as e:
		asyncio.create_task(log_error(f"하이라이트 데이터 저장 실패: {str(e)}"))
		await update_flag('save_highlight_data', False)

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

# 아프리카 사이트 접속용 쿠키 반환
def getAfreecaCookie(): 
	return {'AuthTicket':environ['AuthTicket'],} 

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
	
# 방송 세션을 구분하는 고유 ID 생성
def get_stream_start_id(channel_id: str, start_time: str) -> str:
	# start_time을 기반으로 고유한 스트림 ID 생성
	timestamp = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
	return f"{channel_id}_{timestamp.strftime('%Y%m%d_%H%M%S')}"

#스트림 ID에서 타임스탬프 추출
def get_timestamp_from_stream_id(stream_id: str) -> datetime:
    try:
        # stream_id 형식: "channelID_YYYYMMDD_HHMMSS"
        parts = stream_id.split('_')
        if len(parts) >= 3:
            date_part = parts[-2]  # YYYYMMDD
            time_part = parts[-1]  # HHMMSS
            time_str = f"{date_part}_{time_part}"
            return datetime.strptime(time_str, '%Y%m%d_%H%M%S')
        else:
            raise ValueError(f"Invalid stream_id format: {stream_id}")
    except (ValueError, IndexError) as e:
        raise ValueError(f"Cannot parse timestamp from stream_id '{stream_id}': {e}")
	
def format_time_for_comment(time_str: str, del_sec = 0) -> str:
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
		adjusted_seconds = max(0, total_seconds - int(del_sec))
		
		# 시:분:초로 변환
		h, remainder = divmod(adjusted_seconds, 3600)
		m, s = divmod(remainder, 60)
		
		return f"{h:02d}:{m:02d}:{s:02d}"
		
	except (ValueError, IndexError) as e:
		print(f"[FORMAT_DEBUG] 예외 발생: {e}")
		return "" 

#두 스트림 ID 사이의 시간 차이를 초 단위로 계산
def calculate_stream_duration(stream_start_id: str, stream_end_id: str) -> float:
    try:
        start_time = get_timestamp_from_stream_id(stream_start_id)
        end_time = get_timestamp_from_stream_id(stream_end_id)
        return (end_time - start_time).total_seconds()
    except ValueError as e:
        print(f"{datetime.now()} 스트림 지속시간 계산 오류: {e}")
        return 0.0

# 치지직 API URL 생성 함수
def chzzk_getLink(uid: str): 
	return f"https://api.chzzk.naver.com/service/v2/channels/{uid}/live-detail"

# 아프리카 API URL 생성 함수
def afreeca_getLink(afreeca_id: str): 
	return f"https://chapi.sooplive.co.kr/api/{afreeca_id}/station"

# 플랫폼별 API 요청 처리 함수
async def get_message(performance_manager: PerformanceManager, platform, link):
	start_time = datetime.now()  # 시작 시간 기록
	
	# 미리 정의된 플랫폼별 API 요청 구성
	platform_config = {
		"afreeca": {
			"needs_cookies": False,
			"needs_params": False,
			"url_formatter": link,
			"response_handler": lambda response: loads(response.text),
		},
		"chzzk": {
			"needs_cookies": True,
			"needs_params": True,
			"url_formatter": link,
			"response_handler": lambda response: loads(response.text),
		},
		"twitch": {
			"needs_cookies": False,
			"needs_params": False,
			"url_formatter": link,
			"response_handler": lambda response: loads(response.text),
		},
		"cafe": {
			"needs_cookies": False,
			"needs_params": True,
			"url_formatter": lambda link, cafe_num: link,
			"response_handler": lambda response: loads(response.text),
		},
		"youtube": {
			"needs_cookies": False,
			"needs_params": False,
			"url_formatter": link,
			"response_handler": lambda response: response.text,
		},
		"image": {
    		"needs_cookies": False,
			"needs_params": False,
			"url_formatter": link,
			"response_handler": lambda response: response.content,
		},
	}
	
	try:
		config = platform_config.get(platform)
		if not config:
			raise ValueError(f"지원하지 않는 플랫폼입니다: {platform}")
		
		# 기본 헤더 및 요청 설정
		headers = {}
		request_kwargs = {"timeout": 10}
		
		# 플랫폼별 헤더 설정
		if platform == "chzzk":
			headers = getDefaultHeaders()
		elif platform == "twitch":
			headers = getTwitchHeaders()
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
				pass
		
		# 재시도 설정
		max_retries = 3
		retry_count = 0
		retry_delay = 2  # 초 단위
		
		# 재시도 메커니즘
		while retry_count < max_retries:
			try:
				# API 요청 실행
				response = await asyncio.to_thread(
					get,
					formatted_url,
					**request_kwargs
				)
				
				end_time = datetime.now()
				response_time_ms = int((end_time - start_time).total_seconds() * 1000)
				# 응답 코드 확인
				if response.status_code != 200:
					# 실패 로깅
					asyncio.create_task(performance_manager.log_api_performance(
						api_type=f"{platform}_api",
						response_time_ms=response_time_ms,
						is_success=False,
						http_status_code=response.status_code,
						retry_count=retry_count
					))
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
				
				# 성공 로깅
				asyncio.create_task(performance_manager.log_api_performance(
					api_type=f"{platform}_api",
					response_time_ms=response_time_ms,
					is_success=True,
					http_status_code=response.status_code,
					retry_count=retry_count
				))
				return config["response_handler"](response)
				
			except (ConnectTimeout, ReadTimeout, ConnectionError, HTTPError, RemoteDisconnected) as e:
				end_time = datetime.now()
				response_time_ms = int((end_time - start_time).total_seconds() * 1000)
				
				# 에러 로깅
				asyncio.create_task(performance_manager.log_api_performance(
					api_type=f"{platform}_api",
					response_time_ms=response_time_ms,
					is_success=False,
					error_type=type(e).__name__,
					error_message=str(e),
					retry_count=retry_count
				))
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

# VOD 알림 상태 변경 함수
async def change_is_vod_json_state(is_vod_json, channel_id, chat_rejoin = True):
	is_vod_json[channel_id] = chat_rejoin
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	for _ in range(3):  # 최대 3번 시도
		try:
			supabase.table('date_update').upsert({"idx": 0, "is_vod_json": is_vod_json}).execute()
			break
		except Exception as e:
			asyncio.create_task(log_error(f"echange_chat_join_state {e}"))
			await asyncio.sleep(0.1)

# VOD 채팅 알림 연결 상태 변경 함수
async def change_is_vod_chat_json_state(is_vod_chat_json, channel_id, chat_rejoin = True):
	is_vod_chat_json[channel_id] = chat_rejoin
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	for _ in range(3):  # 최대 3번 시도
		try:
			supabase.table('date_update').upsert({"idx": 0, "is_vod_chat_json": is_vod_chat_json}).execute()
			break
		except Exception as e:
			asyncio.create_task(log_error(f"echange_chat_join_state {e}"))
			await asyncio.sleep(0.1)

# 핫클립 알림 상태 변경 함수
async def change_is_hot_clip_state(is_hot_clip, channel_id, chat_rejoin = True):
	is_hot_clip[channel_id] = chat_rejoin
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	for _ in range(3):  # 최대 3번 시도
		try:
			supabase.table('date_update').upsert({"idx": 0, "is_hot_clip": is_hot_clip}).execute()
			break
		except Exception as e:
			asyncio.create_task(log_error(f"echange_chat_join_state {e}"))
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
	
# 비디오 데이터 저장 함수
async def save_video_data(video_data, _id): 
	supabase = create_client(environ['supabase_url'], environ['supabase_key'])
	data = {
		"channelID": _id,
		'VOD_json': video_data.loc[_id, 'VOD_json']
	}
	for _ in range(3):  # 최대 3번 시도
		try:
			supabase.table(f'video_data').upsert(data).execute()
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
	data = {
			'discordURL': webhook_url, 
			'notifications': notifications,
			'last_db_save_time': last_db_save_time
	}
	
	for _ in range(3):  # 최대 3번 시도
		try:
			await asyncio.to_thread(
				lambda: supabase.table('userStateData')
					.upsert(data)
					.execute()
			)
			print(f"{datetime.now()} 알림을 DB에 저장함 - URL: {webhook_url}")
			return True
		except Exception as e:
			print(f"{datetime.now()} 알림 저장 중 오류: {e} - URL: {webhook_url}")
			await asyncio.sleep(0.1)  # 잠시 대기 후 재시도
	
	return False  # 모든 시도 실패

# 보낸 클립 UID 저장 함수
async def save_sent_notifications(supabase, channel_id, hot_clip_data):
	data = {
                'channelID': channel_id,
                'last_updated': datetime.now().isoformat(),
                'sent_clip_uids': hot_clip_data.loc[channel_id, 'sent_clip_uids']
            }

	for _ in range(3):  # 최대 3번 시도
		try:
			await asyncio.to_thread(
				lambda: supabase.table('hot_clip_data')
					.upsert(data)
					.execute()
			)
			print(f"{datetime.now()} 알림을 DB에 저장함 - channelID: {channel_id}")
			return True
		except Exception as e:
			print(f"{datetime.now()} 알림 저장 중 오류: {e} - channelID : {channel_id}")
			await asyncio.sleep(0.1)  # 잠시 대기 후 재시도
	
	return False  # 모든 시도 실패
