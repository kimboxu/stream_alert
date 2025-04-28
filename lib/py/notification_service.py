import asyncio
from os import environ
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from firebase_admin import messaging, credentials, get_app, initialize_app
from concurrent.futures import ThreadPoolExecutor
from json import loads, dumps
from supabase import create_client
from base import initVar, if_after_time
from shared_state import StateManager
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from base import update_flag

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

# FCM 메시지 전송 함수
async def send_fcm_message(token, notification_data, data_fields):
    """
    개별 FCM 토큰에 메시지를 전송합니다.
    """
    try:
        # FCM은 모든 데이터 필드가 문자열이어야 함
        message_data = {k: str(v) if not isinstance(v, (list, dict)) else dumps(v) for k, v in data_fields.items()}
        
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
        # print(f"FCM 메시지 전송 성공: {token[:15]}... 결과: {result}")
        return result
    except messaging.UnregisteredError:
        print(f"FCM 토큰 등록 취소됨 (앱 제거): {token[:15]}...")
        await validate_fcm_token(token)
        return None
    except messaging.InvalidArgumentError as e:
        print(f"FCM 메시지 전송 실패 - 유효하지 않은 인자 (토큰: {token[:15]}...): {e}")
        await validate_fcm_token(token)
        return None
    except Exception as e:
        print(f"FCM 메시지 전송 실패 (토큰: {token[:15]}...): {e}")
        return None

# FCM 메시지 배치 전송 함수
async def send_fcm_messages_in_batch(tokens, notification_data, data_fields, batch_size=10):
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
            # 수정된 부분: await 없이 코루틴 객체 직접 생성
            task = asyncio.create_task(send_fcm_message(token, notification_data, data_fields))
            batch_tasks.append(task)
            
        # 배치 단위로 병렬 처리하되 타임아웃 설정
        try:
            batch_results = await asyncio.wait_for(
                asyncio.gather(*batch_tasks, return_exceptions=True),
                timeout=10
            )
            all_results.extend(batch_results)
        except asyncio.TimeoutError:
            print(f"배치 FCM 메시지 전송 시간 초과 (배치 크기: {len(batch)})")
            # 타임아웃된 배치에 대한 결과는 None으로 처리
            all_results.extend([None] * len(batch))
    
    return all_results

# 배치 알림 저장 함수
async def batch_save_notifications(init: initVar, user_data_map, notification_id, data_fields):
    """
    여러 사용자의 알림을 일괄 처리하고 init 변수에만 먼저 업데이트하고,
    DB 저장은 조건부로 실행합니다.
    
    Args:
        init: initVar 객체
        user_data_map: 웹훅 URL을 키로, 사용자 데이터를 값으로 하는 딕셔너리
        notification_id: 알림 고유 ID
        data_fields: 알림 데이터 필드
    """
    
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
        
        # 메모리의 init.userStateData 업데이트 (웹훅 URL이 인덱스에 있는 경우)
        if webhook_url in init.userStateData.index:
            # 로컬 데이터는 항상 업데이트
            init.userStateData.loc[webhook_url, 'notifications'] = notifications
            
            # DB 저장 결정을 위한 마지막 저장 시간 확인
            last_db_save = init.userStateData.loc[webhook_url].get('last_db_save_time')
            save_to_db = False
            
            # 마지막 저장 시간이 없거나 일정 시간(예: 15초)이 지났으면 DB에 저장
            if last_db_save is None or if_after_time(init.userStateData.loc[webhook_url, 'last_db_save_time'], 15):
                save_to_db = True
                init.userStateData.loc[webhook_url, 'last_db_save_time'] = datetime.now().astimezone().isoformat()
            
            # DB에 저장이 필요한 경우만 저장 실행
            if save_to_db:
                try:
                    # 비동기로 실행하되 에러 처리 추가
                    await asyncio.to_thread(
                        lambda: init.supabase.table('userStateData')
                              .upsert({
                                  'discordURL': webhook_url, 
                                  'notifications': init.userStateData.loc[webhook_url, 'notifications'],
                                  'last_db_save_time': init.userStateData.loc[webhook_url, 'last_db_save_time']})
                              .execute()
                    )
                    print(f"{datetime.now()} 알림을 DB에 저장함 - URL: {webhook_url}")
                except Exception as e:
                    print(f"{datetime.now()} 알림 저장 중 오류: {e} - URL: {webhook_url}")
            else:
                # print(f"{datetime.now()} 알림을 로컬에만 저장 (DB 저장 건너뜀) - URL: {webhook_url}")
                pass

# init에서 사용자 정보 추출
def get_user_data_from_init(init: initVar, webhook_url):
    """
    init 변수에서 주어진 webhook_url에 해당하는 사용자 데이터를 반환합니다.
    
    Args:
        init: initVar 객체
        webhook_url: 사용자의 디스코드 웹훅 URL
        
    Returns:
        dict: 사용자 데이터 객체
    """
    try:
        if webhook_url in init.userStateData.index:
            # 인덱스 기반으로 사용자 데이터 가져오기
            user_data = init.userStateData.loc[webhook_url].to_dict()
            return user_data
        return None
    except Exception as e:
        print(f"init에서 사용자 데이터 추출 오류: {e}")
        return None

# 푸시 알림 전송 함수
async def send_push_notification(webhook_urls, json_data, firebase_initialized_globally=True):
    """
    fcm_tokens_data만 사용하여 푸시 알림을 전송하는 함수
    
    Args:
        webhook_urls: 웹훅 URL 목록
        json_data: 알림 데이터
        firebase_initialized_globally: Firebase 초기화 상태
    
    Returns:
        bool: 성공 여부
    """
    # init 객체 가져오기
    state = StateManager.get_instance()
    init = state.get_init()
    if init is None: init = await state.initialize()

    # 성능 측정 시작
    start_time = datetime.now()
    recipient_count = len(webhook_urls)
    
    # Firebase 초기화 확인
    if not initialize_firebase(firebase_initialized_globally):
        print("Firebase 초기화 실패")
        return False
        
    try:
        # 알림 ID와 시간 생성 (한 번만)
        notification_id = str(uuid4())
        notification_time = datetime.now().astimezone().isoformat()
        
        # 알림 데이터 준비
        notification_data = {
            "title": json_data.get("username", "(알 수 없음)"),
            "body": json_data.get("content", ""),
        }
        
        # 데이터 필드 준비
        data_fields = {
            "id": notification_id,
            "username": json_data.get("username", "(알 수 없음)"),
            "content": json_data.get("content", ""),
            "avatar_url": json_data.get("avatar_url", ""),
            "timestamp": notification_time,
            "read": False,
        }
        
        # embeds 추가 (있는 경우)
        if "embeds" in json_data and json_data["embeds"]:
            data_fields["embeds"] = json_data["embeds"]
        
        # init에서 사용자 데이터 수집
        all_users = {}
        missing_users = []
        
        for webhook_url in webhook_urls:
            user_data = get_user_data_from_init(init, webhook_url)
            if user_data:
                all_users[webhook_url] = user_data
            else:
                missing_users.append(webhook_url)
        
        # 누락된 사용자가 있으면 Supabase에서 직접 가져오기
        if missing_users:
            try:
                # IN 연산자로 일괄 조회
                result = init.supabase.table("userStateData").select("*").in_("discordURL", missing_users).execute()
                
                # 결과 처리
                for user_data in result.data:
                    webhook_url = user_data.get("discordURL")
                    if webhook_url:
                        all_users[webhook_url] = user_data
            except Exception as e:
                print(f"누락된 사용자 데이터 조회 실패: {e}")
        
        # 알림 처리 (배치로)
        notification_tasks = []
        fcm_tasks = []
        
        # 알림 업데이트 준비 (50명씩 배치 처리)
        user_batches = [list(all_users.items())[i:i+50] for i in range(0, len(all_users), 50)]
        
        for batch in user_batches:
            batch_dict = {url: data for url, data in batch}
            task = asyncio.create_task(
                batch_save_notifications(init, batch_dict, notification_id, data_fields)
            )
            notification_tasks.append(task)
        
        # FCM 토큰 처리 및 메시지 전송 - 간소화된 방식
        for webhook_url, user_data in all_users.items():
            # 개선된 형식의 토큰 데이터 가져오기
            tokens_data = user_data.get("fcm_tokens_data", [])
            
            if not tokens_data or not isinstance(tokens_data, list):
                continue
                
            # 토큰만 추출 (중복 없이)
            fcm_tokens = []
            seen_tokens = set()
            
            for item in tokens_data:
                token = item.get("token")
                if token and token not in seen_tokens:
                    fcm_tokens.append(token)
                    seen_tokens.add(token)
            
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
                    timeout=10
                )
            except asyncio.TimeoutError:
                print(f"일부 FCM 메시지 작업 시간 초과 ({len(fcm_tasks)}개 배치)")
        
        # 알림 저장 작업 대기 (타임아웃 설정)
        if notification_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*notification_tasks, return_exceptions=True),
                    timeout=10
                )
            except asyncio.TimeoutError:
                print(f"일부 알림 저장 작업 시간 초과 ({len(notification_tasks)}개 배치)")
        
        # 성능 보고
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        return True
        
    except Exception as e:
        print(f"푸시 알림 오류: {e}")
        import traceback
        traceback.print_exc()
        return False
    
# FCM 토큰 유효성 검사 함수
async def validate_fcm_token(token):
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
    
    if not fcm_tokens:
        return False, []
    
    original_count = len(fcm_tokens)
    
    # 각 토큰 검사
    validation_tasks = [validate_fcm_token(token) for token in fcm_tokens]
    validation_results = await asyncio.gather(*validation_tasks)
    
    # 유효한 토큰만 필터링
    valid_tokens = [token for token, is_valid in zip(fcm_tokens, validation_results) if is_valid]
    
    # 변경 사항 확인
    if len(valid_tokens) == original_count:
        return False, fcm_tokens  # 변경 없음
        
    # 업데이트된 토큰 목록 반환
    return True, valid_tokens

# 모든 사용자의 유효하지 않은 FCM 토큰 정리 함수
async def cleanup_all_invalid_tokens():
    """
    모든 사용자의 유효하지 않은 토큰을 정리하는 함수 (간소화)
    """
    print(f"{datetime.now()} FCM 토큰 정리 시작")
    start_time = datetime.now()
    
    try:
        # init 객체 가져오기
        state = StateManager.get_instance()
        init = state.get_init()

        if init is None: init = await state.initialize()
                           
        # 사용자를 배치로 처리
        total_users = len(init.userStateData)
        updated_users = 0
        removed_tokens = 0
        
        # 데이터프레임의 각 행을 사전으로 변환하여 처리
        for webhook_url, user_row in init.userStateData.iterrows():
            # 사전으로 변환
            user_data = user_row.to_dict()
            
            # fcm_tokens_data 확인
            tokens_data = user_data.get("fcm_tokens_data", [])
            if not tokens_data or not isinstance(tokens_data, list):
                continue
            
            # 현재 토큰 수 계산
            current_count = len(tokens_data)
            
            # 토큰 정리
            changed, new_tokens_data = await cleanup_user_tokens(user_data)
            
            if changed:
                # 새 토큰 수
                new_count = len(new_tokens_data)
                tokens_removed = current_count - new_count
                
                # 저장
                save_tokens_data(init, webhook_url, new_tokens_data)
                
                # 통계 업데이트
                updated_users += 1
                removed_tokens += tokens_removed
                
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
# 예약 작업 설정 함수 추가
def setup_scheduled_tasks():
    """주기적인 백그라운드 작업 설정"""
    scheduler = BackgroundScheduler()
    
    # 유효하지 않은 FCM 토큰을 매일 정리 (트래픽이 적은 시간에)
    scheduler.add_job(
        func=lambda: asyncio.run(cleanup_all_invalid_tokens()),
        trigger="cron",
        hour=3,  # 새벽 3시
        minute=0
    )
    
    scheduler.start()
    
    # 앱 종료 시 스케줄러 종료
    atexit.register(lambda: scheduler.shutdown())

# 토큰 데이터 저장 함수
def save_tokens_data(init, discordWebhooksURL, tokens_data):
    """
    토큰 데이터를 저장하는 함수
    
    Args:
        init: 초기화 객체
        discordWebhooksURL: 디스코드 웹훅 URL
        tokens_data: 토큰 데이터 리스트
    """
    last_token_update = datetime.now().astimezone().isoformat()
    
    # fcm_tokens_data만 저장
    init.userStateData.loc[discordWebhooksURL, "fcm_tokens_data"] = tokens_data
    init.userStateData.loc[discordWebhooksURL, "last_token_update"] = last_token_update

    # Supabase에 저장
    init.supabase.table("userStateData").upsert({
        "discordURL": discordWebhooksURL,
        "fcm_tokens_data": tokens_data,
        "last_token_update": last_token_update,
    }).execute()
    
    # 사용자 데이터 변경 플래그 설정
    # asyncio.run(update_flag('user_date', True))