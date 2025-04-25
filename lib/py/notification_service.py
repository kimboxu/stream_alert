import asyncio
from os import environ
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from firebase_admin import messaging, credentials, get_app, initialize_app
from concurrent.futures import ThreadPoolExecutor
from json import loads, dumps
from flask import current_app, g
from supabase import create_client

# 전역 설정 및 상수
FCM_BATCH_SIZE = 10  # 배치당 처리할 FCM 토큰 수
FCM_BATCH_TIMEOUT = 10  # 배치 처리 타임아웃(초)
NOTIFICATION_SAVE_TIMEOUT = 10  # 알림 저장 타임아웃(초)
CACHE_TTL = 300  # 캐시 유효 시간(초)

# 캐시 클래스
class NotificationCache:
    """
    사용자 데이터와 알림을 캐싱하여 데이터베이스 조회를 최소화합니다.
    """
    def __init__(self, cache_ttl=CACHE_TTL):
        self.user_cache = {}  # 웹훅 URL -> 사용자 데이터
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
    
    def invalidate(self, webhook_url=None):
        """
        특정 URL 또는 모든 캐시를 무효화합니다.
        """
        if webhook_url:
            if webhook_url in self.user_cache:
                del self.user_cache[webhook_url]
            if webhook_url in self.last_update:
                del self.last_update[webhook_url]
        else:
            self.user_cache = {}
            self.last_update = {}

# 전역 캐시 인스턴스
notification_cache = NotificationCache()

# Supabase 클라이언트 가져오기
def get_supabase_client():
    """애플리케이션 컨텍스트에서 Supabase 클라이언트를 가져오거나 생성합니다."""
    try:
        # Flask 애플리케이션 컨텍스트가 있는 경우
        from flask import g, current_app
        if hasattr(current_app, "_get_current_object") and hasattr(g, "_get_flashed_messages"):
            if not hasattr(g, 'supabase_client'):
                g.supabase_client = create_client(environ.get('supabase_url'), environ.get('supabase_key'))
            return g.supabase_client
    except (RuntimeError, ImportError):
        pass
    
    # Flask 애플리케이션 컨텍스트가 없거나 접근할 수 없는 경우, 
    # 직접 클라이언트 생성
    return create_client(environ.get('supabase_url'), environ.get('supabase_key'))

# FCM 메시지 전송 함수
def send_fcm_message(token, notification_data, data_fields):
    """
    개별 FCM 토큰에 메시지를 전송합니다.
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

# FCM 메시지 배치 전송 함수
async def send_fcm_messages_in_batch(tokens, notification_data, data_fields, batch_size=FCM_BATCH_SIZE):
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
                timeout=FCM_BATCH_TIMEOUT
            )
            all_results.extend(batch_results)
        except asyncio.TimeoutError:
            print(f"배치 FCM 메시지 전송 시간 초과 (배치 크기: {len(batch)})")
            # 타임아웃된 배치에 대한 결과는 None으로 처리
            all_results.extend([None] * len(batch))
    
    return all_results

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

# GMT 시간 변경 함수 (기존 base.py의 함수)
def changeGMTtime(time_str):
    time = datetime.fromisoformat(time_str)
    time += timedelta(hours=9)
    return time.isoformat()

# Firebase 초기화 함수
def initialize_firebase(firebase_initialized_globally=False):
    """Firebase 초기화 함수"""
    # 이미 전역 변수에서 초기화 완료 확인됨
    if firebase_initialized_globally:
        return True
        
    try:
        # 이미 초기화되었는지 확인
        get_app()
        print("Firebase 앱이 이미 초기화되어 있습니다.")
        return True
    except ValueError:
        # 초기화되지 않은 경우에만 초기화 진행
        try:
            # 환경 변수에서 Firebase 인증 정보 가져오기
            cred_dict = {
                "type": environ.get("FIREBASE_TYPE"),
                "project_id": environ.get("FIREBASE_PROJECT_ID"),
                "private_key_id": environ.get("FIREBASE_PRIVATE_KEY_ID"),
                "private_key": environ.get("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
                "client_email": environ.get("FIREBASE_CLIENT_EMAIL"),
                "client_id": environ.get("FIREBASE_CLIENT_ID"),
                "auth_uri": environ.get("FIREBASE_AUTH_URI"),
                "token_uri": environ.get("FIREBASE_TOKEN_URI"),
                "auth_provider_x509_cert_url": environ.get(
                    "FIREBASE_AUTH_PROVIDER_X509_CERT_URL"
                ),
                "client_x509_cert_url": environ.get("FIREBASE_CLIENT_X509_CERT_URL"),
                "universe_domain": environ.get("FIREBASE_UNIVERSE_DOMAIN"),
            }

            # 인증 정보 생성
            cred = credentials.Certificate(cred_dict)

            # 프로젝트 ID 가져오기
            project_id = cred.project_id or environ.get("FIREBASE_PROJECT_ID")

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
            return True
        except Exception as e:
            print(f"Firebase 초기화 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            return False

# 캐시를 활용한 최적화된 푸시 알림 전송 함수
async def cached_send_push_notification(messages, json_data, firebase_initialized_globally=False):
    """
    캐싱 기능을 사용하여 Supabase 쿼리를 최소화한 푸시 알림 전송 함수
    
    Args:
        messages: 웹훅 URL 목록
        json_data: 알림 데이터
        firebase_initialized_globally: Firebase 초기화 상태
    
    Returns:
        bool: 성공 여부
    """
    # Firebase 초기화 확인
    if not initialize_firebase(firebase_initialized_globally):
        print("Firebase 초기화 실패")
        return False
        
    try:
        # 성능 측정 시작
        start_time = datetime.now()
        total_users = len(messages)
        cache_hits = 0
        
        # 알림 ID와 시간 생성 (한 번만)
        notification_id = str(uuid4())
        notification_time = datetime.now(timezone.utc).isoformat()
        notification_time = changeGMTtime(notification_time)
        
        # 알림 데이터 준비
        notification_data = {
            "title": json_data.get("username", "알림"),
            "body": json_data.get("content", ""),
        }
        
        # 데이터 필드 준비
        data_fields = {
            "id": notification_id,
            "username": json_data.get("username", "알림"),
            "content": json_data.get("content", ""),
            "avatar_url": json_data.get("avatar_url", ""),
            "timestamp": notification_time,
            "read": False,
        }
        
        # embeds 추가 (있는 경우)
        if "embeds" in json_data and json_data["embeds"]:
            data_fields["embeds"] = json_data["embeds"]
            if json_data["embeds"][0].get("timestamp"):
                data_fields["embeds"][0]["timestamp"] = changeGMTtime(json_data["embeds"][0]["timestamp"])
        
        # Supabase 클라이언트 가져오기
        supabase = get_supabase_client()
        
        # 각 웹훅 URL에 대해 캐시 확인
        cached_users = {}
        urls_to_fetch = []
        
        for webhook_url in messages:
            cached_data = notification_cache.get_user_data(webhook_url)
            if cached_data:
                cached_users[webhook_url] = cached_data
                cache_hits += 1
            else:
                urls_to_fetch.append(webhook_url)
        
        # 캐시되지 않은 사용자만 Supabase에서 가져오기 (가능하면 일괄 처리)
        fetched_users = {}
        if urls_to_fetch:
            try:
                # IN 연산자로 일괄 조회
                result = supabase.table("userStateData").select("*").in_("discordURL", urls_to_fetch).execute()
                
                # 결과 처리
                for user_data in result.data:
                    webhook_url = user_data.get("discordURL")
                    if webhook_url:
                        fetched_users[webhook_url] = user_data
                        # 캐시 업데이트
                        notification_cache.set_user_data(webhook_url, user_data)
            except Exception as e:
                print(f"일괄 사용자 데이터 조회 실패: {e}")
                # 개별 조회로 대체
                for url in urls_to_fetch:
                    try:
                        result = supabase.table("userStateData").select("*").eq("discordURL", url).execute()
                        if result.data:
                            fetched_users[url] = result.data[0]
                            notification_cache.set_user_data(url, result.data[0])
                    except Exception as e2:
                        print(f"개별 사용자 조회 실패 ({url}): {e2}")
        
        # 캐시된 사용자와 새로 가져온 사용자 결합
        all_users = {**cached_users, **fetched_users}
        
        # 알림 처리 (배치로)
        notification_tasks = []
        fcm_tasks = []
        
        # 알림 업데이트 준비 (50명씩 배치 처리)
        user_batches = [list(all_users.items())[i:i+50] for i in range(0, len(all_users), 50)]
        
        for batch in user_batches:
            batch_dict = {url: data for url, data in batch}
            task = asyncio.create_task(
                batch_save_notifications(supabase, batch_dict, notification_id, data_fields)
            )
            notification_tasks.append(task)
        
        # FCM 토큰 처리 및 메시지 전송
        for webhook_url, user_data in all_users.items():
            # JSON 배열로 저장된 FCM 토큰 가져오기
            fcm_tokens = user_data.get("fcm_tokens", [])
            # 리스트가 아닌 경우(이전 문자열 형식) 처리
            if not isinstance(fcm_tokens, list):
                try:
                    if isinstance(fcm_tokens, str) and fcm_tokens:
                        # 문자열로 저장된 경우 파싱 시도
                        fcm_tokens = [t.strip() for t in fcm_tokens.split(",") if t.strip()]
                    else:
                        fcm_tokens = []
                except Exception:
                    fcm_tokens = []
            
            if not fcm_tokens:
                continue
            
            # FCM 메시지 배치 전송
            batch_task = asyncio.create_task(
                send_fcm_messages_in_batch(fcm_tokens, notification_data, data_fields)
            )
            fcm_tasks.append(batch_task)
        
        # FCM 작업 대기 (타임아웃 설정)
        if fcm_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*fcm_tasks, return_exceptions=True),
                    timeout=FCM_BATCH_TIMEOUT
                )
            except asyncio.TimeoutError:
                print(f"일부 FCM 메시지 작업 시간 초과 ({len(fcm_tasks)}개 배치)")
        
        # 알림 저장 작업 대기 (타임아웃 설정)
        if notification_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*notification_tasks, return_exceptions=True),
                    timeout=NOTIFICATION_SAVE_TIMEOUT
                )
            except asyncio.TimeoutError:
                print(f"일부 알림 저장 작업 시간 초과 ({len(notification_tasks)}개 배치)")
        
        # 성능 보고
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        fcm_token_count = sum(len(user_data.get("fcm_tokens", [])) 
                             for user_data in all_users.values() 
                             if isinstance(user_data.get("fcm_tokens"), list))
        
        print(f"푸시 알림 전송 완료: {len(all_users)}/{total_users}명 사용자, {fcm_token_count}개 토큰, "
              f"{cache_hits}개 캐시 적중, {duration:.2f}초 소요")
        
        return True
        
    except Exception as e:
        print(f"푸시 알림 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

# FCM 토큰 유효성 검사 함수
async def cleanup_invalid_fcm_token(token):
    """
    FCM 토큰이 유효한지 확인
    
    Args:
        token: 검사할 FCM 토큰
        
    Returns:
        bool: 유효하면 True, 아니면 False
    """
    if not token or not token.strip():
        return False
        
    try:
        # 테스트 메시지 생성 (실제로 전송하지 않음)
        message = messaging.Message(
            data={'validate': 'true'},
            token=token
        )
        # dry_run=True로 설정하여 실제 전송하지 않고 유효성만 확인
        messaging.send(message, dry_run=True)
        return True
    except messaging.UnregisteredError:
        # 앱 제거 또는 토큰 등록 취소됨
        return False
    except messaging.InvalidArgumentError:
        # 유효하지 않은 토큰 형식
        return False
    except Exception as e:
        print(f"토큰 검증 오류: {e}")
        # 알 수 없는 오류는 일단 유효하다고 가정 (오탐 방지)
        return True

# 사용자의 FCM 토큰 정리 함수
async def cleanup_user_tokens(user_data):
    """
    사용자의 FCM 토큰 목록에서 유효하지 않은 토큰 제거
    
    Args:
        user_data: 데이터베이스의 사용자 데이터
        
    Returns:
        tuple: (변경 여부, 업데이트된 토큰 목록)
    """
    fcm_tokens = user_data.get('fcm_tokens', [])
    
    # JSON 배열로 저장된 FCM 토큰 가져오기
    if not isinstance(fcm_tokens, list):
        try:
            if isinstance(fcm_tokens, str) and fcm_tokens:
                # 문자열로 저장된 경우 파싱 시도
                fcm_tokens = [t.strip() for t in fcm_tokens.split(",") if t.strip()]
            else:
                fcm_tokens = []
        except Exception:
            fcm_tokens = []
    
    if not fcm_tokens:
        return False, []
    
    original_count = len(fcm_tokens)
    
    # 각 토큰 검사
    validation_tasks = [cleanup_invalid_fcm_token(token) for token in fcm_tokens]
    validation_results = await asyncio.gather(*validation_tasks)
    
    # 유효한 토큰만 필터링
    valid_tokens = [token for token, is_valid in zip(fcm_tokens, validation_results) if is_valid]
    
    # 변경 사항 확인
    if len(valid_tokens) == original_count:
        return False, fcm_tokens  # 변경 없음
        
    # 업데이트된 토큰 목록 반환
    return True, valid_tokens

# 모든 사용자의 유효하지 않은 FCM 토큰 정리 함수 (스케줄러에서 호출)
async def cleanup_all_invalid_tokens():
    """
    모든 사용자의 유효하지 않은 FCM 토큰을 정리하는 예약 작업
    """
    print(f"{datetime.now()} FCM 토큰 정리 시작")
    start_time = datetime.now()
    
    try:
        # Supabase 클라이언트 가져오기
        from flask import current_app
        with current_app.app_context():
            supabase = get_supabase_client()
            
            # FCM 토큰이 있는 모든 사용자 가져오기
            result = supabase.table("userStateData").select("*").not_.is_("fcm_tokens", "null").execute()
            
            if not result.data:
                print("FCM 토큰이 있는 사용자가 없습니다")
                return
                
            # 사용자를 배치로 처리
            batch_size = 10
            user_batches = [result.data[i:i+batch_size] for i in range(0, len(result.data), batch_size)]
            
            total_users = len(result.data)
            updated_users = 0
            removed_tokens = 0
            
            for batch in user_batches:
                for user_data in batch:
                    if not user_data.get("fcm_tokens"):
                        continue
                    
                    # JSON 배열로 저장된 FCM 토큰 가져오기
                    fcm_tokens = user_data.get("fcm_tokens", [])
                    
                    # 현재 토큰 수 계산
                    if isinstance(fcm_tokens, list):
                        current_count = len(fcm_tokens)
                    elif isinstance(fcm_tokens, str):
                        current_count = len([t for t in fcm_tokens.split(",") if t.strip()])
                    else:
                        current_count = 0
                    
                    # 토큰 정리
                    changed, new_tokens = await cleanup_user_tokens(user_data)
                    
                    if changed:
                        # 새 토큰 수
                        new_count = len(new_tokens)
                        tokens_removed = current_count - new_count
                        
                        # 데이터베이스 업데이트
                        update_data = {
                            "fcm_tokens": new_tokens,  # JSON 배열로 저장
                            "last_token_update": datetime.now().isoformat()
                        }
                        
                        supabase.table("userStateData").update(update_data).eq(
                            "discordURL", user_data.get("discordURL")
                        ).execute()
                        
                        # 통계 업데이트
                        updated_users += 1
                        removed_tokens += tokens_removed
                        
                        # 이 사용자의 캐시 무효화
                        notification_cache.invalidate(user_data.get("discordURL"))
                
            # 요약 로깅
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            print(f"{datetime.now()} FCM 토큰 정리 완료: {total_users}명 확인, "
                  f"{updated_users}명 업데이트, {removed_tokens}개 토큰 제거, "
                  f"{duration:.2f}초 소요")
            
    except Exception as e:
        print(f"FCM 토큰 정리 오류: {e}")
        import traceback
        traceback.print_exc()

# 캐시 초기화 함수
def clear_notification_cache():
    """주기적으로 호출하여 캐시를 비웁니다"""
    global notification_cache
    notification_cache.invalidate()
    print(f"{datetime.now()} 알림 캐시가 초기화되었습니다")

# 알림 시스템 초기화 함수
def init_notification_system():
    """
    알림 시스템 초기화 함수
    - 캐시 초기화
    """
    global notification_cache
    notification_cache = NotificationCache()
    
    print("알림 시스템이 초기화되었습니다.")
    return notification_cache