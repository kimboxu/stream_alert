import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from json import load, dump, JSONDecodeError
from dataclasses import dataclass, field
from collections import deque
import glob
from os import environ
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from discord_webhook_sender import DiscordWebhookSender

async def log_error(message, webhook_url = environ.get('errorPostBotURL')):
	await DiscordWebhookSender()._log_error(message, webhook_url)
@dataclass
class APIPerformanceLog:
    """API 성능 로그 데이터 클래스"""
    timestamp: datetime
    api_type: str
    response_time_ms: int
    is_success: bool
    http_status_code: Optional[int] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0

class APIPerformanceLogger:
    """API 성능 로깅을 관리하는 클래스 - 전역변수 없이 구현"""
    
    def __init__(self, log_dir: Path = None, max_memory_logs: int = 10000):
        # 디렉토리 설정
        if log_dir is None:
            current_file = Path(__file__)
            if current_file.parent.name == 'py':
                project_root = current_file.parent.parent
            else:
                project_root = current_file.parent
            log_dir = project_root / "data" / "api_performance_logs"
        
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 메모리 캐시 설정
        self.max_memory_logs = max_memory_logs
        self.memory_logs: deque = deque(maxlen=max_memory_logs)
        
        # 파일 저장 설정
        self.save_interval_minutes = 30  # 30분마다 파일 저장
        self.max_file_age_days = 30  # 30일 이상된 파일 삭제
        
        # 비동기 락
        self._memory_lock = asyncio.Lock()  # 메모리 액세스용 락
        self._save_lock = asyncio.Lock()    # 파일 저장용 락
        
        
        # 마지막 저장 시간
        self._last_save_time = datetime.now()
        
        print(f"{datetime.now()} API 성능 로거 초기화 완료: {self.log_dir}")

    async def log_performance(self, api_type: str, response_time_ms: int, is_success: bool,
                            http_status_code: int = None, error_type: str = None,
                            error_message: str = None, retry_count: int = 0):
        """API 성능 데이터를 로깅"""
        try:
            log_entry = APIPerformanceLog(
                timestamp=datetime.now(),
                api_type=api_type,
                response_time_ms=response_time_ms,
                is_success=is_success,
                http_status_code=http_status_code,
                error_type=error_type,
                error_message=error_message,
                retry_count=retry_count
            )
            
            # 메모리 락으로 안전하게 추가
            async with self._memory_lock:
                self.memory_logs.append(log_entry)
            
            # 주기적 저장 체크
            await self._check_and_save_if_needed()
            
        except Exception as e:
            await log_error(f"API 성능 로깅 실패: {e}")

    async def _check_and_save_if_needed(self):
        """조건에 따라 파일 저장 실행"""
        current_time = datetime.now()
        time_diff = (current_time - self._last_save_time).total_seconds() / 60
        
        # 30분마다 또는 메모리가 가득 찬 경우 저장
        if (time_diff >= self.save_interval_minutes or 
            len(self.memory_logs) >= self.max_memory_logs):
            await self._save_logs_to_file()

    async def _save_logs_to_file(self):
        """메모리의 로그를 시간 기반 파일에 저장"""
        async with self._save_lock:
            # 메모리 락으로 안전하게 복사 후 클리어
            async with self._memory_lock:
                if not self.memory_logs:
                    return
                
                logs_to_save = list(self.memory_logs)  # 안전한 복사
                self.memory_logs.clear()               # 원본 클리어
            
            try:
                # 파일 저장 로직
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"api_performance_{timestamp}.json"
                file_path = self.log_dir / filename
                
                # 복사본을 딕셔너리로 변환
                logs_data = []
                for log_entry in logs_to_save:
                    logs_data.append({
                        "timestamp": log_entry.timestamp.isoformat(),
                        "api_type": log_entry.api_type,
                        "response_time_ms": log_entry.response_time_ms,
                        "is_success": log_entry.is_success,
                        "http_status_code": log_entry.http_status_code,
                        "error_type": log_entry.error_type,
                        "error_message": log_entry.error_message,
                        "retry_count": log_entry.retry_count
                    })
                
                save_data = {
                    "created_at": datetime.now().isoformat(),
                    "log_count": len(logs_data),
                    "logs": logs_data
                }
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    dump(save_data, f, ensure_ascii=False, indent=2)
                
                print(f"{datetime.now()} API 성능 로그 저장 완료: {file_path} ({len(logs_data)}개 기록)")
                
                self._last_save_time = datetime.now()
                await self._cleanup_old_files()
                
            except Exception as e:
                # 저장 실패 시 데이터 복구
                async with self._memory_lock:
                    # 실패한 로그들을 다시 메모리에 추가 (최신 순서 유지)
                    for log_entry in reversed(logs_to_save):
                        self.memory_logs.appendleft(log_entry)
                        
                await log_error(f"API 성능 로그 파일 저장 실패: {e}")

    async def _cleanup_old_files(self):
        """오래된 로그 파일 삭제"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.max_file_age_days)
            pattern = str(self.log_dir / "api_performance_*.json")
            
            for file_path in glob.glob(pattern):
                file_path = Path(file_path)
                
                # 파일명에서 날짜 추출
                try:
                    filename = file_path.stem
                    date_part = filename.split('_')[2] + "_" + filename.split('_')[3]
                    file_date = datetime.strptime(date_part, "%Y%m%d_%H%M%S")
                    
                    if file_date < cutoff_date:
                        file_path.unlink()
                        print(f"{datetime.now()} 오래된 로그 파일 삭제: {file_path}")
                        
                except (IndexError, ValueError):
                    # 파일명 형식이 맞지 않으면 건너뛰기
                    continue
                    
        except Exception as e:
            await log_error(f"오래된 로그 파일 정리 실패: {e}")

    async def get_logs_in_period(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """특정 기간의 로그 데이터 조회"""
        try:
            all_logs = []
            
            # 메모리 락으로 안전하게 복사
            async with self._memory_lock:
                memory_logs_copy = list(self.memory_logs)
            
            # 복사본으로 순회 작업 수행
            for log_entry in memory_logs_copy:
                if start_date <= log_entry.timestamp <= end_date:
                    all_logs.append({
                        "timestamp": log_entry.timestamp.isoformat(),
                        "api_type": log_entry.api_type,
                        "response_time_ms": log_entry.response_time_ms,
                        "is_success": log_entry.is_success,
                        "http_status_code": log_entry.http_status_code,
                        "error_type": log_entry.error_type,
                        "error_message": log_entry.error_message,
                        "retry_count": log_entry.retry_count
                    })
            
            # 파일의 로그 추가
            pattern = str(self.log_dir / "api_performance_*.json")
            for file_path in glob.glob(pattern):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_data = load(f)
                        
                    for log_data in file_data.get('logs', []):
                        log_time = datetime.fromisoformat(log_data['timestamp'])
                        if start_date <= log_time <= end_date:
                            all_logs.append(log_data)
                            
                except (JSONDecodeError, FileNotFoundError, KeyError):
                    continue
            
            return sorted(all_logs, key=lambda x: x['timestamp'])
            
        except Exception as e:
            await log_error(f"로그 조회 실패: {e}")
            return []

    async def force_save(self):
        """강제로 현재 메모리의 로그를 파일에 저장"""
        await self._save_logs_to_file()

    def get_current_memory_stats(self) -> Dict:
        """현재 메모리 상태 정보 반환"""
        try:
            memory_count = len(self.memory_logs)
            
            return {
                "memory_log_count": memory_count,
                "max_memory_logs": self.max_memory_logs,
                "last_save_time": self._last_save_time.isoformat(),
                "next_auto_save_in_minutes": max(0, self.save_interval_minutes - 
                                            (datetime.now() - self._last_save_time).total_seconds() / 60)
            }
        except Exception:
            # 예외 발생 시 기본값 반환
            return {
                "memory_log_count": 0,
                "max_memory_logs": self.max_memory_logs,
                "last_save_time": datetime.now().isoformat(),
                "next_auto_save_in_minutes": 0
            }

class APIStatisticsCalculator:
    """API 통계 계산을 담당하는 클래스"""
    
    def __init__(self, logger: APIPerformanceLogger):
        self.logger = logger

    async def calculate_avg_response_time(self, api_type: str, start_date: datetime, 
                                        end_date: datetime) -> float:
        """특정 API 타입의 평균 응답시간 계산"""
        try:
            logs = await self.logger.get_logs_in_period(start_date, end_date)
            filtered_logs = [
                log for log in logs 
                if log['api_type'] == api_type and log['is_success']
            ]
            
            if filtered_logs:
                times = [log['response_time_ms'] for log in filtered_logs]
                return round(sum(times) / len(times), 2)
            return 0
            
        except Exception as e:
            await log_error(f"평균 응답시간 계산 오류: {e}")
            return 0

    async def calculate_success_rate(self, api_type: str, start_date: datetime, 
                                   end_date: datetime) -> float:
        """특정 API 타입의 성공률 계산"""
        try:
            logs = await self.logger.get_logs_in_period(start_date, end_date)
            filtered_logs = [log for log in logs if log['api_type'] == api_type]
            
            if filtered_logs:
                success_count = sum(1 for log in filtered_logs if log['is_success'])
                return round((success_count / len(filtered_logs)) * 100, 2)
            return 100
            
        except Exception as e:
            await log_error(f"성공률 계산 오류: {e}")
            return 0

    async def get_error_count(self, start_date: datetime, end_date: datetime) -> int:
        """특정 기간의 에러 개수 계산"""
        try:
            logs = await self.logger.get_logs_in_period(start_date, end_date)
            return len([log for log in logs if not log['is_success']])
            
        except Exception as e:
            await log_error(f"에러 개수 계산 오류: {e}")
            return 0

    async def get_notification_statistics(self, start_date: datetime, 
                                        end_date: datetime) -> Dict:
        """알림 통계 계산"""
        try:
            logs = await self.logger.get_logs_in_period(start_date, end_date)
            
            discord_count = len([
                log for log in logs 
                if log['api_type'] == 'discord_webhook' and log['is_success']
            ])
            
            fcm_count = len([
                log for log in logs 
                if log['api_type'] == 'fcm_push' and log['is_success']
            ])
            
            return {
                'discord': discord_count,
                'fcm': fcm_count,
                'total': discord_count + fcm_count
            }
            
        except Exception as e:
            await log_error(f"알림 통계 계산 오류: {e}")
            return {'discord': 0, 'fcm': 0, 'total': 0}

    async def calculate_comprehensive_statistics(self, start_date: datetime, end_date: datetime) -> Dict:
        """포괄적인 통계 계산 - 실시간과 일일 통계 모두 사용"""
        try:
            # 기본 API 통계 계산
            discord_avg = await self.calculate_avg_response_time('discord_webhook', start_date, end_date)
            fcm_avg = await self.calculate_avg_response_time('fcm_push', start_date, end_date)
            discord_success_rate = await self.calculate_success_rate('discord_webhook', start_date, end_date)
            fcm_success_rate = await self.calculate_success_rate('fcm_push', start_date, end_date)
            
            notification_stats = await self.get_notification_statistics(start_date, end_date)
            error_count = await self.get_error_count(start_date, end_date)
            
            # 통합된 형식으로 반환
            return {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "duration_days": (end_date.date() - start_date.date()).days + 1
                },
                "api_performance": {
                    "discord_webhook": {
                        "total_requests": notification_stats.get('discord', 0),
                        "avg_response_time_ms": discord_avg,
                        "success_rate_percent": discord_success_rate
                    },
                    "fcm_push": {
                        "total_requests": notification_stats.get('fcm', 0),
                        "avg_response_time_ms": fcm_avg,
                        "success_rate_percent": fcm_success_rate
                    },
                    "summary": {
                        "total_requests": notification_stats.get('total', 0),
                        "total_errors": error_count,
                        "overall_success_rate": self._calculate_overall_success_rate(notification_stats, error_count)
                    }
                },
                "calculated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            await log_error(f"포괄적 통계 계산 오류: {e}")
            return {}

    def _calculate_overall_success_rate(self, notification_stats: Dict, error_count: int) -> float:
        """전체 성공률 계산"""
        total_requests = notification_stats.get('total', 0)
        if total_requests == 0:
            return 100.0
        
        success_requests = total_requests - error_count
        return round((success_requests / total_requests) * 100, 2)
    
class PerformanceManager:
    """전체 성능 관리 시스템을 조율하는 메인 클래스"""
    
    def __init__(self, log_dir: Path = None):
        self.logger = APIPerformanceLogger(log_dir)
        self.calculator = APIStatisticsCalculator(self.logger)
        self.scheduler = None
        
        # 일일 통계 저장 경로
        self.daily_stats_file = self.logger.log_dir / "daily_statistics.json"

    async def log_api_performance(self, api_type: str, response_time_ms: int, 
                                is_success: bool, **kwargs):
        """API 성능 로깅 (외부 인터페이스)"""
        await self.logger.log_performance(
            api_type=api_type,
            response_time_ms=response_time_ms,
            is_success=is_success,
            **kwargs
        )

    async def get_statistics(self, days: int = 7, stat_type: str = "realtime") -> Dict:
        """통계 조회"""
        if stat_type == "realtime":
            return await self._get_realtime_statistics(days)
        elif stat_type == "daily":
            return await self._get_daily_statistics_list(days)
        elif stat_type == "daily_summary":
            return await self._get_daily_statistics_with_summary(days)
        else:
            raise ValueError(f"지원하지 않는 통계 타입: {stat_type}")

    async def _get_realtime_statistics(self, days: int = 7) -> Dict:
        """실시간 통계 조회 (메모리 + 최근 파일 데이터 기반)"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        try:
            # 통계 계산
            stats = await self.calculator.calculate_comprehensive_statistics(start_date, end_date)
            
            # 메모리 상태 정보 추가
            memory_stats = self.logger.get_current_memory_stats()
            stats["system_status"] = {
                "data_source": "realtime_logs",
                "memory_cache": memory_stats,
                "includes_current_session": True
            }
            
            return stats
            
        except Exception as e:
            await log_error(f"실시간 통계 조회 오류: {e}")
            return {}

    async def _get_daily_statistics_list(self, days: int = 7) -> Dict:
        """일일 통계 리스트 조회"""
        try:
            daily_stats_list = await self.get_daily_statistics_raw(days)
            
            return {
                "period": {
                    "start": (datetime.now().date() - timedelta(days=days)).isoformat(),
                    "end": datetime.now().date().isoformat(),
                    "duration_days": days
                },
                "daily_statistics": daily_stats_list,
                "total_days_available": len(daily_stats_list),
                "system_status": {
                    "data_source": "daily_statistics_file",
                    "includes_current_session": False
                },
                "calculated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            await log_error(f"일일 통계 리스트 조회 오류: {e}")
            return {}

    async def _get_daily_statistics_with_summary(self, days: int = 7) -> Dict:
        """일일 통계 + 요약 정보"""
        try:
            daily_stats_list = await self.get_daily_statistics_raw(days)
            
            if not daily_stats_list:
                return {
                    "period": {
                        "start": (datetime.now().date() - timedelta(days=days)).isoformat(),
                        "end": datetime.now().date().isoformat(),
                        "duration_days": days
                    },
                    "summary": {},
                    "daily_statistics": [],
                    "total_days_available": 0
                }
            
            # 요약 통계 계산
            summary = await self._calculate_daily_summary(daily_stats_list)
            
            return {
                "period": {
                    "start": daily_stats_list[-1]['date'] if daily_stats_list else "",
                    "end": daily_stats_list[0]['date'] if daily_stats_list else "",
                    "duration_days": len(daily_stats_list)
                },
                "summary": summary,
                "daily_statistics": daily_stats_list,
                "total_days_available": len(daily_stats_list),
                "system_status": {
                    "data_source": "daily_statistics_file",
                    "includes_current_session": False
                },
                "calculated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            await log_error(f"일일 통계 요약 조회 오류: {e}")
            return {}

    async def get_daily_statistics_raw(self, days: int = 7) -> List[Dict]:
        """저장된 일일 통계 원본 조회"""
        try:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            if not self.daily_stats_file.exists():
                return []
            
            with open(self.daily_stats_file, 'r', encoding='utf-8') as f:
                all_stats = load(f)
            
            # 날짜 범위 필터링
            filtered_stats = []
            for date_str, stat_data in all_stats.items():
                try:
                    stat_date = datetime.fromisoformat(date_str).date()
                    if start_date <= stat_date <= end_date:
                        filtered_stats.append(stat_data)
                except (ValueError, TypeError):
                    continue
            
            # 날짜순 정렬 (최신순)
            filtered_stats.sort(key=lambda x: x.get('date', ''), reverse=True)
            return filtered_stats
            
        except Exception as e:
            await log_error(f"일일 통계 원본 조회 오류: {e}")
            return []

    async def _calculate_daily_summary(self, daily_stats_list: List[Dict]) -> Dict:
        """일일 통계 리스트에서 요약 계산"""
        try:
            if not daily_stats_list:
                return {}
            
            # 총합 계산 (통합 형식 기준)
            total_discord = sum(
                stat.get('api_performance', {}).get('discord_webhook', {}).get('total_requests', 0) 
                for stat in daily_stats_list
            )
            total_fcm = sum(
                stat.get('api_performance', {}).get('fcm_push', {}).get('total_requests', 0) 
                for stat in daily_stats_list
            )
            total_errors = sum(
                stat.get('api_performance', {}).get('summary', {}).get('total_errors', 0) 
                for stat in daily_stats_list
            )
            
            # 평균 계산 (유효한 값만)
            discord_times = [
                stat.get('api_performance', {}).get('discord_webhook', {}).get('avg_response_time_ms', 0) 
                for stat in daily_stats_list
            ]
            valid_discord_times = [t for t in discord_times if t > 0]
            
            fcm_times = [
                stat.get('api_performance', {}).get('fcm_push', {}).get('avg_response_time_ms', 0) 
                for stat in daily_stats_list
            ]
            valid_fcm_times = [t for t in fcm_times if t > 0]
            
            discord_success_rates = [
                stat.get('api_performance', {}).get('discord_webhook', {}).get('success_rate_percent', 0) 
                for stat in daily_stats_list
            ]
            valid_discord_success = [r for r in discord_success_rates if r > 0]
            
            fcm_success_rates = [
                stat.get('api_performance', {}).get('fcm_push', {}).get('success_rate_percent', 0) 
                for stat in daily_stats_list
            ]
            valid_fcm_success = [r for r in fcm_success_rates if r > 0]
            
            # 최신 사용자 정보
            latest_stat = daily_stats_list[0] if daily_stats_list else {}
            latest_user_stats = latest_stat.get('user_statistics', {})
            
            return {
                "api_performance": {
                    "discord_webhook": {
                        "total_requests": total_discord,
                        "daily_avg_requests": round(total_discord / len(daily_stats_list), 1) if daily_stats_list else 0,
                        "avg_response_time_ms": round(sum(valid_discord_times) / len(valid_discord_times), 2) if valid_discord_times else 0,
                        "avg_success_rate_percent": round(sum(valid_discord_success) / len(valid_discord_success), 2) if valid_discord_success else 0
                    },
                    "fcm_push": {
                        "total_requests": total_fcm,
                        "daily_avg_requests": round(total_fcm / len(daily_stats_list), 1) if daily_stats_list else 0,
                        "avg_response_time_ms": round(sum(valid_fcm_times) / len(valid_fcm_times), 2) if valid_fcm_times else 0,
                        "avg_success_rate_percent": round(sum(valid_fcm_success) / len(valid_fcm_success), 2) if valid_fcm_success else 0
                    },
                    "summary": {
                        "total_requests": total_discord + total_fcm,
                        "daily_avg_requests": round((total_discord + total_fcm) / len(daily_stats_list), 1) if daily_stats_list else 0,
                        "total_errors": total_errors,
                        "daily_avg_errors": round(total_errors / len(daily_stats_list), 1) if daily_stats_list else 0
                    }
                },
                "user_statistics": {
                    "latest_total_users": latest_user_stats.get('total_users', 0),
                    "latest_active_users": latest_user_stats.get('active_users_in_period', 0),
                    "latest_new_users": latest_user_stats.get('new_users_in_period', 0)
                }
            }
            
        except Exception as e:
            await log_error(f"일일 요약 계산 오류: {e}")
            return {}

    async def calculate_and_save_daily_statistics(self, target_date: datetime = None):
        """특정 날짜의 일일 통계를 계산하고 저장"""
        if target_date is None:
            target_date = datetime.now().date() - timedelta(days=1)  # 어제
        elif isinstance(target_date, datetime):
            target_date = target_date.date()
            
        try:
            print(f"{datetime.now()} 일일 통계 계산 시작: {target_date}")
            
            # 해당 날짜의 시작과 끝 시간 설정
            start_datetime = datetime.combine(target_date, datetime.min.time())
            end_datetime = datetime.combine(target_date, datetime.max.time())
            
            # 통계 계산
            comprehensive_stats = await self.calculator.calculate_comprehensive_statistics(
                start_datetime, end_datetime)
            
            # 일일 통계
            daily_stat = {
                "date": target_date.isoformat(),
                "calculated_at": datetime.now().isoformat(),
                **comprehensive_stats
            }
            
            # 일일 통계 저장
            await self._save_daily_statistics(daily_stat)
            
            print(f"{datetime.now()} 일일 통계 저장 완료: {target_date}")
            discord_perf = comprehensive_stats.get('api_performance', {}).get('discord_webhook', {})
            fcm_perf = comprehensive_stats.get('api_performance', {}).get('fcm_push', {})
            print(f"Discord: {discord_perf.get('avg_response_time_ms', 0)}ms, {discord_perf.get('success_rate_percent', 0)}%")
            print(f"FCM: {fcm_perf.get('avg_response_time_ms', 0)}ms, {fcm_perf.get('success_rate_percent', 0)}%")
            
            return daily_stat
            
        except Exception as e:
            await log_error(f"일일 통계 계산 및 저장 오류: {e}")
            return None

    async def _save_daily_statistics(self, daily_stat):
        """일일 통계를 파일에 저장"""
        try:
            # 기존 데이터 로드
            existing_stats = {}
            if self.daily_stats_file.exists():
                with open(self.daily_stats_file, 'r', encoding='utf-8') as f:
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
            with open(self.daily_stats_file, 'w', encoding='utf-8') as f:
                dump(filtered_stats, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            await log_error(f"일일 통계 파일 저장 실패: {e}")

    def setup_scheduler(self):
        """정기적인 작업 스케줄러 설정"""
        if self.scheduler is None:
            self.scheduler = BackgroundScheduler()
            
            # 매 30분마다 강제 저장
            self.scheduler.add_job(
                func=lambda: asyncio.run(self.logger.force_save()),
                trigger="interval",
                minutes=30,
                id='force_save_logs'
            )
            
            # 매일 새벽 1시에 전날 일일 통계 계산
            self.scheduler.add_job(
                func=lambda: asyncio.run(self.calculate_and_save_daily_statistics()),
                trigger="cron",
                hour=1,
                minute=0,
                id='daily_statistics'
            )
            
            # 매일 새벽 2시에 오래된 파일 정리
            self.scheduler.add_job(
                func=lambda: asyncio.run(self.logger._cleanup_old_files()),
                trigger="cron",
                hour=2,
                minute=0,
                id='cleanup_old_files'
            )
            
            self.scheduler.start()
            print(f"{datetime.now()} 성능 관리 스케줄러 시작됨")
            
            # 프로그램 종료시 스케줄러 정리
            atexit.register(lambda: self.scheduler.shutdown() if self.scheduler else None)

    async def shutdown(self):
        """시스템 종료시 정리 작업"""
        # 남은 로그 강제 저장
        await self.logger.force_save()
        
        # 스케줄러 종료
        if self.scheduler:
            self.scheduler.shutdown()
            
        print(f"{datetime.now()} 성능 관리 시스템 종료됨")

# 사용 예시를 위한 헬퍼 함수들
async def log_api_performance(api_type: str, response_time_ms: int, is_success: bool, 
                            http_status_code: int = None, error_type: str = None, 
                            error_message: str = None, retry_count: int = 0):
    """전역 함수로 사용할 수 있는 로깅 인터페이스"""
    try:
        from shared_state import StateManager
        state_manager = StateManager.get_instance()
        performance_manager = state_manager.get_performance_manager()
        
        if performance_manager:
            await performance_manager.log_api_performance(
                api_type=api_type,
                response_time_ms=response_time_ms,
                is_success=is_success,
                http_status_code=http_status_code,
                error_type=error_type,
                error_message=error_message,
                retry_count=retry_count
            )
    except Exception as e:
        # 성능 로깅 실패해도 메인 로직에 영향 주지 않음
        pass

def setup_performance_scheduler():
    """스케줄러 설정을 위한 전역 함수"""
    try:
        from shared_state import StateManager
        state_manager = StateManager.get_instance()
        performance_manager = state_manager.get_performance_manager()
        
        if performance_manager:
            performance_manager.setup_scheduler()
    except Exception as e:
        print(f"성능 스케줄러 설정 실패: {e}")

