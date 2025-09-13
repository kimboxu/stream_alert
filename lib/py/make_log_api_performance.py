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

    async def calculate_avg_response_time(self, api_type: str, logs) -> float:
        """특정 API 타입의 평균 응답시간 계산"""
        try:
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

    async def calculate_success_rate(self, api_type: str, logs) -> float:
        """특정 API 타입의 성공률 계산"""
        try:
            filtered_logs = [log for log in logs if log['api_type'] == api_type]
            
            if filtered_logs:
                success_count = sum(1 for log in filtered_logs if log['is_success'])
                return round((success_count / len(filtered_logs)) * 100, 2)
            return 100
            
        except Exception as e:
            await log_error(f"성공률 계산 오류: {e}")
            return 0

    async def get_error_count(self, api_type: str, logs) -> int:
        """특정 API 타입의 에러 개수 계산"""
        try:
            return len([
                log for log in logs 
                if log['api_type'] == api_type and not log['is_success']
            ])
            
        except Exception as e:
            await log_error(f"에러 개수 계산 오류: {e}")
            return 0

    async def get_request_count(self, api_type: str, logs) -> int:
        """특정 API 타입의 총 요청 수 계산"""
        try:
            return len([log for log in logs if log['api_type'] == api_type])
        except Exception as e:
            await log_error(f"요청 수 계산 오류: {e}")
            return 0
        
    async def get_api_statistics_by_type(self, api_type: str, logs) -> Dict:
        """특정 API 타입에 대한 상세 통계"""
        try:
            total_requests = await self.get_request_count(api_type, logs)
            error_count = await self.get_error_count(api_type, logs)
            avg_response_time = await self.calculate_avg_response_time(api_type, logs)
            success_rate = await self.calculate_success_rate(api_type, logs)
            
            return {
                "total_requests": total_requests,
                "successful_requests": total_requests - error_count,
                "failed_requests": error_count,
                "avg_response_time_ms": avg_response_time,
                "success_rate_percent": success_rate
            }
            
        except Exception as e:
            await log_error(f"API 타입별 통계 계산 오류 ({api_type}): {e}")
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "avg_response_time_ms": 0,
                "success_rate_percent": 100
            }

    async def get_all_api_types_from_logs(self, logs) -> List[str]:
        """로그에서 실제 사용된 모든 API 타입 추출"""
        try:
            api_types = set()
            for log in logs:
                api_type = log.get('api_type')
                if api_type:
                    api_types.add(api_type)
            return sorted(list(api_types))
        except Exception as e:
            await log_error(f"API 타입 추출 오류: {e}")
            return []

    async def get_notification_statistics(self, logs) -> Dict:
        """알림 통계 계산"""
        try:
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
        """포괄적인 통계 계산 - 모든 API 타입 지원"""
        try:
            logs = await self.logger.get_logs_in_period(start_date, end_date)
            
            # 실제 로그에서 사용된 API 타입들 찾기
            actual_api_types = await self.get_all_api_types_from_logs(logs)
            
            # 모든 API 타입에 대한 통계 계산
            api_performance = {}
            
            for api_type in actual_api_types:
                api_performance[api_type] = await self.get_api_statistics_by_type(api_type, logs)
            
            # 전체 요약 통계
            total_requests = sum(stats['total_requests'] for stats in api_performance.values())
            total_errors = sum(stats['failed_requests'] for stats in api_performance.values())
            total_successful = total_requests - total_errors
            
            overall_success_rate = (
                round((total_successful / total_requests) * 100, 2) 
                if total_requests > 0 else 100.0
            )
            
            # 기존 호환성을 위한 알림 통계
            notification_stats = await self.get_notification_statistics(logs)
            
            # 통합된 형식으로 반환
            return {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "duration_days": (end_date.date() - start_date.date()).days + 1
                },
                "api_performance": api_performance,
                "summary": {
                    "total_requests": total_requests,
                    "successful_requests": total_successful,
                    "failed_requests": total_errors,
                    "overall_success_rate_percent": overall_success_rate,
                    "unique_api_types": len(actual_api_types),
                    "active_api_types": actual_api_types
                },
                # 기존 호환성 유지
                "notification_summary": notification_stats,
                "calculated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            await log_error(f"포괄적 통계 계산 오류: {e}")
            return {}

    def _calculate_overall_success_rate(self, total_successful: int, total_requests: int) -> float:
        """전체 성공률 계산"""
        if total_requests == 0:
            return 100.0
        return round((total_successful / total_requests) * 100, 2)
    
    async def get_api_performance_summary(self, logs) -> Dict:
        """API 성능 요약 (상위 API 타입별)"""
        try:
            api_types = await self.get_all_api_types_from_logs(logs)
            
            performance_summary = []
            
            for api_type in api_types:
                stats = await self.get_api_statistics_by_type(api_type, logs)
                performance_summary.append({
                    "api_type": api_type,
                    **stats
                })
            
            # 요청 수 기준으로 정렬
            performance_summary.sort(key=lambda x: x['total_requests'], reverse=True)
            
            return {
                "top_apis_by_usage": performance_summary[:10],  # 상위 10개
                "total_api_types": len(api_types),
                "summary_generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            await log_error(f"API 성능 요약 계산 오류: {e}")
            return {}

    async def calculate_api_health_score(self, api_type: str, logs) -> Dict:
        """API 건강도 점수 계산 (0-100점)"""
        try:
            stats = await self.get_api_statistics_by_type(api_type, logs)
            
            if stats['total_requests'] == 0:
                return {"health_score": 100, "status": "no_data", "details": "요청 없음"}
            
            # 건강도 계산 요소들
            success_score = stats['success_rate_percent']  # 성공률 (0-100)
            
            # 응답시간 점수 (빠를수록 높은 점수)
            avg_time = stats['avg_response_time_ms']
            if avg_time == 0:
                time_score = 100
            elif avg_time <= 100:
                time_score = 100
            elif avg_time <= 500:
                time_score = 90 - (avg_time - 100) * 0.2
            elif avg_time <= 1000:
                time_score = 70 - (avg_time - 500) * 0.1
            elif avg_time <= 3000:
                time_score = 50 - (avg_time - 1000) * 0.02
            else:
                time_score = 10
                
            time_score = max(0, min(100, time_score))
            
            # 종합 건강도 점수 (성공률 70%, 응답시간 30%)
            health_score = round(success_score * 0.7 + time_score * 0.3, 1)
            
            # 상태 분류
            if health_score >= 90:
                status = "excellent"
            elif health_score >= 80:
                status = "good"
            elif health_score >= 70:
                status = "fair"
            elif health_score >= 60:
                status = "poor"
            else:
                status = "critical"
            
            return {
                "health_score": health_score,
                "status": status,
                "details": {
                    "success_component": success_score,
                    "response_time_component": round(time_score, 1),
                    "total_requests": stats['total_requests'],
                    "avg_response_time_ms": avg_time
                }
            }
            
        except Exception as e:
            await log_error(f"API 건강도 계산 오류 ({api_type}): {e}")
            return {"health_score": 0, "status": "error", "details": str(e)}

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

    async def get_statistics(self, days: int = 7, stat_type: str = "realtime", api_type: str = None) -> Dict:
        """통계 조회"""
        if stat_type == "realtime":
            return await self._get_realtime_statistics(days, api_type)
        elif stat_type == "daily":
            return await self._get_daily_statistics_list(days, api_type)
        elif stat_type == "daily_summary":
            return await self._get_daily_statistics_with_summary(days, api_type)
        elif stat_type == "api_health":
            return await self._get_api_health_statistics(days, api_type)
        elif stat_type == "performance_summary":
            return await self._get_performance_summary(days)
        else:
            raise ValueError(f"지원하지 않는 통계 타입: {stat_type}")

    async def _get_realtime_statistics(self, days: int = 7, api_type: str = None) -> Dict:
        """실시간 통계 조회 (메모리 + 최근 파일 데이터 기반)"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        try:
            # 통계 계산
            stats = await self.calculator.calculate_comprehensive_statistics(start_date, end_date)
            
            # 특정 API 타입만 필터링
            if api_type and api_type in stats.get('api_performance', {}):
                filtered_stats = {
                    "period": stats["period"],
                    "api_performance": {api_type: stats['api_performance'][api_type]},
                    "summary": {
                        **stats['api_performance'][api_type],
                        "filtered_by": api_type
                    },
                    "calculated_at": stats["calculated_at"]
                }
                stats = filtered_stats
            
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

    async def _get_api_health_statistics(self, days: int = 7, api_type: str = None) -> Dict:
        """API 건강도 통계"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        try:
            logs = await self.logger.get_logs_in_period(start_date, end_date)
            
            if api_type:
                # 특정 API 타입의 건강도
                health_data = await self.calculator.calculate_api_health_score(api_type, logs)
                api_stats = await self.calculator.get_api_statistics_by_type(api_type, logs)
                
                return {
                    "period": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "duration_days": days
                    },
                    "api_type": api_type,
                    "health_analysis": health_data,
                    "detailed_statistics": api_stats,
                    "calculated_at": datetime.now().isoformat()
                }
            else:
                # 모든 API 타입의 건강도
                api_types = await self.calculator.get_all_api_types_from_logs(logs)
                health_results = {}
                
                for api in api_types:
                    health_results[api] = await self.calculator.calculate_api_health_score(api, logs)
                
                return {
                    "period": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "duration_days": days
                    },
                    "health_by_api_type": health_results,
                    "total_api_types_analyzed": len(api_types),
                    "calculated_at": datetime.now().isoformat()
                }
                
        except Exception as e:
            await log_error(f"API 건강도 통계 조회 오류: {e}")
            return {}

    async def _get_performance_summary(self, days: int = 7) -> Dict:
        """성능 요약 통계"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        try:
            logs = await self.logger.get_logs_in_period(start_date, end_date)
            performance_summary = await self.calculator.get_api_performance_summary(logs)
            
            return {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "duration_days": days
                },
                **performance_summary,
                "calculated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            await log_error(f"성능 요약 조회 오류: {e}")
            return {}

    async def _get_daily_statistics_list(self, days: int = 7, api_type: str = None) -> Dict:
        """일일 통계 리스트 조회 - API 타입 필터링 지원"""
        try:
            daily_stats_list = await self.get_daily_statistics_raw(days)
            
            # API 타입 필터링
            if api_type:
                filtered_stats_list = []
                for daily_stat in daily_stats_list:
                    api_performance = daily_stat.get('api_performance', {})
                    if api_type in api_performance:
                        filtered_stat = {
                            **daily_stat,
                            'api_performance': {api_type: api_performance[api_type]},
                            'filtered_by': api_type
                        }
                        filtered_stats_list.append(filtered_stat)
                daily_stats_list = filtered_stats_list
            
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
                    "includes_current_session": False,
                    "filtered_by": api_type if api_type else None
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
            
            # 모든 API 타입 수집
            all_api_types = set()
            for stat in daily_stats_list:
                api_performance = stat.get('api_performance', {})
                all_api_types.update(api_performance.keys())
            
            # API 타입별 요약 계산
            api_summaries = {}
            for api_type in all_api_types:
                total_requests = sum(
                    stat.get('api_performance', {}).get(api_type, {}).get('total_requests', 0) 
                    for stat in daily_stats_list
                )
                total_errors = sum(
                    stat.get('api_performance', {}).get(api_type, {}).get('failed_requests', 0) 
                    for stat in daily_stats_list
                )
                
                # 평균 계산 (유효한 값만)
                response_times = [
                    stat.get('api_performance', {}).get(api_type, {}).get('avg_response_time_ms', 0) 
                    for stat in daily_stats_list
                ]
                valid_response_times = [t for t in response_times if t > 0]
                
                success_rates = [
                    stat.get('api_performance', {}).get(api_type, {}).get('success_rate_percent', 0) 
                    for stat in daily_stats_list
                ]
                valid_success_rates = [r for r in success_rates if r > 0]
                
                api_summaries[api_type] = {
                    "total_requests": total_requests,
                    "daily_avg_requests": round(total_requests / len(daily_stats_list), 1) if daily_stats_list else 0,
                    "total_errors": total_errors,
                    "daily_avg_errors": round(total_errors / len(daily_stats_list), 1) if daily_stats_list else 0,
                    "avg_response_time_ms": round(sum(valid_response_times) / len(valid_response_times), 2) if valid_response_times else 0,
                    "avg_success_rate_percent": round(sum(valid_success_rates) / len(valid_success_rates), 2) if valid_success_rates else 0
                }
            
            # 전체 요약
            total_all_requests = sum(summary["total_requests"] for summary in api_summaries.values())
            total_all_errors = sum(summary["total_errors"] for summary in api_summaries.values())
            
            return {
                "api_performance_summary": api_summaries,
                "overall_summary": {
                    "total_requests": total_all_requests,
                    "daily_avg_requests": round(total_all_requests / len(daily_stats_list), 1) if daily_stats_list else 0,
                    "total_errors": total_all_errors,
                    "daily_avg_errors": round(total_all_errors / len(daily_stats_list), 1) if daily_stats_list else 0,
                    "total_api_types": len(all_api_types),
                    "api_types": sorted(list(all_api_types))
                }
            }
            
        except Exception as e:
            await log_error(f"일일 요약 계산 오류: {e}")
            return {}
        
    async def get_api_comparison(self, api_types: List[str], days: int = 7) -> Dict:
        """여러 API 타입 간 성능 비교"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        try:
            logs = await self.logger.get_logs_in_period(start_date, end_date)
            
            comparison_data = {}
            for api_type in api_types:
                stats = await self.calculator.get_api_statistics_by_type(api_type, logs)
                health = await self.calculator.calculate_api_health_score(api_type, logs)
                
                comparison_data[api_type] = {
                    **stats,
                    "health_score": health["health_score"],
                    "health_status": health["status"]
                }
            
            return {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "duration_days": days
                },
                "comparison_data": comparison_data,
                "compared_api_types": api_types,
                "calculated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            await log_error(f"API 비교 통계 오류: {e}")
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
            
            # 요약 정보 출력
            api_performance = comprehensive_stats.get('api_performance', {})
            summary = comprehensive_stats.get('summary', {})
            
            print(f"총 {summary.get('unique_api_types', 0)}개 API 타입, "
                  f"{summary.get('total_requests', 0)}건 요청, "
                  f"{summary.get('overall_success_rate_percent', 0)}% 성공률")
            
            # 상위 API 타입들 출력
            sorted_apis = sorted(
                api_performance.items(), 
                key=lambda x: x[1].get('total_requests', 0), 
                reverse=True
            )
            for api_type, stats in sorted_apis[:5]:  # 상위 5개만
                print(f"  {api_type}: {stats.get('total_requests', 0)}건, "
                      f"{stats.get('avg_response_time_ms', 0)}ms, "
                      f"{stats.get('success_rate_percent', 0)}%")
            
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

