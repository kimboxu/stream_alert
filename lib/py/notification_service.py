import asyncio
import os
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from firebase_admin import messaging, credentials, get_app, initialize_app
from concurrent.futures import ThreadPoolExecutor
from json import loads
from flask import current_app, g
from supabase import create_client

# 환경 변수 가져오기
SUPABASE_URL = os.environ.get('supabase_url')
SUPABASE_KEY = os.environ.get('supabase_key')

# 전역 설정
FCM_THREAD_POOL_SIZE = 10
fcm_thread_pool = ThreadPoolExecutor(max_workers=FCM_THREAD_POOL_SIZE)

# 캐시 클래스
class NotificationCache:
    """
    사용자 데이터와 알림을 캐싱하여 데이터베이스 조회를 최소화합니다.
    """
    def __init__(self, cache_ttl=300):  # 기본 캐시 유효시간 5분
        self.user_cache = {}  # 웹훅 URL -> 사용자 데이터
        self.token_cache = {}  # 웹훅 URL -> FCM 토큰 리스트
        self.cache_ttl = cache_ttl
        self.last_update = {}  # 웹훅 URL -> 마지막 업데이트 시간
    
    def get_user_data(self, webhook_url):
        """캐시된 사용자 데이터를 반환합니다."""
        now = datetime.now().timestamp()
        if webhook_url in self.user_cache and now - self.last_update.get(webhook_url, 0) < self.cache_ttl:
            return self.user_cache[webhook_url]
        return None
    
    def set_user_data(self, webhook_url, user_data):
        """사용자 데이터를 캐시에 저장합니다."""
        self.user_cache[webhook_url] = user_data
        self.last_update[webhook_url] = datetime.now().timestamp()
    
    def get_tokens(self, webhook_url):
        """캐시된 FCM 토큰을 반환합니다."""
        now = datetime.now().timestamp()
        if webhook_url in self.token_cache and now - self.last_update.get(webhook_url, 0) < self.cache_ttl:
            return self.token_cache[webhook_url]
        return None
    
    def set_tokens(self, webhook_url, tokens):
        """FCM 토큰을 캐시에 저장합니다."""
        self.token_cache[webhook_url] = tokens
        self.last_update[webhook_url] = datetime.now().timestamp()
    
    def invalidate(self, webhook_url=None):
        """
        특정 URL 또는 모든 캐시를 무효화합니다.
        """
        if webhook_url:
            if webhook_url in self.user_cache:
                del self.user_cache[webhook_url]
            if webhook_url in self.token_cache:
                del self.token_cache[webhook_url]
            if webhook_url in self.last_update:
                del self.last_update[webhook_url]
        else:
            self.user_cache = {}
            self.token_cache = {}
            self.last_update = {}

# 전역 캐시 인스턴스
notification_cache = NotificationCache()

# Supabase 클라이언트 가져오기
def get_supabase_client():
    if not hasattr(g, 'supabase_client'):
        g.supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return g.supabase_client

# FCM 메시지 전송 함수
def send_fcm_message(token, notification_data, data_fields):
    """
    개별 FCM 토큰에 메시지를 전송합니다. 스레드 풀에서 실행됩니다.
    """
    try:
        # FCM은 모든 데이터 필드가 문자열이어야 함
        message_data = {k: str(v) if not isinstance(v, (list, dict)) else str(v) for k, v in data_fields.items()}
        
        # 메시지 객체 생성
        message = messaging.Message(
            notification=messaging.Notification(**notification_data),
            data=message_data,
            token=token,
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="high_importance_channel",
                    priority="high",
                ),
            ),
        )

        # 메시지 전송 및 결과 로깅
        result = messaging.send(message, dry_run=False)
        print(f"FCM 메시지 전송 성공: {token[:15]}... 결과: {result}")
        return result
    except messaging.UnregisteredError:
        print(f"FCM 토큰 등록 취소됨 (앱 제거): {token[:15]}...")
        return None
    except messaging.InvalidArgumentError as e:
        print(f"FCM 메시지 전송 실패 - 유효하지 않은 인자 (토큰: {token[:15]}...): {e}")
        return None
    except Exception as e:
        print(f"FCM 메시지 전송 실패 (토큰: {token[:15]}...): {e}")
        return None

# 배치 알림 저장 함수
async def batch_save_notifications(supabase, user_data_map, notification_id, data_fields):
    """
    여러 사용자의 알림을 일괄 처리합니다.
    
    Args:
        supabase: Supabase 클라이언트
        user_data_map: 웹훅 URL을 키로, 사용자 데이터를 값으로 하는 딕셔너리
        notification_id: 알림 고유 ID
        data_fields: 알림 데이터 필드
    """
    # 일괄 업데이트를 위한 작업 배열
    updates = []
    
    for webhook_url, user_data in user_data_map.items():
        # 기존 알림 목록 가져오기
        notifications = user_data.get('notifications', [])
        if not isinstance(notifications, list):
            try:
                notifications = loads(notifications)
            except:
                notifications = []
        
        # 알림 추가 (이미 있는 알림 체크)
        notification_exists = False
        for idx, notification in enumerate(notifications):
            if notification.get('id') == notification_id:
                # 중복 알림 업데이트
                notifications[idx] = data_fields
                notification_exists = True
                break
                
        if not notification_exists:
            # 새 알림 추가
            notifications.append(data_fields)
            
        # 최대 알림 수 제한 (최신 10000개만 유지)
        if len(notifications) > 10000:
            notifications = notifications[-10000:]
        
        # 업데이트 작업 추가
        updates.append({
            'webhook_url': webhook_url,
            'notifications': notifications
        })
    
    # 일괄 업데이트 수행
    for update in updates:
        try:
            # 비동기로 실행하되 에러 처리 추가
            await asyncio.to_thread(
                lambda: supabase.table('userStateData')
                  .update({'notifications': update['notifications']})
                  .eq('discordURL', update['webhook_url'])
                  .execute()
            )
        except Exception as e:
            print(f"알림 저장 중 오류: {e} - URL: {update['webhook_url'][:20]}...")
            continue

# FCM 메시지 배치 전송 함수
async def send_fcm_messages_in_batch(tokens, notification_data, data_fields, batch_size=20):
    """
    여러 FCM 토큰에 동일한 메시지를 배치로 전송합니다.
    
    Args:
        tokens: FCM 토큰 목록
        notification_data: 알림 데이터
        data_fields: 데이터 필드
        batch_size: 한 번에 처리할 토큰 수
    """
    if not tokens:
        return []
    
    all_results = []
    
    # 토큰을 배치 크기로 분할
    batches = [tokens[i:i+batch_size] for i in range(0, len(tokens), batch_size)]
    
    for batch in batches:
        batch_tasks = []
        for token in batch:
            task = asyncio.to_thread(send_fcm_message, token, notification_data, data_fields)
            batch_tasks.append(task)
            
        # 배치 단위로 병렬 처리하되 타임아웃 설정
        try:
            batch_results = await asyncio.wait_for(
                asyncio.gather(*batch_tasks, return_exceptions=True),
                timeout=5  # 배치당 최대 5초 제한
            )
            all_results.extend(batch_results)
        except asyncio.TimeoutError:
            print(f"배치 FCM 메시지 전송 시간 초과 (배치 크기: {len(batch)})")
            # 타임아웃된 배치에 대한 결과는 None으로 처리
            all_results.extend([None] * len(batch))
    
    return all_results

# GMT 시간 변경 함수 (기존 base.py의 함수)
def changeGMTtime(time_str):
    time = datetime.fromisoformat(time_str)
    time += timedelta(hours=9)
    return time.isoformat()

# Firebase 초기화 함수를 my_app.py에서 가져오거나 여기서 직접 구현
def initialize_firebase(firebase_initialized_globally):
    """Firebase 초기화 함수"""
    # 이미 전역 변수에서 초기화 완료 확인됨
    if firebase_initialized_globally:
        return True
        
    try:
        # 이미 초기화되었는지 확인
        get_app()
        print("Firebase 앱이 이미 초기화되어 있습니다.")
        firebase_initialized_globally = True
        return True
    except ValueError:
        # 초기화되지 않은 경우에만 초기화 진행
        try:
            # 환경 변수에서 Firebase 인증 정보 가져오기
            cred_dict = {
                "type": os.environ.get("FIREBASE_TYPE"),
                "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
                "private_key_id": os.environ.get("FIREBASE_PRIVATE_KEY_ID"),
                "private_key": os.environ.get("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
                "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL"),
                "client_id": os.environ.get("FIREBASE_CLIENT_ID"),
                "auth_uri": os.environ.get("FIREBASE_AUTH_URI"),
                "token_uri": os.environ.get("FIREBASE_TOKEN_URI"),
                "auth_provider_x509_cert_url": os.environ.get(
                    "FIREBASE_AUTH_PROVIDER_X509_CERT_URL"
                ),
                "client_x509_cert_url": os.environ.get("FIREBASE_CLIENT_X509_CERT_URL"),
                "universe_domain": os.environ.get("FIREBASE_UNIVERSE_DOMAIN"),
            }

            # 인증 정보 생성
            cred = credentials.Certificate(cred_dict)

            # 프로젝트 ID 가져오기
            project_id = cred.project_id or os.environ.get("FIREBASE_PROJECT_ID")

            if not project_id:
                print("Firebase 프로젝트 ID를 찾을 수 없습니다.")
                return False

            # Firebase 앱 초기화 (한 번만 호출)
            initialize_app(
                cred,
                {
                    "projectId": project_id,
                },
            )

            print(f"Firebase 앱이 프로젝트 ID '{project_id}'로 성공적으로 초기화되었습니다.")
            firebase_initialized_globally = True
            return True
        except Exception as e:
            print(f"Firebase 초기화 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            return False

# 푸시 알림 전송 함수
async def new_send_push_notification(messages, json_data, firebase_initialized_globally=True):
    """
    여러 사용자에게 푸시 알림을 전송합니다.
    성능이 개선된 버전입니다.
    
    Args:
        messages: 웹훅 URL 목록
        json_data: 알림 데이터
        firebase_initialized_globally: Firebase 초기화 상태
    """
    # Firebase 초기화 확인
    if not (firebase_initialized_globally := initialize_firebase(firebase_initialized_globally)):
        print("Firebase 초기화 실패")
        return False

    try:
        # 실행 시간 측정 시작
        start_time = datetime.now()
        
        # 알림 고유 ID 및 시간 미리 생성
        notification_id = str(uuid4())
        notification_time = datetime.now(timezone.utc).isoformat()
        notification_time = changeGMTtime(notification_time)

        # 알림 데이터 준비
        notification_data = {
            "title": json_data.get("username", "알림"),
            "body": json_data.get("content", ""),
        }

        # 기본 데이터 필드
        data_fields = {
            "id": notification_id,
            "username": json_data.get("username", "알림"),
            "content": json_data.get("content", ""),
            "avatar_url": json_data.get("avatar_url", ""),
            "timestamp": notification_time,
            "read": False,  # 읽음 상태 추가
        }

        # embeds 데이터가 있으면 추가
        if "embeds" in json_data and json_data["embeds"]:
            data_fields["embeds"] = json_data["embeds"]
            if json_data["embeds"][0].get("timestamp"):
                data_fields["embeds"][0]["timestamp"] = changeGMTtime(json_data["embeds"][0]["timestamp"])

        # 모든 사용자 데이터를 한 번에 조회
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # 필요한 웹훅 URL만 필터링
        webhook_filter = ",".join([f"'{url}'" for url in messages])
        
        # 한 번의 쿼리로 모든 데이터 조회
        try:
            result = supabase.table("userStateData")\
                .select("*")\
                .in_("discordURL", messages)\
                .execute()
            
            user_data_list = result.data
        except Exception as e:
            print(f"사용자 데이터 일괄 조회 중 오류: {e}")
            user_data_list = []
            
            # 대체 방법: 개별 조회
            for url in messages:
                try:
                    individual_result = supabase.table("userStateData")\
                        .select("*")\
                        .eq("discordURL", url)\
                        .execute()
                    
                    if individual_result.data:
                        user_data_list.append(individual_result.data[0])
                except Exception as e2:
                    print(f"개별 사용자 조회 중 오류: {e2}")
        
        # 웹훅 URL을 키로 하는 사용자 데이터 맵 생성
        user_data_map = {user_data.get("discordURL"): user_data for user_data in user_data_list if user_data.get("discordURL")}
        
        # 모든 사용자의 알림 데이터를 일괄 처리
        notification_save_task = asyncio.create_task(
            batch_save_notifications(supabase, user_data_map, notification_id, data_fields)
        )
        
        # FCM 메시지 병렬 처리
        fcm_tasks = []
        
        for user_data in user_data_list:
            # FCM 토큰 목록 가져오기
            existing_tokens = user_data.get("fcm_tokens", "")
            if not existing_tokens:
                continue

            tokens_list = [token.strip() for token in existing_tokens.split(",") if token.strip()]
            if not tokens_list:
                continue
            
            # 각 토큰에 대해 스레드 풀에서 FCM 메시지 전송
            for token in tokens_list:
                fcm_task = asyncio.to_thread(
                    send_fcm_message,
                    token,
                    notification_data,
                    data_fields
                )
                fcm_tasks.append(fcm_task)
        
        # FCM 작업 최대 10초 동안만 기다림 (전체 대기시간 제한)
        if fcm_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*fcm_tasks, return_exceptions=True),
                    timeout=10
                )
            except asyncio.TimeoutError:
                print(f"일부 FCM 메시지 전송이 시간 초과되었습니다. (전체 {len(fcm_tasks)}개 중)")
        
        # 알림 저장 작업이 완료될 때까지 기다림 (최대 5초)
        try:
            await asyncio.wait_for(notification_save_task, timeout=5)
        except asyncio.TimeoutError:
            print("알림 저장 작업이 시간 초과되었습니다.")
        
        # 실행 시간 측정 종료
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        print(f"푸시 알림 전송 완료: {len(user_data_list)}명 대상, {len(fcm_tasks)}개 토큰, {duration:.2f}초 소요")
        
        return True

    except Exception as e:
        print(f"알림 전송 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

# 알림 시스템 초기화 함수
def init_notification_system():
    """
    알림 시스템 초기화 함수
    - FCM 스레드 풀 설정
    - 캐시 초기화
    """
    global fcm_thread_pool
    
    # 스레드 풀 설정
    fcm_thread_pool = ThreadPoolExecutor(max_workers=FCM_THREAD_POOL_SIZE)
    
    # 캐시 초기화
    global notification_cache
    notification_cache = NotificationCache()
    
    print("알림 시스템이 초기화되었습니다.")
    return notification_cache