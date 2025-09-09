from os import environ
import logging
import asyncio
import aiohttp
from json import loads, load, dump, JSONDecodeError
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
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from pathlib import Path
from typing import List, Dict, Optional
import google.generativeai as genai

# 로컬 통계 파일 경로 설정
STATS_DIR = Path("stats_data")
API_PERFORMANCE_FILE = STATS_DIR / "api_performance.json"
DAILY_STATS_FILE = STATS_DIR / "daily_statistics.json"

# 디렉토리가 없으면 생성
STATS_DIR.mkdir(exist_ok=True)

# 메모리 캐시
_api_performance_cache = []

# 파일 쓰기 락 (동시 쓰기 방지)
_file_write_lock = asyncio.Lock()

#API 성능 데이터를 효율적으로 관리하는 클래스
class APIPerformanceManager:
	
	def __init__(self):
		self._file_data_cache = None
		self._cache_timestamp = None
		self._cache_ttl = 300  # 5분
		
	#캐시가 유효한지 확인
	def _is_cache_valid(self) -> bool:
		if self._file_data_cache is None or self._cache_timestamp is None:
			return False
		return (datetime.now() - self._cache_timestamp).seconds < self._cache_ttl
	
	#파일에서 데이터를 로드하고 캐시에 저장
	def _load_file_data(self) -> List[Dict]:
		try:
			if API_PERFORMANCE_FILE.exists():
				with open(API_PERFORMANCE_FILE, 'r', encoding='utf-8') as f:
					data = load(f)
					self._file_data_cache = data
					self._cache_timestamp = datetime.now()
					return data
		except Exception as e:
			print(f"API 성능 데이터 로드 실패: {e}")
		return []
	
	#메모리 캐시와 파일 데이터를 합쳐서 반환
	def get_all_data(self) -> List[Dict]:
		# 파일 캐시가 유효하지 않으면 다시 로드
		if not self._is_cache_valid():
			self._load_file_data()
		
		file_data = self._file_data_cache or []
		return _api_performance_cache + file_data
	
	#캐시 무효화
	def invalidate_cache(self):
		self._file_data_cache = None
		self._cache_timestamp = None

# 전역 매니저 인스턴스
performance_manager = APIPerformanceManager()

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
		{"after_openDate": "시간", "text": "댓글 내용", "description": "방송 썸네일을 포함한 상세 분석 댓글"}
		]

		분석 우선순위:
		1. "최근 채팅" 내용으로 구체적 상황 파악 (게임, 행동, 사건)
		2. "하이라이트 이유"로 반응 유형 확인
		3. 점수 데이터로 상황의 특성 분석:
		- 채팅 급증 점수 높음 → 갑작스러운 사건
		- 리액션 점수 높음 → 강한 감정 반응
		- 시청자 급증 점수 높음 → 화제성 있는 순간
		- 다양성 점수 높음 → 다양한 시청자 참여

		댓글 작성 방식:
		1. 채팅에서 명확한 상황(게임명, 행동)이 보이면 구체적으로 표현
		2. 점수 패턴으로 상황의 성격 파악:
		- 리액션 점수 > 채팅 급증 점수 → 감정적 반응 중심
		- 채팅 급증 점수 > 리액션 점수 → 사건/상황 중심
		- 시청자 급증 있음 → 주목받는 순간
		3. "큰 하이라이트 여부"가 true면 더 임팩트 있게 표현
		4. 필드별 작성 규칙:
		- text: 채팅과 점수 데이터만으로 분석한 기본 댓글
		- description: 방송 썸네일이 있다면 이미지까지 분석하여 더 구체적이고 정확한 시청자 반응으로 작성. 썸네일이 없다면 "방송 썸네일이 없어 기본 분석만 가능합니다"
		5. 모든 댓글은 실제 시청자 톤으로 20자 이내, 자연스럽게 작성

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

# API 성능 데이터를 로컬 파일에 로깅하는 함수
async def log_api_performance(api_type: str, response_time_ms: int, is_success: bool, 
							http_status_code: int = None, error_type: str = None, 
							error_message: str = None, retry_count: int = 0,
							user_count: int = None, batch_size: int = None,
							additional_data: dict = None):
	return 

	data = {
		"timestamp": datetime.now().isoformat(),
		"api_type": api_type,
		"response_time_ms": response_time_ms,
		"is_success": is_success,
		"http_status_code": http_status_code,
		"error_type": error_type,
		"error_message": error_message,
		"retry_count": retry_count,
		"user_count": user_count,
		"batch_size": batch_size,
		"additional_data": additional_data,
	}
	
	try:
		# 메모리 캐시에 추가
		_api_performance_cache.append(data)
		
		# 캐시가 1000개 이상이면 파일에 저장하고 캐시 정리
		if len(_api_performance_cache) >= 1000:
			asyncio.create_task(_flush_api_performance_cache())
			
	except Exception as e:
		print(f"API 성능 로깅 실패: {e}")

# API 성능 캐시를 파일에 저장하는 함수
async def _flush_api_performance_cache():
    async with _file_write_lock:
        if not _api_performance_cache:
            return
    
        try:
            data_to_save = _api_performance_cache.copy()
            _api_performance_cache.clear()
            
            # 기존 데이터 로드
            existing_data = []
            if API_PERFORMANCE_FILE.exists():
                with open(API_PERFORMANCE_FILE, 'r', encoding='utf-8') as f:
                    try:
                        existing_data = load(f)
                    except JSONDecodeError:
                        existing_data = []
            
            # 복사한 데이터 추가
            existing_data.extend(data_to_save)
            
            # 오래된 데이터 제거
            cutoff_date = datetime.now() - timedelta(days=3)
            filtered_data = [    
                item for item in existing_data
                if datetime.fromisoformat(item['timestamp']) > cutoff_date
            ]
            
            # 파일에 저장
            with open(API_PERFORMANCE_FILE, 'w', encoding='utf-8') as f:
                dump(filtered_data, f, ensure_ascii=False, indent=2)
            
            # 캐시 무효화
            performance_manager.invalidate_cache()
            
        except Exception as e:
            print(f"API 성능 데이터 파일 저장 실패: {e}")

# 로컬 파일에서 일일 통계 로드하는 함수
def load_daily_statistics():
	try:
		if DAILY_STATS_FILE.exists():
			with open(DAILY_STATS_FILE, 'r', encoding='utf-8') as f:
				return load(f)
	except Exception as e:
		print(f"일일 통계 데이터 로드 실패: {e}")
	return {}

# 앱 종료 시 캐시 저장
async def save_all_cached_data():
	try:
		if _api_performance_cache:
			await _flush_api_performance_cache()
	
		print("모든 캐시된 통계 데이터가 파일에 저장되었습니다.")
	except Exception as e:
		print(f"캐시 데이터 저장 실패: {e}")

# 특정 API 타입의 평균 응답시간 계산하는 함수
async def calculate_avg_response_time(api_type: str, date, days=1, data_source: List[Dict] = None):
	try:
		# 데이터 소스가 제공되지 않으면 매니저에서 가져오기
		if data_source is None:
			all_data = performance_manager.get_all_data()
		else:
			all_data = data_source
		
		# 기간별 계산
		end_date = date
		start_date = date - timedelta(days=days-1)
		filtered_data = []
		
		for item in all_data:
			if item['api_type'] == api_type and item['is_success']:
				item_date = datetime.fromisoformat(item['timestamp']).date()
				if start_date <= item_date <= end_date:
					filtered_data.append(item)
		
		if filtered_data:
			times = [item['response_time_ms'] for item in filtered_data]
			return round(sum(times) / len(times), 2)
		return 0
		
	except Exception as e:
		await log_error(f"평균 응답시간 계산 오류: {e}")
		return 0

# 특정 API 타입의 성공률 계산하는 함수
async def calculate_success_rate(api_type: str, date, days=1, 
										data_source: List[Dict] = None):
	try:
		if data_source is None:
			all_data = performance_manager.get_all_data()
		else:
			all_data = data_source

		# 기간별 계산
		end_date = date
		start_date = date - timedelta(days=days-1)
		filtered_data = []
		
		for item in all_data:
			if item['api_type'] == api_type:
				item_date = datetime.fromisoformat(item['timestamp']).date()
				if start_date <= item_date <= end_date:
					filtered_data.append(item)
		
		if filtered_data:
			total_count = len(filtered_data)
			success_count = sum(1 for item in filtered_data if item['is_success'])
			return round((success_count / total_count) * 100, 2) if total_count > 0 else 100
		
		return 100
		
	except Exception as e:
		await log_error(f"성공률 계산 오류: {e}")
		return 0

# 에러 개수 계산하는 함수
async def get_error_count(date, data_source: List[Dict] = None):
	try:
		if data_source is None:
			all_data = performance_manager.get_all_data()
		else:
			all_data = data_source
		
		target_date = date.strftime('%Y-%m-%d')
		filtered_data = [
			item for item in all_data
			if (not item['is_success'] and
				item['timestamp'].startswith(target_date))
		]
		
		return len(filtered_data)
		
	except Exception as e:
		await log_error(f"에러 개수 계산 오류: {e}")
		return 0
	
# 사용자 통계 계산하는 함수
async def get_user_statistics(date):
	try:
		from shared_state import StateManager
		state = StateManager.get_instance()
		init = state.get_init()

		total_users_result = await asyncio.to_thread(
			lambda: init.supabase.table('userStateData')
				.select('discordURL', count='exact')
				.execute()
		)
		
		yesterday = date - timedelta(days=1)
		active_users_result = await asyncio.to_thread(
			lambda: init.supabase.table('userStateData')
				.select('discordURL', count='exact')
				.gte('last_db_save_time', f'{yesterday}T00:00:00')
				.execute()
		)
		
		return {
			'total_users': total_users_result.count or 0,
			'active_users': active_users_result.count or 0,
		}
	except Exception as e:
		await log_error(f"사용자 통계 계산 오류: {e}")
		return {'total_users': 0, 'active_users': 0}

# 알림 통계 계산하는 함수
async def get_notification_statistics(date, data_source: List[Dict] = None):
	try:
		if data_source is None:
			all_data = performance_manager.get_all_data()
		else:
			all_data = data_source
		
		target_date = date.strftime('%Y-%m-%d')
		
		discord_data = [
			item for item in all_data
			if (item['api_type'] == 'discord_webhook' and 
				item['is_success'] and
				item['timestamp'].startswith(target_date))
		]
		
		fcm_data = [
			item for item in all_data
			if (item['api_type'] == 'fcm_push' and 
				item['is_success'] and
				item['timestamp'].startswith(target_date))
		]
		
		discord_count = len(discord_data)
		fcm_count = len(fcm_data)
		
		return {
			'discord': discord_count,
			'fcm': fcm_count,
			'total': discord_count + fcm_count
		}
	except Exception as e:
		await log_error(f"알림 통계 계산 오류: {e}")
		return {'discord': 0, 'fcm': 0, 'total': 0}
	
#모니터링 중인 스트리머 수 계산하는 함수
async def get_monitored_streamers_count():
	try:
		from shared_state import StateManager
		state = StateManager.get_instance()
		init = state.get_init()
		if init is None:
			return 0
			
		chzzk_count = len(init.chzzkIDList) if hasattr(init, 'chzzkIDList') else 0
		afreeca_count = len(init.afreecaIDList) if hasattr(init, 'afreecaIDList') else 0
		
		return chzzk_count + afreeca_count 
	except Exception as e:
		await log_error(f"모니터링 스트리머 수 계산 오류: {e}")
		return 0

#현재 활성 스트림 수 계산하는 함수
async def get_active_streams_count():
	try:
		from shared_state import StateManager
		state = StateManager.get_instance()
		init = state.get_init()
		if init is None:
			return 0
			
		online_counts = {
			'chzzk': get_online_count(init.chzzk_titleData) if hasattr(init, 'chzzk_titleData') else 0,
			'afreeca': get_online_count(init.afreeca_titleData) if hasattr(init, 'afreeca_titleData') else 0,
			'twitch': get_online_count(init.twitch_titleData) if hasattr(init, 'twitch_titleData') else 0
		}
		
		# 전체 활성 스트림 수 반환
		return sum(online_counts.values())

	except Exception as e:
		await log_error(f"활성 스트림 수 계산 오류: {e}")
		return 0

# 일일 통계를 계산하고 로컬 파일에 저장하는 함수
async def calculate_and_save_daily_statistics():
	today = datetime.now().date()
	yesterday = today - timedelta(days=1)
	
	try:
		print(f"{datetime.now()} 일일 통계 계산 시작: {yesterday}")
		
		# 데이터 로드
		all_data = performance_manager.get_all_data()
		
		# 통계 계산
		discord_avg = await calculate_avg_response_time(
			'discord_webhook', yesterday, data_source=all_data)
		fcm_avg = await calculate_avg_response_time(
			'fcm_push', yesterday, data_source=all_data)
		discord_success_rate = await calculate_success_rate(
			'discord_webhook', yesterday, data_source=all_data)
		fcm_success_rate = await calculate_success_rate(
			'fcm_push', yesterday, data_source=all_data)
		
		user_stats = await get_user_statistics(yesterday)
		notification_stats = await get_notification_statistics(
			yesterday, data_source=all_data)
		error_count = await get_error_count(yesterday, data_source=all_data)
		
		monitored_streamers = await get_monitored_streamers_count()
		active_streams = await get_active_streams_count()
		system_uptime = await calculate_system_uptime(data_source=all_data)
		
		# 일일 통계 데이터
		daily_stat = {
			"date": yesterday.isoformat(),
			"total_users": user_stats.get('total_users', 0),
			"active_users": user_stats.get('active_users', 0),
			"total_notifications_sent": notification_stats.get('total', 0),
			"discord_notifications": notification_stats.get('discord', 0),
			"fcm_notifications": notification_stats.get('fcm', 0),
			"monitored_streamers": monitored_streamers,
			"active_streams": active_streams,
			"avg_discord_response_time_ms": discord_avg,
			"avg_fcm_response_time_ms": fcm_avg,
			"discord_success_rate": discord_success_rate,
			"fcm_success_rate": fcm_success_rate,
			"system_uptime_hours": system_uptime,
			"error_count": error_count,
			"created_at": datetime.now().isoformat()
		}
		
		# 로컬 파일에 저장
		await _save_daily_statistics(daily_stat)
		
		print(f"{datetime.now()} 일일 통계 저장 완료: {yesterday}")
		print(f"Discord 평균 응답시간: {discord_avg}ms, 성공률: {discord_success_rate}%")
		print(f"FCM 평균 응답시간: {fcm_avg}ms, 성공률: {fcm_success_rate}%")
		
	except Exception as e:
		await log_error(f"일일 통계 계산 및 저장 오류: {e}")

# 일일 통계를 로컬 파일에 저장하는 함수
async def _save_daily_statistics(daily_stat):
	try:
		# 기존 데이터 로드
		existing_stats = {}
		if DAILY_STATS_FILE.exists():
			with open(DAILY_STATS_FILE, 'r', encoding='utf-8') as f:
				try:
					existing_stats = load(f)
				except JSONDecodeError:
					existing_stats = {}
		
		# 새 통계 추가 (날짜를 키로 사용)
		date_key = daily_stat['date']
		existing_stats[date_key] = daily_stat
		
		# 오래된 데이터 제거 (30일 이상된 데이터)
		cutoff_date = datetime.now().date() - timedelta(days=30)
		filtered_stats = {
			date: stat for date, stat in existing_stats.items()
			if datetime.fromisoformat(date).date() > cutoff_date
		}
		
		# 파일에 저장
		with open(DAILY_STATS_FILE, 'w', encoding='utf-8') as f:
			dump(filtered_stats, f, ensure_ascii=False, indent=2)
			
	except Exception as e:
		print(f"일일 통계 파일 저장 실패: {e}")

# 시스템 가동 시간 계산하는 함수
async def calculate_system_uptime(data_source: List[Dict] = None):
	try:
		today = datetime.now().date()
		
		if data_source is None:
			all_data = performance_manager.get_all_data()
		else:
			all_data = data_source
		
		target_date = today.strftime('%Y-%m-%d')
		today_data = [
			item for item in all_data
			if item['timestamp'].startswith(target_date)
		]
		
		if today_data:
			# 첫 번째 API 호출 시간 찾기
			earliest_time = min(item['timestamp'] for item in today_data)
			first_call = datetime.fromisoformat(earliest_time)
			now = datetime.now()
			uptime_hours = (now - first_call).total_seconds() / 3600
			return round(uptime_hours, 2)
		
		return 0
		
	except Exception as e:
		await log_error(f"시스템 가동시간 계산 오류: {e}")
		return 0

#실시간 통계 조회하는 함수
async def get_realtime_statistics(days=7):
	end_date = datetime.now().date()
	
	try:
		# 데이터 로드
		all_data = performance_manager.get_all_data()
		
		# 통계 계산
		discord_avg = await calculate_avg_response_time(
			'discord_webhook', end_date, days, data_source=all_data)
		fcm_avg = await calculate_avg_response_time(
			'fcm_push', end_date, days, data_source=all_data)
		discord_success = await calculate_success_rate(
			'discord_webhook', end_date, days, data_source=all_data)
		fcm_success = await calculate_success_rate(
			'fcm_push', end_date, days, data_source=all_data)
		
		monitored_streamers = await get_monitored_streamers_count()
		active_streams = await get_active_streams_count()
		
		start_date = end_date - timedelta(days=days-1)
		
		return {
			"period": f"{start_date} ~ {end_date}",
			"performance": {
				"discord_webhook": {
					"avg_response_time_ms": discord_avg,
					"success_rate": discord_success
				},
				"fcm_push": {
					"avg_response_time_ms": fcm_avg,
					"success_rate": fcm_success
				}
			},
			"system": {
				"monitored_streamers": monitored_streamers,
				"active_streams": active_streams
			}
		}
	except Exception as e:
		await log_error(f"실시간 통계 조회 오류: {e}")
		return None

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
				'chzzk_video': 'channelID',
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

#두 스트림 ID 사이의 시간 차이를 초 단위로 계산
def calculate_stream_duration(start_stream_id: str, end_stream_id: str) -> float:
    try:
        start_time = get_timestamp_from_stream_id(start_stream_id)
        end_time = get_timestamp_from_stream_id(end_stream_id)
        return (end_time - start_time).total_seconds()
    except ValueError as e:
        print(f"스트림 지속시간 계산 오류: {e}")
        return 0.0

# 치지직 API URL 생성 함수
def chzzk_getLink(uid: str): 
	return f"https://api.chzzk.naver.com/service/v2/channels/{uid}/live-detail"

# 아프리카 API URL 생성 함수
def afreeca_getLink(afreeca_id: str): 
	return f"https://chapi.sooplive.co.kr/api/{afreeca_id}/station"

# 플랫폼별 API 요청 처리 함수
async def get_message(platform, link):
	start_time = datetime.now()  # 시작 시간 기록
	
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
					asyncio.create_task(log_api_performance(
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
				asyncio.create_task(log_api_performance(
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
				asyncio.create_task(log_api_performance(
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

#성능 통계 수집 스케줄러 설정 함수
def setup_performance_scheduler():
	scheduler = BackgroundScheduler()
	
	scheduler.add_job(
		func=lambda: asyncio.run(calculate_and_save_daily_statistics()),
		trigger="cron",
		hour=0,
		minute=5,
		id='daily_statistics'
	)
	
	scheduler.start()
	print("성능 통계 스케줄러가 시작되었습니다 (매일 00:05에 실행)")
	
	atexit.register(lambda: scheduler.shutdown())