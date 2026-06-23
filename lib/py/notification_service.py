import os
import json
import atexit
import asyncio
import hashlib
import tempfile
import threading
from uuid import uuid4
from pathlib import Path
from json import loads, dumps
from datetime import datetime, timedelta
from firebase_admin import messaging, credentials, get_app, initialize_app
from apscheduler.schedulers.background import BackgroundScheduler

from shared_state import StateManager
from base import initVar, if_after_time, get_online_count
from make_log_api_performance import PerformanceManager

def sanitize_data_for_json(data):
    """ JSON 직렬화 데이터 정리"""
    import inspect
    
    def _sanitize_recursive(obj, depth=0, max_depth=10):
        if depth > max_depth:
            return str(obj)
            
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                try:
                    result[k] = _sanitize_recursive(v, depth + 1, max_depth)
                except (TypeError, ValueError, RecursionError, MemoryError):
                    result[k] = str(v)
            return result
            
        elif isinstance(obj, list):
            result = []
            for item in obj:
                try:
                    result.append(_sanitize_recursive(item, depth + 1, max_depth))
                except (TypeError, ValueError, RecursionError, MemoryError):
                    result.append(str(item))
            return result
            
        elif asyncio.iscoroutine(obj):
            return str(obj)
        elif inspect.isgenerator(obj):
            return f"<generator: {type(obj).__name__}>"
        elif callable(obj):
            return str(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            try:
                return _sanitize_recursive(obj.__dict__, depth + 1, max_depth)
            except:
                return str(obj)
        else:
            try:
                import json
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return str(obj)
    
    try:
        result = _sanitize_recursive(data)
        
        # 대용량 데이터 처리 후 가비지 컬렉션
        # if isinstance(data, (list, dict)) and len(str(data)) > 50000:  # 50KB 이상
        #     import gc
            # gc.collect()
            
        return result
        
    except Exception as e:
        print(f"데이터 정리 중 오류: {str(e)}")
        return {"error": "데이터 정리 실패", "original_type": str(type(data))}
    
notification_queue = None

async def initialize_notification_queue():
    """알림 큐 초기화"""
    global notification_queue
    if notification_queue is None:
        notification_queue = asyncio.Queue(maxsize=5000)  # 최대 5000개 대기
    return notification_queue

async def notification_worker():
    """
    별도 작업자가 알림을 천천히 저장
    메인 I/O 부하를 분산시킴
    """
    global notification_queue, file_notification_manager
    
    # print(f"{datetime.now()} 알림 저장 워커 시작")
    
    while True:
        try:
            # 큐에서 작업 가져오기 (타임아웃 60초)
            webhook_url, notification_data = await asyncio.wait_for(
                notification_queue.get(),
                timeout=60
            )
            
            try:
                # 실제 저장 작업
                await file_notification_manager.add_notification(
                    webhook_url,
                    notification_data
                )
                
                # 작은 지연으로 I/O 분산
                await asyncio.sleep(0.02)
                
            except Exception as e:
                print(f"{datetime.now()} 알림 저장 실패 ({webhook_url}): {str(e)}")
            
            finally:
                # 작업 완료 표시
                notification_queue.task_done()
                
        except asyncio.TimeoutError:
            # 60초 동안 작업이 없으면 계속
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            print(f"{datetime.now()} 알림 저장 워커 중지")
            break
        except Exception as e:
            print(f"{datetime.now()} 알림 워커 예외: {str(e)}")
            await asyncio.sleep(1)

class FileNotificationManager:
    """파일 기반 사용자 알림 관리 클래스"""
    
    def __init__(self):
        # 프로젝트 루트 디렉토리 찾기
        current_file = Path(__file__)
        if current_file.parent.name == 'py':
            project_root = current_file.parent.parent
        else:
            project_root = current_file.parent
        
        self.data_dir = project_root / "data"
        self.notifications_dir = self.data_dir / "user_notifications"
        self.notifications_dir.mkdir(parents=True, exist_ok=True)
        
        # 캐시된 알림 데이터 (메모리 최적화를 위해)
        self.notification_cache = {}
        self.last_save_times = {}
        
        # 스레드 안전성을 위한 락
        self._cache_lock = threading.RLock()  # 재진입 가능한 락
    
    def _get_file_path(self, webhook_url: str) -> Path:
        """웹훅 URL에서 안전한 파일명 생성"""
        # URL을 해시화하여 안전한 파일명 생성
        url_hash = hashlib.md5(webhook_url.encode()).hexdigest()
        return self.notifications_dir / f"notifications_{url_hash}.json"
    
    def _get_backup_file_path(self, webhook_url: str) -> Path:
        """백업 파일 경로 생성"""
        url_hash = hashlib.md5(webhook_url.encode()).hexdigest()
        return self.notifications_dir / f"notifications_{url_hash}_backup.json"
    
    def load_notifications(self, webhook_url: str) -> list:
        """사용자 알림 데이터 로드"""
        try:
            with self._cache_lock:
                # 캐시에서 먼저 확인
                if webhook_url in self.notification_cache:
                    return self.notification_cache[webhook_url].copy()
            
            file_path = self._get_file_path(webhook_url)
            
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    notifications = data.get('notifications', [])
                    
                    # 캐시에 저장
                    with self._cache_lock:
                        self.notification_cache[webhook_url] = notifications.copy()
                        self.last_save_times[webhook_url] = data.get('last_save_time')
                    
                    return notifications.copy()
            
            # 파일이 없으면 빈 리스트 반환
            with self._cache_lock:
                self.notification_cache[webhook_url] = []
            return []
            
        except Exception as e:
            print(f"알림 데이터 로드 오류 ({webhook_url}): {str(e)}")
            # 백업 파일에서 복구 시도
            return self._load_from_backup(webhook_url)
    
    def _load_from_backup(self, webhook_url: str) -> list:
        """백업 파일에서 데이터 복구"""
        try:
            backup_path = self._get_backup_file_path(webhook_url)
            if backup_path.exists():
                with open(backup_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    notifications = data.get('notifications', [])
                    print(f"백업 파일에서 알림 데이터 복구 성공: {webhook_url}")
                    return notifications
        except Exception as e:
            print(f"백업 파일 복구 실패 ({webhook_url}): {str(e)}")
        
        return []
    
    async def save_notifications(self, webhook_url: str, notifications: list, force_save: bool = False) -> bool:
        """사용자 알림 데이터 저장"""
        try:
            # current_time = datetime.now().astimezone().isoformat()
            current_time = datetime.now().isoformat()

            # 강제 저장이 아닌 경우 시간 간격 확인 (5분)
            if not force_save:
                with self._cache_lock:
                    last_save = self.last_save_times.get(webhook_url)
                if last_save and not if_after_time(last_save, 300):
                    with self._cache_lock:
                        self.notification_cache[webhook_url] = notifications.copy()
                    return True
            
            file_path = self._get_file_path(webhook_url)
            backup_path = self._get_backup_file_path(webhook_url)
            
            # 디렉토리 존재 확인 및 생성
            self.notifications_dir.mkdir(parents=True, exist_ok=True)
            
            # 기존 파일 백업
            if file_path.exists():
                try:
                    import shutil
                    shutil.copy2(file_path, backup_path)
                    del shutil
                except Exception as e:
                    print(f"백업 파일 생성 실패 ({webhook_url}): {str(e)}")
            
            # 알림 데이터를 JSON 직렬화 가능하도록 정리
            clean_notifications = sanitize_data_for_json(notifications)
            
            # 원본 notifications 해제
            del notifications
            
            # 저장할 데이터 구조 생성
            save_data = {
                'webhook_url': webhook_url,
                'notifications': clean_notifications,
                'last_save_time': current_time,
                'notification_count': len(clean_notifications)
            }
            
            # 임시 파일에 저장
            temp_fd = None
            temp_path = None
            
            try:
                # 같은 디렉토리에 임시 파일 생성
                temp_fd, temp_path_str = tempfile.mkstemp(
                    suffix='.tmp',
                    prefix='notifications_',
                    dir=self.notifications_dir,
                    text=True
                )
                temp_path = Path(temp_path_str)
                await asyncio.sleep(0.001)
                
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                temp_fd = None
                
                # 파일 쓰기 완료 후 메모리 정리
                del save_data
                
                if len(clean_notifications) > 3000:
                    import gc
                    # gc.collect()
                
                # 임시 파일이 정상적으로 생성되었는지 확인
                if not temp_path.exists() or temp_path.stat().st_size == 0:
                    raise IOError(f"임시 파일 생성 실패 또는 빈 파일: {temp_path}")
                
                # 임시 파일을 실제 파일로 이동 (원자적 연산)
                try:
                    if os.name == 'nt' and file_path.exists():
                        file_path.unlink()
                    temp_path.replace(file_path)
                    
                except (OSError, PermissionError) as e:
                    # replace 실패 시 대체 방법 시도
                    print(f"파일 이동(replace) 실패, 복사 후 삭제 방식 시도: {str(e)}")
                    import shutil
                    shutil.copy2(temp_path, file_path)
                    
                    # 복사 성공 확인
                    if not file_path.exists() or file_path.stat().st_size == 0:
                        raise IOError("파일 복사 후 검증 실패")
                        
                    # 복사 성공 후 임시 파일 삭제
                    try:
                        temp_path.unlink()
                    except Exception as unlink_error:
                        print(f"임시 파일 삭제 실패 (무시 가능): {unlink_error}")
                        
                    del shutil
                
            except Exception as e:
                # 임시 파일 정리
                if temp_fd is not None:
                    try:
                        os.close(temp_fd)
                    except:
                        pass
                        
                if temp_path and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception as cleanup_error:
                        print(f"임시 파일 정리 실패: {cleanup_error}")
                raise e
            
            # 캐시 업데이트
            with self._cache_lock:
                self.notification_cache[webhook_url] = clean_notifications
                self.last_save_times[webhook_url] = current_time
            
            # print(f"{datetime.now()} 알림을 파일에 저장함 - URL: {webhook_url}, 개수: {len(clean_notifications)}")
            del clean_notifications
            
            return True
            
        except Exception as e:
            print(f"{datetime.now()} 알림 파일 저장 오류 ({webhook_url}): {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 오류 발생시 메모리 정리
            # import gc
            # gc.collect()
            
            return False
   
    async def add_notification(self, webhook_url: str, notification_data: dict) -> bool:
        """알림 추가"""
        try:
            notifications = self.load_notifications(webhook_url)
            
            # 중복 확인 (ID 기반)
            notification_id = notification_data.get('id')
            if notification_id:
                # 기존 알림 중에 같은 ID가 있으면 업데이트
                for idx, existing in enumerate(notifications):
                    if existing.get('id') == notification_id:
                        notifications[idx] = notification_data
                        return await self.save_notifications(webhook_url, notifications)
            
            # 새 알림 추가
            notifications.append(notification_data)
            
            # 알림 개수 제한 (최신 100000개만 유지), 전체 알림 테스트 1달이 4500개, 10,000개면 충분
            if len(notifications) > 100000:
                notifications = notifications[-100000:]
            
            return await self.save_notifications(webhook_url, notifications)
            
        except Exception as e:
            print(f"알림 추가 오류 ({webhook_url}): {str(e)}")
            return False
    
    def get_notification_count(self, webhook_url: str) -> int:
        """사용자의 총 알림 개수 반환"""
        notifications = self.load_notifications(webhook_url)
        return len(notifications)
    
    async def cleanup_old_notifications(self, webhook_url: str, max_age_days: int = 10) -> bool:
        """오래된 알림 정리"""
        try:
            notifications = self.load_notifications(webhook_url)
            if not notifications:
                return True
            
            original_count = len(notifications)
            cutoff_time = datetime.now().astimezone() - timedelta(days=max_age_days)
            
            # 최근 알림만 유지
            filtered_notifications = []

            batch_size = 1000  # 1000개씩 처리
            for i in range(0, len(notifications), batch_size):
                batch = notifications[i:i + batch_size]

                for notification in batch:
                    try:
                        timestamp_str = notification.get('timestamp', '')
                        if timestamp_str:
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

                            if timestamp > cutoff_time:
                                filtered_notifications.append(notification)
                    except Exception as e:
                        # 타임스탬프 파싱 실패시 유지
                        filtered_notifications.append(notification)

                await asyncio.sleep(0.01)  # 제어권만 반환
                
            if len(filtered_notifications) != len(notifications):
                # print(f"{datetime.now()} {webhook_url}: {original_count}개 -> {len(filtered_notifications)}개로 정리")
                return await self.save_notifications(webhook_url, filtered_notifications, force_save=True)
                
            return True
            
        except Exception as e:
            print(f"오래된 알림 정리 오류 ({webhook_url}): {str(e)}")
            return False
    
    async def force_save_all_cache(self):
        """메모리 캐시 전체 저장"""
        saved_count = 0
        failed_count = 0
        
        try:
            # print(f"{datetime.now()} 캐시 강제 저장 시작")
            
            # 캐시 내용을 배치로 처리
            with self._cache_lock:
                cache_items = list(self.notification_cache.items())
            
            batch_size = 10
            
            for i in range(0, len(cache_items), batch_size):
                batch = cache_items[i:i + batch_size]
                
                for webhook_url, notifications in batch:
                    try:
                        if await self.save_notifications(webhook_url, notifications.copy(), force_save=True):
                            saved_count += 1
                        else:
                            failed_count += 1
                    except Exception as e:
                        print(f"사용자 {webhook_url} 저장 실패: {str(e)}")
                        failed_count += 1
                
                # 배치 처리 후 메모리 정리
                del batch
                
                # 주기적으로 가비지 컬렉션 실행
                if i > 0 and i % (batch_size * 5) == 0:  # 50개마다
                    import gc
                    # gc.collect()
                    
                # 배치 간 잠깐 대기
                await asyncio.sleep(0.01)
            
            # print(f"{datetime.now()} 캐시된 알림 데이터 강제 저장 완료: {saved_count}개 성공, {failed_count}개 실패")
            
            return saved_count
            
        except Exception as e:
            print(f"전체 캐시 저장 중 오류: {str(e)}")
            import gc
            gc.collect()
            return saved_count 

file_notification_manager = FileNotificationManager()

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
                print(f"{datetime.now()} Firebase 프로젝트 ID를 찾을 수 없습니다.")
                return False

            # Firebase 앱 초기화 (한 번만 호출)
            initialize_app(
                cred,
                {
                    "projectId": project_id,
                },
            )

            print(f"{datetime.now()} Firebase 앱이 프로젝트 ID '{project_id}'로 성공적으로 초기화되었습니다.")
            return True
        except Exception as e:
            print(f"{datetime.now()} Firebase 초기화 중 오류 발생: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

# FCM 메시지 전송 함수
async def send_fcm_message(performance_manager: PerformanceManager , token, notification_data, data_fields):
    """
    개별 FCM 토큰에 메시지를 전송합니다.
    """
    start_time = datetime.now()
    
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
        
        end_time = datetime.now()
        response_time_ms = int((end_time - start_time).total_seconds() * 1000)

        # 성공 로깅
        asyncio.create_task(performance_manager.log_api_performance(
                api_type='fcm_push',
                response_time_ms=response_time_ms,
                is_success=True,
        ))
        
        # print(f"{datetime.now()} FCM 메시지 전송 성공: {token[:15]}... 결과: {result}, 응답시간: {response_time_ms/1000:.3f}초")
        return result
        
    except messaging.UnregisteredError:
        end_time = datetime.now()
        response_time_ms = int((end_time - start_time).total_seconds() * 1000)
        asyncio.create_task(performance_manager.log_api_performance(
            api_type='fcm_push',
            response_time_ms=response_time_ms,
            is_success=False,
            error_type='UnregisteredError',
            error_message='토큰이 등록 취소됨'
        ))

        remove_fcm_token(token)
        return None
        
    except messaging.InvalidArgumentError as e:
        end_time = datetime.now()
        response_time_ms = int((end_time - start_time).total_seconds() * 1000)

        # 잘못된 인수 로깅
        asyncio.create_task(performance_manager.log_api_performance(
            api_type='fcm_push',
            response_time_ms=response_time_ms,
            is_success=False,
            error_type='InvalidArgumentError',
            error_message=str(e)
        ))

        print(f"{datetime.now()} FCM 메시지 전송 실패 - 유효하지 않은 인자 (토큰: {token}): {str(e)}")
        remove_fcm_token(token)
        return None
    
    except messaging.QuotaExceededError as e:
        end_time = datetime.now()
        response_time_ms = int((end_time - start_time).total_seconds() * 1000)
        
        # 할당량 초과 로깅
        asyncio.create_task(performance_manager.log_api_performance(
            api_type='fcm_push',
            response_time_ms=response_time_ms,
            is_success=False,
            error_type='QuotaExceededError',
            error_message=str(e)
        ))

        print(f"{datetime.now()} FCM 할당량 초과: {token[:15]}... 오류: {str(e)}")
        return None

    except Exception as e:
        end_time = datetime.now()
        response_time_ms = int((end_time - start_time).total_seconds() * 1000)
        
        # 기타 예외 로깅
        asyncio.create_task(performance_manager.log_api_performance(
            api_type='fcm_push',
            response_time_ms=response_time_ms,
            is_success=False,
            error_type=type(e).__name__,
            error_message=str(e)
        ))

        print(f"{datetime.now()} FCM 메시지 전송 실패: {token[:15]}... 오류: {str(e)}")
        return None

# FCM 메시지 배치 전송 함수
async def send_fcm_messages_in_batch(performance_manager: PerformanceManager, tokens, notification_data, data_fields, batch_size=10):
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
            task = asyncio.create_task(send_fcm_message(performance_manager, token, notification_data, data_fields))
            batch_tasks.append(task)
            
        # 배치 단위로 병렬 처리하되 타임아웃 설정
        try:
            batch_results = await asyncio.wait_for(
                asyncio.gather(*batch_tasks, return_exceptions=True),
                timeout=10
            )
            all_results.extend(batch_results)
        except asyncio.TimeoutError:
            print(f"{datetime.now()} 배치 FCM 메시지 전송 시간 초과 (배치 크기: {len(batch)})")
            # 타임아웃된 배치에 대한 결과는 None으로 처리
            all_results.extend([None] * len(batch))
    
    return all_results

# 배치 알림 저장 함수
async def batch_save_notifications(user_data_map, data_fields):
    """
    여러 사용자의 알림을 큐에 추가 
    실제 저장은 notification_worker가 백그라운드에서 처리
    """
    global notification_queue, file_notification_manager
    
    if notification_queue is None:
        print(f"{datetime.now()} 경고: notification_queue가 초기화되지 않았습니다")
        # 폴백: 직접 저장 (느림)
        await _batch_save_notifications_direct(user_data_map, data_fields)
        return [True] * len(user_data_map)
    
    queued_count = 0
    skipped_count = 0
    
    # 데이터 정리는 한 번만
    clean_data_fields = sanitize_data_for_json(data_fields)
    
    for webhook_url, user_data in user_data_map.items():
        try:
            # 큐에 추가 (논블로킹)
            if notification_queue.full():
                print(f"{datetime.now()} 경고: 알림 큐가 가득 찼습니다 ({notification_queue.qsize()})")
                skipped_count += 1
                continue
            
            # 큐에 추가
            notification_queue.put_nowait((webhook_url, clean_data_fields))
            queued_count += 1
            
        except asyncio.QueueFull:
            print(f"{datetime.now()} 알림 큐 오버플로우: {webhook_url}")
            skipped_count += 1
        except Exception as e:
            print(f"{datetime.now()} 알림 큐 추가 실패 ({webhook_url}): {str(e)}")
            skipped_count += 1
    
    # print(f"{datetime.now()} 알림 배치 처리: "
    #     f"{queued_count}개 큐에 추가, {skipped_count}개 스킵, "
    #     f"현재 큐 크기: {notification_queue.qsize()}")
    
    # 큐에만 추가했으므로 모두 True 반환 (실제 저장은 워커가 함)
    return [True] * len(user_data_map)


async def _batch_save_notifications_direct(user_data_map, data_fields):
    """
    폴백: 큐 없이 직접 저장 (느림 - 피해야 함)
    """
    global file_notification_manager
    
    save_results = []
    clean_data_fields = sanitize_data_for_json(data_fields)
    
    for webhook_url, user_data in user_data_map.items():
        try:
            # 캐시에 있으면 파일 안 읽음
            if webhook_url in file_notification_manager.notification_cache:
                notifications = file_notification_manager.notification_cache[webhook_url].copy()
            else:
                notifications = file_notification_manager.load_notifications(webhook_url)
            
            # 추가
            notifications.append(clean_data_fields)
            
            # 최대 개수 제한
            if len(notifications) > 100000:
                notifications = notifications[-100000:]
            
            # 저장
            result = await file_notification_manager.save_notifications(
                webhook_url,
                notifications
            )
            save_results.append(result)
            
            # 작은 지연
            await asyncio.sleep(0.01)
            
        except Exception as e:
            print(f"{datetime.now()} 알림 저장 오류 ({webhook_url}): {str(e)}")
            save_results.append(False)
    
    return save_results

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
        print(f"{datetime.now()} init에서 사용자 데이터 추출 오류: {str(e)}")
        return None

def get_notification_data(json_data):
    # 알림 데이터 준비 부분 수정
    notification_data = {
    "title": json_data.get("username", "(알 수 없음)"),
    "body": "",
    }

    body = json_data.get("content", "")

    # embeds 데이터가 있으면 확인
    if "embeds" in json_data and json_data["embeds"]:
        try:
            embeds = json_data["embeds"]

            if isinstance(embeds, list) and embeds and isinstance(embeds[0], dict):
                if "title" in embeds[0] and embeds[0]["title"]:
                    body = embeds[0]["title"]
                elif "description" in embeds[0] and embeds[0]["description"]:
                    body = embeds[0]["description"]
        except Exception as e:
            print(f"{datetime.now()} embeds 데이터 파싱 오류: {str(e)}")
    if not body:
        body = "새 알림이 도착했습니다"

    # 업데이트된 body 설정
    notification_data["body"] = body
    return notification_data

# 푸시 알림 전송 함수
async def send_push_notification(webhook_urls, json_data, firebase_initialized_globally=True):
    """
    파일 기반 저장을 사용하는 푸시 알림 전송 함수
    """
    global notification_queue, file_notification_manager
    
    # 초기화
    state = StateManager.get_instance()
    init = state.get_init()
    performance_manager = state.get_performance_manager()
    init = await state.initialize()
    
    # 큐 초기화 확인
    if notification_queue is None:
        notification_queue = await initialize_notification_queue()
    
    try:
        # 알림 ID와 시간
        notification_id = str(uuid4())
        notification_time = datetime.now().astimezone().isoformat()
        
        # 알림 데이터 준비
        notification_data = get_notification_data(json_data)
        
        # 데이터 필드 준비
        data_fields = {
            "id": notification_id,
            "username": json_data.get("username", "(알 수 없음)"),
            "content": json_data.get("content", ""),
            "avatar_url": json_data.get("avatar_url", ""),
            "timestamp": notification_time,
            "read": False,
        }
        
        if "embeds" in json_data and json_data["embeds"]:
            data_fields["embeds"] = json_data["embeds"]
        
        # JSON 직렬화 가능하도록 정리
        data_fields = sanitize_data_for_json(data_fields)
        
        # 사용자 데이터 수집
        all_users = {}
        missing_users = []
        
        for webhook_url in webhook_urls:
            user_data = get_user_data_from_init(init, webhook_url)
            if user_data:
                all_users[webhook_url] = user_data
            else:
                missing_users.append(webhook_url)
        
        # 누락된 사용자는 Supabase에서 가져오기
        if missing_users:
            try:
                result = init.supabase.table("userStateData").select("*").in_("discordURL", missing_users).execute()
                for user_data in result.data:
                    webhook_url = user_data.get("discordURL")
                    if webhook_url:
                        all_users[webhook_url] = user_data
            except Exception as e:
                print(f"{datetime.now()} 누락된 사용자 데이터 조회 실패: {str(e)}")
        
        # print(f"{datetime.now()} 알림 전송 시작: {len(all_users)}명의 사용자")
        
        # 파일 기반 알림 저장 (큐에 추가만 함)
        await batch_save_notifications(all_users, data_fields)
        
        # FCM 토큰 처리
        fcm_tasks = []
        
        for webhook_url, user_data in all_users.items():
            tokens_data = user_data.get("fcm_tokens_data", [])
            
            if not tokens_data or not isinstance(tokens_data, list):
                continue
            
            # 토큰 추출
            fcm_tokens = []
            seen_tokens = set()
            
            for item in tokens_data:
                token = item.get("token")
                if token and token not in seen_tokens:
                    fcm_tokens.append(token)
                    seen_tokens.add(token)
            
            if not fcm_tokens:
                continue
            
            # FCM 배치 전송
            batch_task = asyncio.create_task(
                send_fcm_messages_in_batch(
                    performance_manager,
                    fcm_tokens,
                    notification_data,
                    data_fields
                )
            )
            fcm_tasks.append(batch_task)
        
        # FCM 작업 대기
        if fcm_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*fcm_tasks, return_exceptions=True),
                    timeout=10
                )
            except asyncio.TimeoutError:
                print(f"{datetime.now()} 일부 FCM 메시지 작업 시간 초과 ({len(fcm_tasks)}개 배치)")
        
        # print(f"{datetime.now()} 알림 전송 완료")
        return True
        
    except Exception as e:
        print(f"{datetime.now()} 파일 기반 푸시 알림 오류: {str(e)}")
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
        print(f"{datetime.now()} 토큰 검증 오류: {str(e)}")
        # 알 수 없는 오류는 일단 유효하다고 가정 (오탐 방지)
        return True

# 사용자의 FCM 토큰 정리 함수
async def cleanup_user_tokens(user_data):
    """FCM 토큰 정리"""
    tokens_data = user_data.get("fcm_tokens_data", [])
    
    if not tokens_data or not isinstance(tokens_data, list):
        return False, []
    
    # 토큰만 추출
    tokens = []
    for item in tokens_data:
        if isinstance(item, dict) and item.get("token"):
            tokens.append(item.get("token"))
    
    if not tokens:
        return False, tokens_data
    
    original_count = len(tokens)
    
    batch_size = 20
    valid_tokens = set()
    
    for i in range(0, len(tokens), batch_size):
        batch_tokens = tokens[i:i + batch_size]
        validation_tasks = [validate_fcm_token(token) for token in batch_tokens]
        
        try:
            validation_results = await asyncio.wait_for(
                asyncio.gather(*validation_tasks, return_exceptions=True),
                timeout=30
            )
            
            # 유효한 토큰만 필터링
            for token, is_valid in zip(batch_tokens, validation_results):
                if isinstance(is_valid, bool) and is_valid:
                    valid_tokens.add(token)
                elif isinstance(is_valid, Exception):
                    # 예외 발생시 유효하다고 가정
                    valid_tokens.add(token)
                    
        except asyncio.TimeoutError:
            print(f"토큰 검증 타임아웃 - 배치를 유효하다고 가정")
            valid_tokens.update(batch_tokens)
        
        # 배치 간 CPU 양보
        await asyncio.sleep(0.1)
    
    # 원본 tokens_data에서 유효한 토큰만 필터링
    filtered_tokens_data = [
        item for item in tokens_data 
        if isinstance(item, dict) and item.get("token") in valid_tokens
    ]
    
    # 변경 사항 확인
    if len(filtered_tokens_data) == original_count:
        return False, tokens_data
        
    return True, filtered_tokens_data

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
        print(f"{datetime.now()} FCM 토큰 정리 오류: {str(e)}")
        import traceback
        traceback.print_exc()

# 예약 작업 설정 함수
def setup_scheduled_tasks():
    """주기적인 백그라운드 작업 설정"""
    scheduler = BackgroundScheduler()
    
    # 유효하지 않은 FCM 토큰을 매일 정리 (트래픽이 적은 시간에)
    scheduler.add_job(
        func=lambda: asyncio.run(cleanup_all_invalid_tokens()),
        trigger="cron",
        hour=3,  # 새벽 3시
        minute=5
    )

    """파일 기반 알림 시스템의 정리 작업"""
    # 매시간마다 캐시 강제 저장
    scheduler.add_job(
        func=lambda: asyncio.run(file_notification_manager.force_save_all_cache()),
        trigger="cron",
        minute=0,  # 매시 정각
        # second=0
    )
    
    # 매일 새벽 2시에 10일 이상 된 알림 정리
    scheduler.add_job(
        func=lambda: asyncio.run(cleanup_old_notifications_for_all_users()),
        trigger="cron",
        hour=2,
        minute=10
        # second=0
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

#특정 토큰 삭제 함수
def remove_fcm_token(token):

    try:
        state = StateManager.get_instance()
        init = state.get_init()
        for discordWebhooksURL in init.userStateData.index:
            # 사용자 데이터 가져오기
            user_data = init.userStateData.loc[discordWebhooksURL]
            
            # 토큰 데이터 형식 확인
            tokens_data = user_data.get("fcm_tokens_data", [])
            if not isinstance(tokens_data, list):
                tokens_data = []

            original_count = len(tokens_data)

            tokens_data = [item for item in tokens_data if item.get("token") != token]

            # 변경사항이 있으면 저장
            if len(tokens_data) != original_count:
                save_tokens_data(init, discordWebhooksURL, tokens_data)
                break

    except Exception as e:
        print(f"{datetime.now()} FCM 토큰 제거 중 오류: {str(e)}")
        return

#모든 사용자의 오래된 알림 정리
async def cleanup_old_notifications_for_all_users():
    try:
        print(f"{datetime.now()} 오래된 알림 정리 시작")
        # 알림 디렉토리의 모든 파일 확인
        notification_files = list(file_notification_manager.notifications_dir.glob("notifications_*.json"))
        
        cleaned_count = 0
        for file_path in notification_files:
            try:
                # 파일에서 webhook_url 추출을 위해 파일 내용 확인
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    webhook_url = data.get('webhook_url')
                    
                if webhook_url:
                    if await file_notification_manager.cleanup_old_notifications(webhook_url, max_age_days=10):
                        cleaned_count += 1
                    await asyncio.sleep(0.01)
                            
            except Exception as e:
                print(f"파일 정리 중 오류 ({file_path}): {str(e)}")
        
        print(f"{datetime.now()} 오래된 알림 정리 완료: {cleaned_count}개 사용자")
        
    except Exception as e:
        print(f"{datetime.now()} 전체 알림 정리 오류: {str(e)}")
