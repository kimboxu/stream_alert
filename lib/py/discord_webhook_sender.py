import asyncio
from os import environ
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any

from aiohttp import ClientSession, ClientError, TCPConnector
from supabase import create_client
class DiscordWebhookSender:
    # 디스코드 웹훅 전송 클래스 초기화
    def __init__(self,
                supabase_url: str = environ.get('supabase_url'),
                supabase_key: str = environ.get('supabase_key'),
                error_webhook_url: str = environ.get('errorPostBotURL')):

        self.supabase_url = supabase_url  # Supabase URL
        self.supabase_key = supabase_key  # Supabase API 키
        self.error_webhook_url = error_webhook_url  # 오류 로깅용 웹훅 URL
        from shared_state import StateManager
        state_manager = StateManager.get_instance()
        self.performance_manager = state_manager.get_performance_manager()
        
        # 재시도 및 동시성 설정
        self.MAX_RETRIES = 3  # 최대 재시도 횟수
        self.MAX_CONCURRENT = 5  # 최대 동시 요청 수
        self.BASE_DELAY = 0.2  # 지수 백오프의 기본 지연 시간(초)
        self.TIMEOUT = 15  # 요청 타임아웃 시간(초)

    # 여러 웹훅 URL에 메시지를 전송하는 함수
    async def send_messages(self, messages: List[str], json_data, DO_TEST = False) -> List[str]:
        if DO_TEST: # 테스트 모드면 실제 전송하지 않음
            return []  
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)  # 동시 요청 제한을 위한 세마포어
        
        # HTTP 클라이언트 세션 생성
        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            # 각 URL에 대한 전송 태스크 생성
            tasks = [
                asyncio.create_task(
                    self._send_message_with_retry(session, url, json_data, semaphore)
                ) 
                for url in messages
            ]
            
            # 태스크 완료 시 응답 수집
            responses = []
            for task in asyncio.as_completed(tasks):
                result = await task
                if result is not None:
                    responses.append(result)
            
            return responses

    # 재시도 로직이 포함된 메시지 전송 함수
    async def _send_message_with_retry(self, 
                                session: ClientSession, 
                                url: str, 
                                data: Dict[str, Any], 
                                semaphore: asyncio.Semaphore) -> Optional[str]:
        

        async with semaphore:  # 세마포어로 동시 요청 제한
            for attempt in range(self.MAX_RETRIES):
                start_time = datetime.now()
                
                try:
                    # 웹훅 POST 요청 전송
                    async with session.post(url, json=data, timeout=self.TIMEOUT) as response:
                        end_time = datetime.now()
                        response_time_ms = int((end_time - start_time).total_seconds() * 1000)
                        
                        # 성능 로깅
                        asyncio.create_task(self.performance_manager.log_api_performance(
                            api_type='discord_webhook',
                            response_time_ms=response_time_ms,
                            is_success=response.status < 400,
                            http_status_code=response.status,
                            retry_count=attempt
                        ))
                        
                        response.raise_for_status()  # HTTP 오류 발생 시 예외 발생
                        return await response.text()  # 응답 반환
                
                except ClientError as e:
                    end_time = datetime.now()
                    response_time_ms = int((end_time - start_time).total_seconds() * 1000)
                    
                    # 에러 로깅
                    asyncio.create_task(self.performance_manager.log_api_performance(
                        api_type='discord_webhook',
                        response_time_ms=response_time_ms,
                        is_success=False,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        retry_count=attempt
                    ))
                    
                    if hasattr(e, 'status') and e.status == 404:
                        await self._handle_404_error(url)
                    
                    # 지수 백오프 적용 (재시도 간격 점점 증가)
                    await asyncio.sleep(self.BASE_DELAY * (2 ** attempt))
                
                except asyncio.TimeoutError:
                    end_time = datetime.now()
                    response_time_ms = int((end_time - start_time).total_seconds() * 1000)
                    
                    # 타임아웃 로깅
                    asyncio.create_task(self.performance_manager.log_api_performance(
                        api_type='discord_webhook',
                        response_time_ms=response_time_ms,
                        is_success=False,
                        error_type='TimeoutError',
                        retry_count=attempt
                    ))

                    print(f"{datetime.now()} Timeout for {url}: {str(data)}")
                    
                    # 마지막 시도에서 실패한 경우
                    if attempt == self.MAX_RETRIES - 1:
                        return None
                    
                    # 지수 백오프 적용
                    await asyncio.sleep(self.BASE_DELAY * (2 ** attempt))
                
                except Exception as e:
                    end_time = datetime.now()
                    response_time_ms = int((end_time - start_time).total_seconds() * 1000)
                    
                    # 기타 예외 로깅
                    asyncio.create_task(self.performance_manager.log_api_performance(
                        api_type='discord_webhook',
                        response_time_ms=response_time_ms,
                        is_success=False,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        retry_count=attempt
                    ))

                    print(f"{datetime.now()} Unexpected error sending message: {e}")
                    
                    # 마지막 시도에서 실패한 경우
                    if attempt == self.MAX_RETRIES - 1:
                        return None
                    
                    # 지수 백오프 적용
                    await asyncio.sleep(self.BASE_DELAY * (2 ** attempt))
        
        return None  # 모든 시도 실패 시 None 반환

    # 404 오류 처리 함수 (웹훅 URL이 더 이상 존재하지 않는 경우)
    async def _handle_404_error(self, url: str):
        try:
            # 데이터베이스에서 해당 URL 관련 사용자 데이터 삭제
            await self._delete_user_state_data(url)
            await self._log_error(f"Deleted user data for non-existent URL: {url}")
        except Exception as e:
            await self._log_error(f"Error handling 404: {e}")

    # 지속적인 실패 처리 함수
    async def _handle_persistent_failure(self, url: str, error: Exception):
        try:
            # 지속적으로 실패하는 URL의 사용자 데이터 삭제
            await self._delete_user_state_data(url)
            await self._log_error(f"Persistent failure for {url}: {str(error)}")
        except Exception as e:
            await self._log_error(f"Error handling persistent failure: {e}")

    # Supabase에서 사용자 데이터 삭제 함수
    async def _delete_user_state_data(self, url: str):
        if not self.supabase_url or not self.supabase_key:
            return

        # Supabase 클라이언트 생성
        supabase = create_client(self.supabase_url, self.supabase_key)
        
        try:
            # URL에 해당하는 사용자 상태 데이터 삭제
            supabase.table('userStateData').delete().eq('discordURL', url).execute()
        except Exception as e:
            await self._log_error(f"Error deleting user state data: {e}")

    # 오류 로깅 함수
    async def _log_error(self, message: str, webhook_url = environ.get('errorPostBotURL')):
        try:
            # 디스코드 웹훅을 통해 오류 메시지 전송
            async with ClientSession() as session:
                data = {'content': message, "username": "Error Alarm"}
                if webhook_url not in [environ['donation_post_url']]:
                    print(f"{datetime.now()} {message}")
                    
                async with session.post(webhook_url, json=data, timeout=10) as response:
                    # 디스코드 속도 제한 처리
                    if response.status == 429:
                        retry_after = float(response.headers.get('Retry-After', 1))
                        await asyncio.sleep(retry_after)
        except Exception as e:
            print(f"{datetime.now()} Failed to log error to webhook: message:{str(message)},e:{e}")

# 사용자 설정에 따른 전송 대상 웹훅 URL 목록 생성 함수
def get_list_of_urls(DO_TEST, userStateData, name, channel_id, db_name):
    # 결과 URL 목록
    result_urls = []
    try:
        # 테스트 모드인 경우 테스트용 웹훅 URL만 반환
        if DO_TEST:
            for _ in range(1):
                result_urls.append(environ['testPostBotURL'])
            return result_urls
        
        # 사용자 데이터에서 적절한 웹훅 URL 찾기
        for discordWebhookURL in userStateData['discordURL']:
            try:
                # 해당 URL의 사용자 데이터 가져오기
                user_data = userStateData.loc[discordWebhookURL, db_name]
                
                # 데이터 유형 확인 후 리스트 변환
                if isinstance(user_data, str):
                    name_list = user_data  # 문자열인 경우
                elif isinstance(user_data, dict):
                    name_list = user_data.get(channel_id, [])  # 딕셔너리인 경우
                else:
                    name_list = []  # 그 외 경우
                
                # 해당 이름이 리스트에 있으면 URL 추가
                if name in name_list:
                    result_urls.append(discordWebhookURL)
            except (KeyError, AttributeError) as e:
                # 특정 URL 처리 중 오류가 발생해도 다른 URL 처리는 계속
                continue
                
        return result_urls
    except Exception as e:
        # 전체 처리 중 오류 발생 시 로깅
        asyncio.create_task(DiscordWebhookSender._log_error(f"Error in get_cafe_list_of_urls: {type(e).__name__}: {str(e)}"))
        return result_urls

# 채팅 메시지용 웹훅 JSON 데이터 생성 함수
def get_chat_json_data(name, chat, channel_name, profile_image):
    # 채팅 메시지 포맷
    return {'content'   : chat,  # 채팅 내용
            "username"  : name + " >> " + channel_name,  # 표시될 사용자 이름
            "avatar_url": profile_image}  # 프로필 이미지 URL