import asyncio
import logging
from datetime import datetime
from json import loads
from typing import Dict, Optional, Any, Callable, Union
from dataclasses import dataclass
from enum import Enum

import aiohttp
from base import log_error
from aiohttp import ClientTimeout

from session_manager import SessionManager, ConnectorConfig


logger = logging.getLogger(__name__)


# ==================== 설정 클래스 ====================
class PlatformType(Enum):
    """플랫폼 타입"""
    AFREECA = "afreeca"
    CHZZK = "chzzk"
    TWITCH = "twitch"
    CAFE = "cafe"
    YOUTUBE = "youtube"
    IMAGE = "image"


@dataclass
class TimeoutConfig:
    """플랫폼별 타임아웃 설정"""
    platform: str
    connect_timeout: float = 5.0
    read_timeout: float = 10.0
    total_timeout: float = 30.0
    
    @classmethod
    def get_config(cls, platform: str) -> "TimeoutConfig":
        """플랫폼별 타임아웃 설정 반환"""
        configs = {
            "image": cls(
                platform="image",
                connect_timeout=2.0,
                read_timeout=3.0,
                total_timeout=5.0,
            ),
            "afreeca": cls(
                platform="afreeca",
                connect_timeout=5.0,
                read_timeout=10.0,
                total_timeout=20.0,
            ),
            "chzzk": cls(
                platform="chzzk",
                connect_timeout=5.0,
                read_timeout=12.0,
                total_timeout=25.0,
            ),
            "twitch": cls(
                platform="twitch",
                connect_timeout=5.0,
                read_timeout=10.0,
                total_timeout=25.0,
            ),
            "cafe": cls(
                platform="cafe",
                connect_timeout=5.0,
                read_timeout=10.0,
                total_timeout=25.0,
            ),
            "youtube": cls(
                platform="youtube",
                connect_timeout=5.0,
                read_timeout=10.0,
                total_timeout=25.0,
            ),
        }
        return configs.get(
            platform,
            cls(platform=platform),
        )
    
    def to_client_timeout(self) -> ClientTimeout:
        """aiohttp ClientTimeout으로 변환"""
        return ClientTimeout(
            total=self.total_timeout,
            connect=self.connect_timeout,
            sock_read=self.read_timeout,
        )


@dataclass
class RetryConfig:
    """재시도 설정"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    exponential_base: float = 2.0
    
    @classmethod
    def get_config(cls, platform: str) -> "RetryConfig":
        """플랫폼별 재시도 설정"""
        if platform == "image":
            return cls(max_retries=1, base_delay=0.5, max_delay=2.0)
        return cls()


# ==================== 플랫폼 설정 ====================
@dataclass
class PlatformConfig:
    """플랫폼별 API 설정"""
    needs_cookies: bool = False
    needs_params: bool = False
    url_formatter: Optional[Callable] = None
    response_handler: Callable = None
    is_binary: bool = False
    
    def __post_init__(self):
        if self.response_handler is None:
            self.response_handler = lambda r: r


# ==================== 메인 함수 ====================
async def get_message(
    performance_manager,
    platform: str,
    link: str,
) -> Dict[str, Any]:

    start_time = datetime.now()
    
    # 플랫폼 설정 검증
    platform_configs = _get_platform_configs()
    if platform not in platform_configs:
        error_msg = f"지원하지 않는 플랫폼입니다: {platform}"
        await log_error(error_msg)
        return {}
    
    config = platform_configs[platform]
    timeout_config = TimeoutConfig.get_config(platform)
    retry_config = RetryConfig.get_config(platform)
    
    # 세션 관리자에서 세션 가져오기 (연결 풀 재사용)
    session_manager = SessionManager()
    session = await session_manager.get_session()
    
    # aiohttp ClientTimeout 설정
    timeout = timeout_config.to_client_timeout()
    
    retry_count = 0
    retry_delay = retry_config.base_delay
    
    while retry_count < retry_config.max_retries:
        try:
            # ===== 요청 준비 =====
            headers = _get_headers(platform)
            request_kwargs = {
                "headers": headers,
                "timeout": timeout,
            }
            
            # 쿠키 추가
            if config.needs_cookies:
                cookies = _get_cookies(platform)
                if cookies:
                    request_kwargs["cookies"] = cookies
            
            # 파라미터 추가
            if config.needs_params:
                params = _get_params(platform, link)
                if params:
                    request_kwargs["params"] = params
            
            # URL 포맷팅
            formatted_url = link
            
            if config.url_formatter:
                formatted_url = config.url_formatter(link)

            if platform == "cafe":
                formatted_url = link.split(",")[0]
            
            # ===== API 요청 실행 =====
            response_data = await _fetch_with_retry(
                session,
                platform,
                formatted_url,
                request_kwargs,
                timeout,
                is_binary=config.is_binary,
            )
            
            # ===== 성공 =====
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            await _log_performance(
                performance_manager,
                platform,
                response_time_ms,
                is_success=True,
                retry_count=retry_count,
            )
            
            logger.info(
                f"✅ {platform} API 성공 | "
                f"응답 시간: {response_time_ms}ms | "
                f"재시도: {retry_count}회"
            )
            
            return config.response_handler(response_data)
        
        # ===== 타임아웃 에러 =====
        except asyncio.TimeoutError:
            retry_count += 1
            await _handle_timeout_error(
                performance_manager,
                platform,
                retry_count,
                retry_config.max_retries,
            )
            
            if retry_count < retry_config.max_retries:
                await asyncio.sleep(retry_delay)
                retry_delay = min(
                    retry_delay * retry_config.exponential_base,
                    retry_config.max_delay,
                )
            else:
                return {}
        
        # ===== 연결 에러 =====
        except aiohttp.ClientConnectorError as e:
            retry_count += 1
            await _handle_connection_error(
                performance_manager,
                platform,
                retry_count,
                retry_config.max_retries,
                type(e).__name__,
                str(e),
            )
            
            if retry_count < retry_config.max_retries:
                await asyncio.sleep(retry_delay)
                retry_delay = min(
                    retry_delay * retry_config.exponential_base,
                    retry_config.max_delay,
                )
            else:
                return {}
        
        # ===== 기타 aiohttp 에러 =====
        except aiohttp.ClientError as e:
            # error_msg = (
            #     f"aiohttp 클라이언트 에러: {platform} - "
            #     f"{type(e).__name__}: {str(e)}"
            # )
            # await log_error(error_msg)
            return {}
        
        # ===== 예상치 못한 에러 =====
        except Exception as e:
            error_msg = (
                f"예상치 못한 에러 in get_message: {platform} - "
                f"{type(e).__name__}: {str(e)}"
            )
            await log_error(error_msg)
            return {}
    
    return {}


# ==================== 헬퍼 함수 ====================
async def _fetch_with_retry(
    session: aiohttp.ClientSession,
    platform: str,
    url: str,
    request_kwargs: Dict[str, Any],
    timeout: ClientTimeout,
    is_binary: bool = False,
) -> Union[str, bytes]:
    """
    aiohttp을 사용한 요청 실행
    
    Args:
        session: aiohttp 세션 (연결 풀 포함)
        platform: 플랫폼명
        url: 요청 URL
        request_kwargs: 요청 파라미터
        timeout: 타임아웃 설정
    
    Returns:
        응답 텍스트
    """
    try:
        async with session.get(url, **request_kwargs) as response:
            if response.status != 200:
                error_msg = (
                    f"HTTP {response.status} error for {platform}: {url}"
                )
                # logger.warning(error_msg)
                raise aiohttp.ClientError(error_msg)
            
            if is_binary:
                return await response.read()  # 바이너리 데이터
            else:
                return await response.text()  # 텍스트 데이터
    
    except asyncio.TimeoutError:
        # logger.warning(f"{datetime.now()} 타임아웃 ({platform}): {url}")
        raise
    
    except aiohttp.ClientConnectorError as e:
        # logger.warning(f"{datetime.now()} 연결 에러 ({platform}): {str(e)}")
        raise
    
    except aiohttp.ClientError as e:
        # logger.warning(f"{datetime.now()} 클라이언트 에러 ({platform}): {str(e)}")
        raise


def _get_platform_configs() -> Dict[str, PlatformConfig]:
    """플랫폼별 API 설정 반환"""
    return {
        "afreeca": PlatformConfig(
            needs_cookies=False,
            needs_params=False,
            url_formatter=None,
            response_handler=lambda r: loads(r),
            is_binary=False,
        ),
        "chzzk": PlatformConfig(
            needs_cookies=True,
            needs_params=True,
            url_formatter=None,
            response_handler=lambda r: loads(r),
            is_binary=False,
        ),
        "twitch": PlatformConfig(
            needs_cookies=False,
            needs_params=False,
            url_formatter=None,
            response_handler=lambda r: loads(r),
            is_binary=False,
        ),
        "cafe": PlatformConfig(
            needs_cookies=False,
            needs_params=True,
            url_formatter=None,
            response_handler=lambda r: loads(r),
            is_binary=False,
        ),
        "youtube": PlatformConfig(
            needs_cookies=False,
            needs_params=False,
            url_formatter=None,
            response_handler=lambda r: r,
            is_binary=False,
        ),
        "image": PlatformConfig(
            needs_cookies=False,
            needs_params=False,
            url_formatter=None,
            response_handler=lambda r: {
                "status_code": 200,
                "content": r,
            },
            is_binary=True,
        ),
    }


def _get_headers(platform: str) -> Dict[str, str]:
    """플랫폼별 헤더 반환"""
    # base.py의 함수들을 임포트해서 사용
    from base import getDefaultHeaders, getTwitchHeaders
    
    if platform == "chzzk":
        return getDefaultHeaders()
    elif platform == "twitch":
        return getTwitchHeaders()
    else:
        return getDefaultHeaders()


def _get_cookies(platform: str) -> Optional[Dict]:
    """플랫폼별 쿠키 반환"""
    from base import getChzzkCookie, getAfreecaCookie
    
    if platform == "chzzk":
        return getChzzkCookie()
    elif platform == "afreeca":
        return getAfreecaCookie()
    
    return None


def _get_params(platform: str, link: str) -> Optional[Dict]:
    """플랫폼별 파라미터 반환"""
    from base import cafe_params
    
    if platform == "cafe":
        page_num = 1  # 기본값
        cafe_num = link.split(",")[-1]  # 링크에서 카페 번호 추출
        return cafe_params(cafe_num, page_num)
    
    return None


async def _log_performance(
    performance_manager,
    platform: str,
    response_time_ms: int,
    is_success: bool,
    retry_count: int = 0,
    http_status_code: Optional[int] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
):
    """성능 로깅"""
    try:
        await performance_manager.log_api_performance(
            api_type=f"{platform}_api",
            response_time_ms=response_time_ms,
            is_success=is_success,
            http_status_code=http_status_code,
            retry_count=retry_count,
            error_type=error_type,
            error_message=error_message,
        )
    except Exception as e:
        logger.error(f"{datetime.now()} 성능 로깅 오류: {str(e)}")


async def _handle_timeout_error(
    performance_manager,
    platform: str,
    retry_count: int,
    max_retries: int,
):
    """타임아웃 에러 처리"""
    error_msg = (
        f"{datetime.now()} ⏱️  API 타임아웃 (시도 {retry_count}/{max_retries}): {platform}"
    )
    
    # logger.warning(error_msg)
    
    if retry_count >= max_retries:
        await log_error(error_msg)
    
    await _log_performance(
        performance_manager,
        platform,
        response_time_ms=0,
        is_success=False,
        retry_count=retry_count,
        error_type="TimeoutError",
        error_message=error_msg,
    )


async def _handle_connection_error(
    performance_manager,
    platform: str,
    retry_count: int,
    max_retries: int,
    error_type: str,
    error_msg: str,
):
    """연결 에러 처리"""
    error_message = (
        f"{datetime.now()} 🔌 API 연결 오류 (시도 {retry_count}/{max_retries}): "
        f"{platform} - {error_type}: {error_msg}"
    )
    
    # logger.warning(error_message)
    
    if retry_count >= max_retries:
        await log_error(error_message)
        
    
    await _log_performance(
        performance_manager,
        platform,
        response_time_ms=0,
        is_success=False,
        retry_count=retry_count,
        error_type=error_type,
        error_message=error_msg,
    )



# ==================== 세션 관리자 초기화 ====================
def initialize_session_manager(config: Optional[ConnectorConfig] = None):

    if config:
        SessionManager.configure(config)
    
    logger.info(
        "SessionManager 초기화 완료 - "
        "aiohttp 연결 풀이 활성화되었습니다"
    )
